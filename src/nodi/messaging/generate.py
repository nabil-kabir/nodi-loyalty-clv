"""Generate campaign SMS with Claude, validate hard, cache everything, run without a key in mock mode.

Modes (config llm.mode, or run.py --live / --mock):
  live : call the Anthropic API for any cell not already cached for the exact same prompt
  mock : read only from the on-disk cache (no API key needed). This is the default when no
         ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN is set.
  auto : live if credentials are present, else mock

Facts never come from the model: offer numbers are injected from messaging.yml, and every
generated message is checked by nodi.messaging.sms.check_message. Invalid variants are sent back
to the model with the validator's errors (up to llm.max_repairs times), and any still invalid are
kept out of the app.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import yaml

from nodi.config import ROOT
from nodi.segments.build import load_spec as load_segments

from .sms import check_message

CACHE_PATH = ROOT / "app_data" / "llm_cache" / "sms_cache.json"
PROMPT_VERSION = 1
LANGS = {"en": "English", "bn": "Bangla"}

SCHEMA = {
    "type": "object",
    "properties": {
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "angle": {"type": "string"},
                    "english_gloss": {"type": "string"},
                },
                "required": ["text", "angle", "english_gloss"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["variants"],
    "additionalProperties": False,
}


def load_spec(path: Path | None = None) -> dict:
    with open(path or ROOT / "messaging.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cells(spec: dict) -> list[dict]:
    """Segment x offer cells. No-spend segments only get the free reminder (DECISIONS B5.4)."""
    segs = load_segments()
    out = []
    for s in segs["segments"]:
        offers = ["reminder"] if s["stance"] == "no_spend" else \
            ["bonus_data", "recharge_cashback", "tenure_reward", "bundle_discount"]
        for o in offers:
            out.append({"cell_id": f"S{s['id']}-{o}", "segment_id": s["id"], "segment": s["name"],
                        "stance": s["stance"], "offer_id": o})
    return out


def build_prompt(cell: dict, lang: str, spec: dict, n_variants: int) -> tuple[str, str]:
    limit = spec["sms_limits"][lang]
    budget = 160 if lang == "en" else 67 * limit if limit > 1 else 70
    system = (
        "You write promotional SMS for Nodi Telecom, a fictional Bangladeshi mobile operator. "
        "All customers and data are synthetic; this is a portfolio project.\n\n"
        f"BRAND VOICE\n{spec['brand_voice']}\n"
        "HARD RULES (messages that break them are rejected automatically)\n"
        "- Use ONLY the numbers listed in the offer record, written as digits. No other numbers, no number words.\n"
        "- Include the dial code exactly as given (English digits) when the offer has one.\n"
        f"- End every message with exactly: {spec['optout']}\n"
        "- English messages: only basic GSM-7 characters (no taka sign, no curly quotes, no emoji).\n"
        "- Each variant must take a clearly different angle (opening line and emphasis), not a rewording.\n"
    )
    o = spec["offers"][cell["offer_id"]]
    user = (
        f"Write {n_variants} SMS variants in {LANGS[lang]}.\n\n"
        f"AUDIENCE (segment {cell['segment_id']}, {cell['segment']}): {spec['segment_angles'][cell['segment_id']]}\n"
        f"OFFER RECORD: {o['facts']}\n"
        f"ALLOWED NUMBERS: {o['numbers']} (must include {o['required']})\n"
        f"DIAL CODE: {o['dial_code'] or 'none - do not invent one'}\n"
        f"OPT-OUT LINE (end with it): {spec['optout']}\n"
        f"LENGTH: at most {budget} characters including the opt-out line"
        f"{' (Bangla is sent as Unicode SMS)' if lang == 'bn' else ''}.\n\n"
        "For each variant return: text (the SMS exactly as sent), angle (3-6 words), "
        "english_gloss (a literal English translation for Bangla; repeat the text for English)."
    )
    return system, user


def cache_key(model: str, system: str, user: str) -> str:
    raw = json.dumps({"v": PROMPT_VERSION, "model": model, "system": system, "user": user}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class Cache:
    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def get(self, key):
        return self.data.get(key)

    def latest_for(self, cell_id: str, lang: str):
        """Mock-mode fallback when the prompt changed after caching: newest entry for the cell."""
        hits = [v for v in self.data.values() if v["cell_id"] == cell_id and v["lang"] == lang]
        return max(hits, key=lambda v: v["created_at"]) if hits else None

    def put(self, key, record):
        self.data[key] = record
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


class Refused(RuntimeError):
    pass


def resolve_mode(cfg: dict, override: str | None = None) -> str:
    mode = override or cfg["llm"].get("mode", "auto")
    if mode == "auto":
        has_creds = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
        return "live" if has_creds else "mock"
    return mode


def call_claude(client, cfg: dict, system: str, messages: list) -> tuple[str, str]:
    """One structured-output request. Server-side refusal fallback is on by default."""
    llm = cfg["llm"]
    resp = client.beta.messages.create(
        model=llm["model"],
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        messages=messages,
        output_config={"effort": llm.get("effort", "medium"),
                       "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if resp.stop_reason == "refusal":
        cat = resp.stop_details.category if resp.stop_details else None
        raise Refused(f"request declined (category: {cat})")
    text = next(b.text for b in resp.content if b.type == "text")
    return text, resp.model


def generate_live(client, cell, lang, cfg, spec) -> dict:
    llm = cfg["llm"]
    system, user = build_prompt(cell, lang, spec, llm["variants"])
    offer = spec["offers"][cell["offer_id"]]
    messages = [{"role": "user", "content": user}]
    attempts = []
    for attempt in range(1 + llm.get("max_repairs", 2)):
        text, served_by = call_claude(client, cfg, system, messages)
        variants = json.loads(text)["variants"]
        checks = [check_message(v["text"], lang, offer, spec) for v in variants]
        attempts.append({"variants": variants, "errors": [c.errors for c in checks]})
        problems = [f"Variant {i + 1}: {'; '.join(c.errors)}" for i, c in enumerate(checks) if not c.ok]
        if len(variants) != llm["variants"]:
            problems.append(f"Return exactly {llm['variants']} variants (got {len(variants)}).")
        if not problems:
            break
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "The validator rejected some variants:\n" + "\n".join(problems)
                      + "\nReturn all variants again with these fixed. Keep the valid ones as they are."}]
    return {"cell_id": cell["cell_id"], "lang": lang, "variants": variants, "attempts": len(attempts),
            "repair_history": attempts[:-1], "model": served_by, "source": "api",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
