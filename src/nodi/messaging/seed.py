"""Seed cache so the project runs in mock mode before anyone has an API key (DECISIONS B6.2).

HONEST LABEL: this copy was written by Claude (claude-opus-5-5) in a Claude Code session, not
produced by the API pipeline. It is assembled from three per-segment opening lines and one
per-offer body, so variants differ only in their opening. Every message still passes
nodi.messaging.sms.check_message. Running `python run.py --only messages --live` with a key
replaces every seed entry with real pipeline output under the same cache keys.

    python -m nodi.messaging.seed
"""
from __future__ import annotations

from nodi.config import load_config

from . import generate as G
from .sms import check_message

SOURCE = "seed-claude-code-session"
MODEL = "claude-opus-5-5 (Claude Code session, not the API pipeline)"
CREATED = "2026-11-17T00:00:00+00:00"

BODY = {
    "en": {
        "bonus_data": "2 GB free data, valid 7 days. Dial *121*2# to claim.",
        "recharge_cashback": "Recharge Tk100 or more within 7 days and get 20% cashback, up to Tk30.",
        "tenure_reward": "1 GB data + 50 min free, valid 7 days. Dial *121*4# to claim.",
        "bundle_discount": "Combo L, 8 GB + 200 min for 30 days, now Tk244 (was Tk349). Dial *121*5# within 7 days.",
        "reminder": "Data 1GB, 7 days, only Tk59. Dial *121*1# to buy.",
    },
    "bn": {
        "bonus_data": ("২ জিবি ফ্রি ডেটা, মেয়াদ ৭ দিন। পেতে ডায়াল করুন *121*2#",
                       "2 GB free data, valid 7 days. To get it, dial *121*2#"),
        "recharge_cashback": ("৭ দিনের মধ্যে ১০০ টাকা বা বেশি রিচার্জে ২০% ক্যাশব্যাক, সর্বোচ্চ ৩০ টাকা।",
                              "20% cashback on a recharge of Tk 100 or more within 7 days, up to Tk 30."),
        "tenure_reward": ("১ জিবি ডেটা + ৫০ মিনিট ফ্রি, মেয়াদ ৭ দিন। পেতে ডায়াল করুন *121*4#",
                          "1 GB data + 50 minutes free, valid 7 days. To get it, dial *121*4#"),
        "bundle_discount": ("কম্বো এল: ৮ জিবি + ২০০ মিনিট, ৩০ দিন, ২৪৪ টাকা (আগে ৩৪৯)। ৭ দিনের মধ্যে ডায়াল *121*5#",
                            "Combo L: 8 GB + 200 minutes, 30 days, Tk 244 (was 349). Dial *121*5# within 7 days."),
        "reminder": ("১ জিবি ডেটা, ৭ দিন, মাত্র ৫৯ টাকা। কিনতে ডায়াল করুন *121*1#",
                     "1 GB data, 7 days, only Tk 59. To buy, dial *121*1#"),
    },
}

