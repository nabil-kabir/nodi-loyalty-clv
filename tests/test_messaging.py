"""Phase 6 tests: SMS maths, fact checks, seed copy, live path with a fake client, mock mode."""
import csv
import json
from types import SimpleNamespace

import pytest

from nodi.config import load_config
from nodi.messaging import generate as G
from nodi.messaging import seed
from nodi.messaging.run import MissingFromCache, run_messages
from nodi.messaging.sms import check_message, encoding, length_units, numbers_in, parts

SPEC = G.load_spec()
BONUS = SPEC["offers"]["bonus_data"]


# ---------------------------------------------------------------- SMS length maths
def test_gsm7_part_boundaries():
    assert encoding("Hello Tk100 *121*2#") == "GSM-7"
    assert parts("a" * 160) == 1 and parts("a" * 161) == 2
    assert parts("a" * 306) == 2 and parts("a" * 307) == 3        # 153 per concatenated part
    assert length_units("[]") == 4                                # extension table counts double


def test_ucs2_part_boundaries_and_taka_sign():
    assert encoding("২ জিবি") == "UCS-2"
    assert encoding("Tk 100") == "GSM-7" and encoding("৳100") == "UCS-2"
    assert parts("ক" * 70) == 1 and parts("ক" * 71) == 2
    assert parts("ক" * 134) == 2 and parts("ক" * 135) == 3       # 67 per concatenated part


# ---------------------------------------------------------------- fact checks
def test_bangla_digits_are_normalised():
    assert numbers_in("২ জিবি, ৭ দিন, *121*2#") == [2, 7, 121, 2]


def test_valid_message_passes_in_both_languages():
    assert check_message("Gift: 2 GB free data, valid 7 days. Dial *121*2#. STOP: 21212", "en", BONUS, SPEC).ok
    assert check_message("উপহার: ২ জিবি ফ্রি ডেটা, মেয়াদ ৭ দিন। ডায়াল *121*2# STOP: 21212", "bn", BONUS, SPEC).ok


@pytest.mark.parametrize("text,lang,expect", [
    ("Gift: 3 GB free data, valid 7 days. Dial *121*2#. STOP: 21212", "en", "not in the offer record"),
    ("Gift: free data, valid 7 days. Dial *121*2#. STOP: 21212", "en", "required offer numbers missing"),
    ("Gift: 2 GB free data, valid 7 days. Dial *121*3#. STOP: 21212", "en", "dial code"),
    ("Gift: 2 GB free data, valid 7 days. Dial *121*2#.", "en", "opt-out"),
    ("Gift: two GB, 2 GB data, valid 7 days. Dial *121*2#. STOP: 21212", "en", "words"),
    ("Gift: 2 GB unlimited data, valid 7 days. Dial *121*2#. STOP: 21212", "en", "forbidden"),
    ("Gift worth ৳: 2 GB data, valid 7 days. Dial *121*2#. STOP: 21212", "en", "GSM-7"),
    ("উপহার: দুই জিবি, ২ জিবি ডেটা, ৭ দিন। *121*2# STOP: 21212", "bn", "words"),
])
def test_validator_rejects(text, lang, expect):
    c = check_message(text, lang, BONUS, SPEC)
    assert not c.ok and any(expect in e for e in c.errors), c.errors


def test_bangla_words_that_merely_contain_numbers_are_allowed():
    # একটু ("a little") contains এক, শতাংশ ("percent") contains শত: neither is a number word
    text = "একটু বাড়তি, ২০ শতাংশ নয়: ২ জিবি ডেটা, ৭ দিন। *121*2# STOP: 21212"
    c = check_message(text, "bn", {**BONUS, "numbers": [2, 7, 20]}, SPEC)
    assert c.ok, c.errors


# ---------------------------------------------------------------- cells and seed
def test_cells_respect_guardrail():
    cs = G.cells(SPEC)
    assert len(cs) == 26
    no_spend = {c["offer_id"] for c in cs if c["stance"] == "no_spend"}
    assert no_spend == {"reminder"}


def test_seed_copy_all_valid_and_labelled():
    recs = seed.seed_records(load_config())
    assert len(recs) == 52
    assert all(r["source"] == seed.SOURCE and "not the API pipeline" in r["model"] for r in recs.values())


