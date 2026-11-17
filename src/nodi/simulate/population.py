"""Subscriber attributes (observable) and latent traits (hidden ground truth).

Observable attributes are what an operator's CRM would hold. Latent traits drive behaviour and
are saved only to ground truth.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .calendar import Calendar

# Census 2022 adjusted shares where published; Mymensingh/Sylhet/Barishal from preliminary counts.
DIVISION_SHARE = {
    "Dhaka": 26.88, "Chattogram": 20.13, "Rajshahi": 12.24, "Rangpur": 10.61,
    "Khulna": 10.49, "Mymensingh": 7.39, "Sylhet": 6.68, "Barishal": 5.51,
}
URBAN_SHARE = {  # assumption; weighted national total ~33% urban (census: ~68% rural)
    "Dhaka": 0.55, "Chattogram": 0.35, "Rajshahi": 0.25, "Rangpur": 0.18,
    "Khulna": 0.27, "Mymensingh": 0.18, "Sylhet": 0.22, "Barishal": 0.20,
}
# HIDDEN: Nodi's synthetic network quality by division (never written to observable data)
NETWORK_QUALITY = {
    "Dhaka": 0.4, "Chattogram": 0.3, "Rajshahi": 0.1, "Khulna": 0.1,
    "Mymensingh": -0.1, "Rangpur": -0.2, "Barishal": -0.3, "Sylhet": -0.3,
}
HANDSET_TIERS = np.array(["feature_phone", "low_smart", "mid_smart", "high_smart"])
HANDSET_P = {"urban": [0.30, 0.35, 0.25, 0.10], "rural": [0.52, 0.30, 0.14, 0.04]}
CHANNELS = np.array(["retail_outlet", "activation_kiosk", "care_centre", "digital"])
CHANNEL_P = {"urban": [0.58, 0.14, 0.14, 0.14], "rural": [0.70, 0.16, 0.10, 0.04]}


@dataclass
class Traits:
    """Arrays indexed by sub_id. Everything here except the observable block is hidden truth."""
    # observable / derivable by the operator
    activation_day: np.ndarray
    smart: np.ndarray
    tier: np.ndarray
    urban: np.ndarray
    kiosk: np.ndarray
    # hidden behavioural traits
    engagement: np.ndarray
    price_sens: np.ndarray
    data_aff: np.ndarray
    voice_aff: np.ndarray
    pack_aff: np.ndarray
    has_other_sim: np.ndarray
    competitor_pull: np.ndarray
    w_base: np.ndarray
    network_quality: np.ndarray
    contact_fatigue: np.ndarray
    log_h0: np.ndarray
    # derived behaviour parameters
    base_recharge: np.ndarray
    base_active: np.ndarray
    amount_mu: np.ndarray
    wealth: np.ndarray
    p_pack: np.ndarray
    data_share: np.ndarray
    chan_cum: np.ndarray  # (N, 3) cumulative recharge-channel probabilities
    log_h_static: np.ndarray

    def hidden_frame(self) -> pd.DataFrame:
        n = len(self.engagement)
        return pd.DataFrame({
            "sub_id": np.arange(n, dtype=np.int32),
            "engagement": self.engagement, "price_sensitivity": self.price_sens,
            "data_affinity": self.data_aff, "voice_affinity": self.voice_aff,
            "pack_affinity": self.pack_aff, "has_other_sim": self.has_other_sim,
            "competitor_pull": self.competitor_pull, "wallet_share_base": self.w_base,
            "network_quality": self.network_quality, "contact_fatigue": self.contact_fatigue,
            "log_base_hazard": self.log_h0,
        })


def build_population(n: int, cfg: dict, cal: Calendar, rng: np.random.Generator):
    sim = cfg["simulation"]
    divs = np.array(list(DIVISION_SHARE))
    p_div = np.array(list(DIVISION_SHARE.values()))
    division = rng.choice(divs, size=n, p=p_div / p_div.sum())
    urban = rng.random(n) < np.vectorize(URBAN_SHARE.get)(division)

    tier = np.where(
        urban,
        rng.choice(4, size=n, p=HANDSET_P["urban"]),
        rng.choice(4, size=n, p=HANDSET_P["rural"]),
    )
    smart = tier > 0
    channel = np.where(
        urban,
        rng.choice(4, size=n, p=CHANNEL_P["urban"]),
        rng.choice(4, size=n, p=CHANNEL_P["rural"]),
    )
    kiosk = channel == 1

    # activation: existing base with long tenure tail + new acquisitions inside the window
    n_init = int(round(n * sim["initial_base_share"]))
    is_new = np.zeros(n, dtype=bool)
    is_new[rng.permutation(n)[: n - n_init]] = True
    tenure_days = np.where(
        rng.random(n) < 0.2, rng.exponential(200, n), rng.exponential(1460, n)
    )
    tenure_days = np.clip(tenure_days, 1, 20 * 365).astype(int)
    act = -cal.burn_in - tenure_days
    obs_days = np.arange(0, cal.n_observed)
    w_acq = cal.acquisition_mult[cal.idx(0): cal.idx(cal.n_observed)]
    act[is_new] = rng.choice(obs_days, size=is_new.sum(), p=w_acq / w_acq.sum())

    # ---- hidden traits
    engagement = rng.beta(2.5, 2.0, n) * np.where(kiosk, 0.8, 1.0)
    price_sens = np.clip(rng.beta(2, 2, n) + 0.15 * (~smart) - 0.10 * urban, 0.01, 0.99)
    tier_scale = np.array([0.0, 0.8, 1.0, 1.1])[tier]
    data_aff = np.clip(rng.beta(2, 2, n) * tier_scale, 0, 1)
    voice_aff = rng.beta(2, 2, n)
    pack_aff = np.clip(np.where(smart, 0.3 * voice_aff + 0.7 * data_aff, 0.6 * voice_aff)
                       + rng.normal(0, 0.08, n), 0.0, 1.0)

    dual_sim = rng.random(n) < np.where(smart, 0.80, 0.70)
    has_other = rng.random(n) < 0.25 + 0.40 * dual_sim
    competitor_pull = np.where(has_other, rng.beta(2, 3, n), 0.0)
    w_base = np.where(has_other, 1 - 0.4 * competitor_pull * rng.uniform(0.5, 1.0, n), 1.0)

    nq = np.vectorize(NETWORK_QUALITY.get)(division) + 0.2 * urban + rng.normal(0, 0.25, n)
    contact_fatigue = np.where(rng.random(n) < cfg["truth_world"]["contact_fatigue_share"], rng.uniform(0.6, 1.0, n), rng.uniform(0, 0.05, n))
    log_h0 = np.log(0.0008) + rng.normal(0, 0.8, n)

    # ---- behaviour parameters
    base_recharge = 0.045 + 0.20 * engagement * (0.8 + 0.4 * price_sens)
    base_active = np.clip(0.30 + 0.65 * engagement + 0.05 * smart, 0, 0.98)
    amount_mu = np.log(21) + 0.25 * tier + 0.15 * urban - 0.5 * (price_sens - 0.5)
    wealth = 1 / (1 + np.exp(-2 * (amount_mu - np.log(30))))
    p_pack = 0.10 + 0.45 * pack_aff
    data_share = np.where(smart, data_aff / (data_aff + 0.5 * voice_aff + 1e-9), 0.0)
    p_mfs = 0.20 + 0.25 * smart + 0.10 * urban
    p_app = 0.02 + 0.12 * (tier >= 2) + 0.05 * (urban & smart)
    chan_cum = np.stack([1 - p_mfs - p_app, 1 - p_app, np.ones(n)], axis=1)

    log_h_static = log_h0 - 0.5 * nq - 1.2 * (engagement - 0.55)

    traits = Traits(
        activation_day=act, smart=smart, tier=tier, urban=urban, kiosk=kiosk,
        engagement=engagement, price_sens=price_sens, data_aff=data_aff, voice_aff=voice_aff,
        pack_aff=pack_aff, has_other_sim=has_other, competitor_pull=competitor_pull,
        w_base=w_base, network_quality=nq, contact_fatigue=contact_fatigue, log_h0=log_h0,
        base_recharge=base_recharge, base_active=base_active, amount_mu=amount_mu,
        wealth=wealth, p_pack=p_pack, data_share=data_share, chan_cum=chan_cum,
        log_h_static=log_h_static,
    )

    subscribers = pd.DataFrame({
        "sub_id": np.arange(n, dtype=np.int32),
        "activation_date": [cal.date(int(d)) for d in act],
        "division": division,
        "area_type": np.where(urban, "urban", "rural"),
        "handset_tier": HANDSET_TIERS[tier],
        "dual_sim_handset": dual_sim,
        "acquisition_channel": CHANNELS[channel],
    })
    return subscribers, traits
