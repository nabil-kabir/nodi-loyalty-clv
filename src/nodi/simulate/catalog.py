"""Nodi Telecom's (fictional) pack catalogue, recharge denominations and nominal offers.

Prices are illustrative and labelled as assumptions in ASSUMPTIONS.md.
Packs are ordered by type (voice, data, combo) and by price within type; the engine relies on that.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PACKS = pd.DataFrame(
    [
        # pack_id, name,        type,    price, data_mb, voice_min, validity_days
        ("V29",   "Talk 40",    "voice",  29,       0,  40,  7),
        ("V69",   "Talk 100",   "voice",  69,       0, 100, 15),
        ("V199",  "Talk 300",   "voice", 199,       0, 300, 30),
        ("D29",   "Data Mini",  "data",   29,     500,   0,  3),
        ("D59",   "Data 1GB",   "data",   59,    1024,   0,  7),
        ("D109",  "Data 3GB",   "data",  109,    3072,   0,  7),
        ("D299",  "Data 10GB",  "data",  299,   10240,   0, 30),
        ("D499",  "Data 25GB",  "data",  499,   25600,   0, 30),
        ("C79",   "Combo S",    "combo",  79,    1024,  50,  7),
        ("C349",  "Combo L",    "combo", 349,    8192, 200, 30),
    ],
    columns=["pack_id", "name", "pack_type", "price_bdt", "data_mb", "voice_min", "validity_days"],
)

TYPE_CODES = {"voice": 0, "data": 1, "combo": 2}
PACK_TYPE_CODE = PACKS["pack_type"].map(TYPE_CODES).to_numpy()
PACK_PRICE = PACKS["price_bdt"].to_numpy()
PACK_VALIDITY = PACKS["validity_days"].to_numpy()
TYPE_OFFSET = np.array([0, 3, 8])
TYPE_COUNT = np.array([3, 5, 2])

DENOMINATIONS = np.array([10, 20, 30, 50, 100, 150, 200, 300, 500, 1000])

RECHARGE_CHANNELS = np.array(["retailer", "mfs", "app"])

# Nominal offer designs. The planted treatment effects are tied to these designs.
# Phase 5 attaches the ৳ cost model; values here are descriptive only.
OFFERS = pd.DataFrame(
    [
        ("bonus_data",      "Bonus data",      "2 GB free data, 7-day validity"),
        ("recharge_cashback", "Recharge cashback", "20% cashback (max ৳30) on next recharge of ৳100+"),
        ("tenure_reward",   "Tenure reward",   "Loyalty thank-you: 1 GB + 50 min, 7-day validity"),
        ("bundle_discount", "Bundle discount", "30% off Combo L (8 GB + 200 min, 30 days)"),
    ],
    columns=["offer_id", "name", "nominal_design"],
)
OFFER_IDS = OFFERS["offer_id"].tolist()


def snap_to_denomination(x: np.ndarray) -> np.ndarray:
    """Nearest recharge denomination on a log scale."""
    logs = np.log(DENOMINATIONS)
    mids = (logs[1:] + logs[:-1]) / 2
    return DENOMINATIONS[np.searchsorted(mids, np.log(np.maximum(x, 1)))]


def ceil_to_denomination(x: np.ndarray) -> np.ndarray:
    i = np.minimum(np.searchsorted(DENOMINATIONS, x), len(DENOMINATIONS) - 1)
    return DENOMINATIONS[i]