# ---------------------------------------------------------------- live path with a fake client
class FakeClient:
    """Mimics client.beta.messages.create: returns queued JSON payloads, records requests."""
    def __init__(self, payloads, stop_reason="end_turn"):
        self.payloads, self.calls, self.stop_reason = list(payloads), [], stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        text = self.payloads.pop(0) if self.payloads else self.calls_default
        return SimpleNamespace(stop_reason=self.stop_reason, stop_details=None, model=kw["model"],
                               content=[SimpleNamespace(type="text", text=text)])


def _payload(texts):
    return json.dumps({"variants": [{"text": t, "angle": "a", "english_gloss": t} for t in texts]})


GOOD = ["Hi! 2 GB free data, valid 7 days. Dial *121*2#. STOP: 21212",
        "Gift: 2 GB free data, valid 7 days. Dial *121*2#. STOP: 21212",
        "Thanks: 2 GB free data, valid 7 days. Dial *121*2#. STOP: 21212"]


def test_live_generation_repairs_rejected_variants():
    cfg = load_config()
    bad = ["Hi! 3 GB free data, valid 7 days. Dial *121*2#. STOP: 21212"] + GOOD[1:]
    client = FakeClient([_payload(bad), _payload(GOOD)])
    cell = next(c for c in G.cells(SPEC) if c["cell_id"] == "S1-bonus_data")
    rec = G.generate_live(client, cell, "en", cfg, SPEC)
    assert rec["attempts"] == 2 and len(rec["repair_history"]) == 1
    second = client.calls[1]["messages"]
    assert second[-1]["role"] == "user" and "not in the offer record: [3]" in second[-1]["content"]
    req = client.calls[0]
    assert req["model"] == cfg["llm"]["model"] and req["fallbacks"] == "default"
    assert req["output_config"]["format"]["type"] == "json_schema"


def test_refusal_is_surfaced():
    cfg = load_config()
    client = FakeClient([_payload(GOOD)], stop_reason="refusal")
    cell = G.cells(SPEC)[0]
    with pytest.raises(G.Refused):
        G.generate_live(client, cell, "en", cfg, SPEC)


def test_live_run_replaces_seed_and_keeps_review_notes(tmp_path, monkeypatch):
    cfg = load_config(data_dir=tmp_path)
    cache = G.Cache(tmp_path / "cache.json")
    seed.write_seed(cfg, cache)
    run_messages(cfg, mode="mock", cache=cache, out_dir=tmp_path)
    review = tmp_path / "review" / "bangla_review.csv"
    rows = list(csv.DictReader(open(review, encoding="utf-8-sig")))
    rows[0]["review_status"], rows[0]["reviewer_notes"] = "APPROVED", "natural"
    with open(review, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    run_messages(cfg, mode="mock", cache=cache, out_dir=tmp_path)   # same text -> note survives
    again = list(csv.DictReader(open(review, encoding="utf-8-sig")))
    assert again[0]["review_status"] == "APPROVED" and again[0]["reviewer_notes"] == "natural"

    # live mode regenerates the seed entries for a cell; use a cache with only one cell's seed removed
    cell = next(c for c in G.cells(SPEC) if c["cell_id"] == "S1-bonus_data")
    system, user = G.build_prompt(cell, "en", SPEC, cfg["llm"]["variants"])
    key = G.cache_key(cfg["llm"]["model"], system, user)
    assert cache.get(key)["source"] == seed.SOURCE
    client = FakeClient([_payload(GOOD)])
    rec = G.generate_live(client, cell, "en", cfg, SPEC)
    cache.put(key, rec)
    assert G.Cache(tmp_path / "cache.json").get(key)["source"] == "api"


def test_mock_mode_without_cache_fails_clearly(tmp_path):
    cfg = load_config(data_dir=tmp_path)
    with pytest.raises(MissingFromCache, match="ANTHROPIC_API_KEY"):
        run_messages(cfg, mode="mock", cache=G.Cache(tmp_path / "empty.json"), out_dir=tmp_path)


def test_cache_key_changes_with_prompt_and_model():
    a = G.cache_key("m1", "sys", "user")
    assert a == G.cache_key("m1", "sys", "user")
    assert a != G.cache_key("m2", "sys", "user") and a != G.cache_key("m1", "sys", "user2")
