"""Churn drivers in business language.

Two layers:
1. How much each *theme* contributes to the model's risk ranking (mean |SHAP|, grouped).
2. A plain-English, measured statement per theme: observed churn rates in contrasting groups on
   the out-of-time test set, plus the CVM action it implies.
"""
from __future__ import annotations

import pandas as pd

THEMES = {
    "Activity falling off": ["active_days_30", "active_days_prev30", "voice_30", "voice_prev30", "voice_trend",
                             "data_mb_30", "data_mb_prev30", "data_trend"],
    "Gone quiet on recharges": ["days_since_last_event", "max_gap_90"],
    "Recharge slowdown": ["rech_30", "rech_prev30", "rech_90", "rech_180", "rech_trend", "gross_30", "gross_90"],
    "Tenure and how they joined": ["tenure_months", "acquisition_channel"],
    "Where they live (network)": ["division", "area_type"],
    "Handset and spend level": ["handset_tier", "is_smartphone", "dual_sim_handset", "avg_recharge_90",
                                "mfs_share_90", "app_share_90"],
    "Pack habit": ["n_packs_90", "pack_spend_90", "data_pack_share_90", "days_to_pack_expiry"],
    "History (dormancy, offers)": ["dormant_spells_365", "ever_reactivated", "n_offers_90", "offer_redeemed_90"],
}


def theme_importance(contrib: pd.DataFrame) -> pd.DataFrame:
    imp = contrib.abs().mean()
    rows = [{"theme": t, "share": imp[cols].sum() / imp.sum()} for t, cols in THEMES.items()]
    return pd.DataFrame(rows).sort_values("share", ascending=False).reset_index(drop=True)


def _rate(df, mask):
    return df.loc[mask, "churn_90d"].mean(), int(mask.sum())


def statements(test: pd.DataFrame) -> pd.DataFrame:
    """Measured contrasts on the test snapshot. Each row: theme, finding, action."""
    d = test
    out = []

    def add(theme, hi_mask, lo_mask, hi_label, lo_label, action):
        hr, hn = _rate(d, hi_mask)
        lr, ln = _rate(d, lo_mask)
        out.append({
            "theme": theme,
            "finding": f"{hi_label}: {hr:.0%} churn next quarter vs {lr:.0%} for {lo_label} ({hr / lr:.1f}x).",
            "group_share_of_base": hn / len(d), "rate_high": hr, "rate_low": lr, "ratio": hr / lr,
            "action": action,
        })

    add("Activity falling off",
        d.active_days_30 < 0.5 * d.active_days_prev30, d.active_days_30 >= d.active_days_prev30,
        "Subscribers active on fewer than half as many days as the month before",
        "those holding steady",
        "Trigger a contact in the week activity halves, not after recharges stop.")
    add("Gone quiet on recharges",
        d.days_since_last_event >= 21, d.days_since_last_event <= 7,
        "No recharge for 3+ weeks", "those who recharged in the last week",
        "Silence is the strongest signal but arrives late; treat 21+ days as last-chance win-back.")
    add("Recharge slowdown",
        (d.rech_prev30 >= 2) & (d.rech_30 < 0.5 * d.rech_prev30),
        (d.rech_prev30 >= 2) & (d.rech_30 >= d.rech_prev30),
        "Recharges more than halved vs the previous month", "steady rechargers",
        "Today's win-back rule uses this; the model ranks within it far better.")
    add("Tenure and how they joined",
        d.tenure_months < 6, d.tenure_months >= 60,
        "Subscribers in their first 6 months", "5+ year customers",
        "Invest in onboarding (first 90 days) rather than late rescue for new SIMs.")
    kiosk = d.acquisition_channel.astype(str) == "activation_kiosk"
    add("Tenure and how they joined",
        kiosk, ~kiosk, "Street activation-kiosk acquisitions", "all other channels",
        "Review kiosk incentives: they buy SIMs, not customers.")
    weak = d.division.astype(str).isin(["Sylhet", "Barishal", "Rangpur"])
    add("Where they live (network)",
        weak, d.division.astype(str) == "Dhaka", "Sylhet, Barishal and Rangpur", "Dhaka",
        "A network problem, not a marketing one: share this with the network team before buying offers.")
    add("Pack habit",
        d.n_packs_90 == 0, d.n_packs_90 >= 3, "No pack bought in 90 days", "regular pack buyers (3+)",
        "Pack habits anchor people; a first-pack nudge is a cheap retention lever.")
    add("History (dormancy, offers)",
        d.dormant_spells_365 >= 2, d.dormant_spells_365 == 0, "Two or more 30-day silences in the past year",
        "never dormant", "Serial sleepers: likely secondary SIMs; don't spend premium offers on them.")
    return pd.DataFrame(out)
