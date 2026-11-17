"""Phase 6 orchestrator: every cell x language -> cached or generated variants -> validated ->
app_data/messages.json + review/bangla_review.csv + reports/phase6/summary.md."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from nodi.config import ROOT

from . import generate as G
from .sms import check_message

MESSAGES_PATH = ROOT / "app_data" / "messages.json"
REVIEW_PATH = ROOT / "review" / "bangla_review.csv"
REVIEW_COLS = ["cell_id", "segment", "offer_id", "variant", "bangla_text", "english_gloss", "sms_parts",
               "source", "review_status", "reviewer_notes"]


class MissingFromCache(RuntimeError):
    pass


def run_messages(cfg: dict, mode: str | None = None, cache: G.Cache | None = None,
                 client=None, out_dir: Path | None = None) -> dict:
    spec = G.load_spec()
    mode = G.resolve_mode(cfg, mode)
    cache = cache or G.Cache()
    if mode == "live" and client is None:
        import anthropic  # only needed for live generation
        client = anthropic.Anthropic()
    n = cfg["llm"]["variants"]
    rows, missing, stale = [], [], []
    for cell in G.cells(spec):
        for lang in G.LANGS:
            system, user = G.build_prompt(cell, lang, spec, n)
            key = G.cache_key(cfg["llm"]["model"], system, user)
            rec = cache.get(key)
            if mode == "live" and (rec is None or rec["source"] != "api"):  # live replaces seed copy
                rec = G.generate_live(client, cell, lang, cfg, spec)
                cache.put(key, rec)
            if rec is None:
                rec = cache.latest_for(cell["cell_id"], lang)
                if rec is None:
                    missing.append(f"{cell['cell_id']}/{lang}")
                    continue
                stale.append(f"{cell['cell_id']}/{lang}")
            offer = spec["offers"][cell["offer_id"]]
            for i, v in enumerate(rec["variants"], start=1):
                c = check_message(v["text"], lang, offer, spec)  # re-check: rules may have changed
                rows.append({**cell, "lang": lang, "variant": i, "text": v["text"], "angle": v["angle"],
                             "english_gloss": v["english_gloss"], "encoding": c.encoding, "units": c.units,
                             "parts": c.parts, "valid": c.ok, "errors": c.errors, "source": rec["source"],
                             "model": rec["model"], "attempts": rec.get("attempts", 1),
                             "prompt_stale": f"{cell['cell_id']}/{lang}" in stale})
    if missing:
        raise MissingFromCache(f"{len(missing)} cell/language pairs are not cached and mode is '{mode}': "
                               f"{missing[:6]}... Set ANTHROPIC_API_KEY and run with --live.")

    out_dir = out_dir or ROOT
    mpath = out_dir / MESSAGES_PATH.relative_to(ROOT)
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps({"spec_optout": spec["optout"], "messages": rows}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    _write_review(rows, out_dir / REVIEW_PATH.relative_to(ROOT))
    summary = _summary(rows, mode, stale)
    rdir = Path(cfg["paths"]["reports"]) / "phase6"
    rdir.mkdir(parents=True, exist_ok=True)
    _write_report(rdir, rows, summary, spec)
    return summary


def _write_review(rows: list[dict], path: Path):
    """Bangla copy for native-speaker review. Keeps earlier review notes when the text is unchanged."""
    old = {}
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                old[(r["cell_id"], r["variant"], r["bangla_text"])] = r
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:  # BOM so Excel shows Bangla correctly
        w = csv.DictWriter(f, fieldnames=REVIEW_COLS)
        w.writeheader()
        for r in rows:
            if r["lang"] != "bn":
                continue
            prev = old.get((r["cell_id"], str(r["variant"]), r["text"]), {})
            w.writerow({"cell_id": r["cell_id"], "segment": r["segment"], "offer_id": r["offer_id"],
                        "variant": r["variant"], "bangla_text": r["text"], "english_gloss": r["english_gloss"],
                        "sms_parts": r["parts"], "source": r["source"],
                        "review_status": prev.get("review_status", "PENDING"),
                        "reviewer_notes": prev.get("reviewer_notes", "")})


def _summary(rows, mode, stale) -> dict:
    by_lang = {}
    for lang in G.LANGS:
        rs = [r for r in rows if r["lang"] == lang]
        by_lang[lang] = {"messages": len(rs), "valid": sum(r["valid"] for r in rs),
                         "parts": dict(Counter(r["parts"] for r in rs)),
                         "max_units": max((r["units"] for r in rs), default=0)}
    return {"mode": mode, "cells": len({r["cell_id"] for r in rows}), "messages": len(rows),
            "valid": sum(r["valid"] for r in rows), "by_lang": by_lang,
            "sources": dict(Counter(r["source"] for r in rows)), "stale_prompts": len(stale)}


def _write_report(rdir: Path, rows, s, spec):
    from .sms import check_message as chk
    o = spec["offers"]["bonus_data"]
    demos = [
        ("Model invents a bigger allowance", "en", "Nodi gift: 3 GB free data, valid 7 days. Dial *121*2# to claim. STOP: 21212"),
        ("Model invents a deadline", "en", "Nodi gift: 2 GB free data, valid 7 days. Offer ends in 48 hours! Dial *121*2#. STOP: 21212"),
        ("Taka sign in English (forces Unicode)", "en", "Nodi gift: 2 GB free data, no ৳ needed, valid 7 days. Dial *121*2#. STOP: 21212"),
        ("Number in words", "en", "Nodi gift: two GB free data, valid 7 days. Dial *121*2# to claim. STOP: 21212"),
        ("Opt-out line missing", "en", "Nodi gift: 2 GB free data, valid 7 days. Dial *121*2# to claim."),
        ("Bangla too long (3 parts)", "bn", "নদী-র পক্ষ থেকে আপনার জন্য বিশেষ উপহার, আমরা আপনাকে অনেক মিস করছি এবং চাই আপনি আবার আমাদের সাথে থাকুন: "
         "২ জিবি ফ্রি ডেটা, মেয়াদ ৭ দিন। পেতে ডায়াল করুন *121*2# STOP: 21212"),
        ("Dial code in Bangla digits", "bn", "নদী-র উপহার: ২ জিবি ফ্রি ডেটা, মেয়াদ ৭ দিন। ডায়াল করুন *১২১*২# STOP: 21212"),
        ("Unlimited claim", "bn", "নদী-র উপহার: ২ জিবি ডেটা, আনলিমিটেড কথা, মেয়াদ ৭ দিন। ডায়াল করুন *121*2# STOP: 21212"),
    ]
    lines = ["# Phase 6: campaign SMS (synthetic data)", "",
             f"Mode: **{s['mode']}**. Sources: {s['sources']}. "
             f"{s['cells']} segment x offer cells, {s['messages']} messages, **{s['valid']} pass every check**.", ""]
    if any(r["source"] != "api" for r in rows):
        lines += ["> **Seed copy.** These messages were written in a Claude Code session (claude-opus-5-5), "
                  "assembled from per-segment openings and per-offer bodies, NOT produced by the API pipeline. "
                  "Regenerate with `python run.py --only messages --live` once an API key is set.", ""]
    lines += ["| Language | Messages | Valid | SMS parts | Longest |", "|---|---:|---:|---|---:|"]
    for lang, b in s["by_lang"].items():
        lines.append(f"| {G.LANGS[lang]} | {b['messages']} | {b['valid']} | {b['parts']} | {b['max_units']} units |")
    lines += ["", "## The validator catches what a model might get wrong", "",
              "| Planted mistake | Caught? | Validator says |", "|---|---|---|"]
    for label, lang, text in demos:
        c = chk(text, lang, o, spec)
        lines.append(f"| {label} | {'yes' if not c.ok else '**NO**'} | {'; '.join(c.errors)} |")
    lines += ["", "## One example per segment (variant 1)", ""]
    seen = set()
    for r in rows:
        if r["variant"] != 1 or (r["segment_id"], r["lang"]) in seen:
            continue
        seen.add((r["segment_id"], r["lang"]))
        lines.append(f"- **{r['segment_id']}. {r['segment']}** · {r['offer_id']} · {r['lang']} "
                     f"({r['parts']} part{'s' if r['parts'] > 1 else ''}, {r['units']} {r['encoding']} units): {r['text']}")
    (rdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
