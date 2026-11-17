"""SMS encoding, length and part counting, plus fact checks. Pure functions, no model calls.

GSM-7 (3GPP TS 23.038 default alphabet): 160 septets in one SMS, 153 per part when concatenated.
Characters from the extension table (^ { } \\ [ ~ ] | and the euro sign) take 2 septets.
Anything outside GSM-7 (Bangla script, the taka sign, emoji, curly quotes) forces UCS-2:
70 UTF-16 code units in one SMS, 67 per part.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXT = set("^{}\\[~]|€\f")
BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
EN_NUMBER_WORDS = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|fifty|hundred|double|half)\b",
    re.IGNORECASE)
# Whole Bangla tokens only: substrings would hit ordinary words (একটু "a little", শতাংশ "percent").
# নয় is left out on purpose: it usually means "is not".
BN_NUMBER_WORDS = {"এক", "একটি", "দুই", "দুটি", "দুইটি", "তিন", "তিনটি", "চার", "চারটি", "পাঁচ", "ছয়",
                   "সাত", "আট", "দশ", "বিশ", "ত্রিশ", "পঞ্চাশ", "একশ", "একশো", "দ্বিগুণ", "অর্ধেক"}
TOKEN_SPLIT = re.compile(r"[\s,.;:!?()\[\]'\"।+/-]+")


def number_word(text: str) -> str | None:
    m = EN_NUMBER_WORDS.search(text)
    if m:
        return m.group(0)
    return next((t for t in TOKEN_SPLIT.split(text) if t in BN_NUMBER_WORDS), None)
BANNED = re.compile(r"unlimited|forever|guarantee|আনলিমিটেড|সীমাহীন|চিরকাল|গ্যারান্টি", re.IGNORECASE)
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿]")


def encoding(text: str) -> str:
    return "GSM-7" if all(c in GSM7_BASIC or c in GSM7_EXT for c in text) else "UCS-2"


def length_units(text: str) -> int:
    if encoding(text) == "GSM-7":
        return sum(2 if c in GSM7_EXT else 1 for c in text)
    return len(text.encode("utf-16-le")) // 2


def parts(text: str) -> int:
    n = length_units(text)
    single, multi = (160, 153) if encoding(text) == "GSM-7" else (70, 67)
    return 1 if n <= single else math.ceil(n / multi)


def numbers_in(text: str) -> list[int]:
    """All integers written in digits (Bangla or ASCII), dial codes split into their parts."""
    return [int(x) for x in re.findall(r"\d+", text.translate(BN_DIGITS))]


@dataclass
class Check:
    ok: bool
    errors: list[str] = field(default_factory=list)
    encoding: str = ""
    units: int = 0
    parts: int = 0


def check_message(text: str, lang: str, offer: dict, spec: dict) -> Check:
    """Every hard rule a message must pass before it can be cached or shown."""
    errs = []
    enc, units, n_parts = encoding(text), length_units(text), parts(text)
    limit = spec["sms_limits"][lang]
    if lang == "en" and enc != "GSM-7":
        bad = sorted({c for c in text if c not in GSM7_BASIC and c not in GSM7_EXT})
        errs.append(f"English must be GSM-7; non-GSM characters: {''.join(bad)}")
    if n_parts > limit:
        errs.append(f"{n_parts} SMS parts ({units} {enc} units); limit is {limit}")
    optout = spec["optout"]
    if not text.rstrip().endswith(optout):
        errs.append(f"must end with the opt-out line '{optout}'")
    # Facts are checked on the copy itself: digits inside the dial code (*121*2#) or the opt-out
    # short code must not count as "mentioning 2 GB", nor be flagged as stray numbers.
    body = text
    for code in [offer.get("dial_code"), optout]:
        if code:
            body = body.replace(code, " ")
    allowed = set(offer["numbers"])
    found = numbers_in(body)
    stray = sorted(set(found) - allowed)
    if stray:
        errs.append(f"numbers not in the offer record: {stray}")
    missing = sorted(set(offer["required"]) - set(found))
    if missing:
        errs.append(f"required offer numbers missing: {missing}")
    if offer.get("dial_code") and offer["dial_code"] not in text:
        errs.append(f"dial code {offer['dial_code']} missing or altered (keep English digits)")
    word = number_word(text)
    if word:
        errs.append(f"number written in words ('{word}'): use digits")
    if BANNED.search(text):
        errs.append(f"forbidden claim: '{BANNED.search(text).group(0)}'")
    if EMOJI.search(text):
        errs.append("emoji not allowed")
    if lang == "bn" and not re.search(r"[ঀ-৿]", text):
        errs.append("Bangla message contains no Bangla script")
    return Check(not errs, errs, enc, units, n_parts)