# (English opening, Bangla opening, Bangla literal gloss, angle) x 3 per segment
OPENERS = {
    1: [("We miss you at Nodi!", "নদী আপনাকে মিস করছে!", "Nodi misses you!", "we miss you"),
        ("Come back to Nodi:", "নদী-তে ফিরে আসুন:", "Come back to Nodi:", "come-back invitation"),
        ("A welcome-back gift from Nodi:", "ফিরে আসার উপহার:", "A welcome-back gift:", "gift framing")],
    2: [("Welcome to Nodi!", "নদী-তে স্বাগতম!", "Welcome to Nodi!", "warm welcome"),
        ("Nodi gift for new customers:", "নতুন গ্রাহকের জন্য নদী-র উপহার:", "Nodi's gift for new customers:", "new-customer gift"),
        ("Make a great start with Nodi:", "নদী-র সাথে শুরুটা হোক দারুণ:", "Make a great start with Nodi:", "good start")],
    3: [("Just for you:", "শুধু আপনার জন্য:", "Just for you:", "personal pick"),
        ("For you, from Nodi:", "নদী-র পক্ষ থেকে আপনার জন্য:", "For you, from Nodi:", "from the brand"),
        ("Stay connected with Nodi:", "নদী-র সাথে যুক্ত থাকুন:", "Stay connected with Nodi:", "stay connected")],
    4: [("Thank you for staying with Nodi!", "নদী-র সাথে থাকার জন্য ধন্যবাদ!", "Thank you for staying with Nodi!", "loyalty thanks"),
        ("A thank-you from Nodi:", "নদী-র পক্ষ থেকে ধন্যবাদ:", "A thank-you from Nodi:", "simple thanks"),
        ("You are special to us:", "আপনি আমাদের কাছে বিশেষ:", "You are special to us:", "you matter")],
    5: [("Haven't seen you in a while!", "অনেকদিন দেখা নেই!", "Haven't seen you in a while!", "gentle check-in"),
        ("Nodi reminder:", "নদী-র রিমাইন্ডার:", "Nodi reminder:", "plain reminder"),
        ("Come back to Nodi:", "আবার নদী-তে আসুন:", "Come back to Nodi:", "come-back invitation")],
    6: [("Nodi reminder:", "নদী-র রিমাইন্ডার:", "Nodi reminder:", "plain reminder"),
        ("Greetings from Nodi:", "নদী থেকে শুভেচ্ছা:", "Greetings from Nodi:", "friendly hello"),
        ("Stay connected:", "যুক্ত থাকুন:", "Stay connected:", "stay connected")],
    7: [("Nodi tip:", "নদী-র টিপস:", "Nodi tip:", "helpful tip"),
        ("A quick tip from Nodi:", "নদী থেকে ছোট্ট টিপস:", "A small tip from Nodi:", "quick tip"),
        ("Stay online with Nodi:", "নদী-র সাথে অনলাইনে থাকুন:", "Stay online with Nodi:", "stay online")],
    8: [("A little extra from Nodi:", "নদী-র পক্ষ থেকে একটু বাড়তি:", "A little extra from Nodi:", "small extra"),
        ("For you from Nodi:", "আপনার জন্য নদী থেকে:", "For you from Nodi:", "from the brand"),
        ("Nodi bonus:", "নদী বোনাস:", "Nodi bonus:", "bonus framing")],
}


def seed_records(cfg: dict) -> dict[str, dict]:
    spec = G.load_spec()
    out, failures = {}, []
    for cell in G.cells(spec):
        for lang in G.LANGS:
            variants = []
            for en_open, bn_open, bn_gloss, angle in OPENERS[cell["segment_id"]]:
                if lang == "en":
                    text = f"{en_open} {BODY['en'][cell['offer_id']]} {spec['optout']}"
                    gloss = text
                else:
                    body, body_gloss = BODY["bn"][cell["offer_id"]]
                    text = f"{bn_open} {body} {spec['optout']}"
                    gloss = f"{bn_gloss} {body_gloss} {spec['optout']}"
                c = check_message(text, lang, spec["offers"][cell["offer_id"]], spec)
                if not c.ok:
                    failures.append((cell["cell_id"], lang, text, c.errors))
                variants.append({"text": text, "angle": angle, "english_gloss": gloss})
            system, user = G.build_prompt(cell, lang, spec, cfg["llm"]["variants"])
            key = G.cache_key(cfg["llm"]["model"], system, user)
            out[key] = {"cell_id": cell["cell_id"], "lang": lang, "variants": variants, "attempts": 1,
                        "repair_history": [], "model": MODEL, "source": SOURCE, "created_at": CREATED}
    if failures:
        raise ValueError("seed copy fails validation:\n" + "\n".join(map(str, failures)))
    return out


def write_seed(cfg: dict, cache: G.Cache | None = None) -> int:
    cache = cache or G.Cache()
    recs = seed_records(cfg)
    for k, v in recs.items():
        if cache.get(k) is None or cache.get(k)["source"] != "api":  # never overwrite real output
            cache.data[k] = v
    cache.put(next(iter(recs)), cache.data[next(iter(recs))])  # persist
    return len(recs)


if __name__ == "__main__":
    print(f"seeded {write_seed(load_config())} cell/language entries")
