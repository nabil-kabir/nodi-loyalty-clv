"""Vectorised day-by-day subscriber simulation.

Mechanics (all hidden from the observable data):
- Multi-SIM subscribers have a share of wallet `w`. Competitor "switch episodes" push it down
  for weeks, which lowers recharging and activity and raises churn hazard.
- A daily churn hazard (traits x wallet share x tenure x new-sub/kiosk x price shock x offers)
  can fire a *churn decision*. The subscriber then fades out over 14-45 days and is absorbed
  (true churn). This gives the operator observable warning signs.
- Dormancy spells (travel, migrant work, SIM rested) silence a subscriber temporarily. A few are
  longer than 90 days, so some "churned" subscribers come back, as in real prepaid data.
- Offers scale the hazard (planted heterogeneous treatment effects) and recharge rate.

Common random numbers: in "future" mode exactly four full-length uniform arrays are drawn per
day, and every sub-decision is derived from them, so treatment arms stay aligned path by path.
"""
from __future__ import annotations

import numpy as np
from scipy.special import ndtri

from . import catalog as C
from .calendar import Calendar
from .population import Traits

PARAMS = dict(
    b_wallet=2.0,          # log-hazard per unit of lost wallet share
    b_tenure=0.08,         # log-hazard reduction per year of tenure (capped at 8y)
    log_new_sub=np.log(2.5),   # first 90 days
    log_kiosk=np.log(1.8),     # activation-kiosk acquisitions, first 180 days
    b_price_shock=1.0,     # hazard x (1 + b * price_sensitivity) during the tariff shock
    switch_rate=0.004,     # daily switch-episode start rate per unit competitor pull
    switch_mean_days=30,
    decline_min=14, decline_max=45,
    dorm_rate=0.0015, dorm_median=25, dorm_sigma=0.7,
    dorm_long_share=0.03, dorm_long_min=120, dorm_long_max=300,
    # treatment effects: delta(log hazard) = -kappa * responsiveness * (1 - atten*pull) + lam * fatigue
    kappa={"bonus_data": 1.3, "recharge_cashback": 1.0, "tenure_reward": 1.5, "bundle_discount": 0.9},
    gamma={"bonus_data": 0.10, "recharge_cashback": 0.35, "tenure_reward": 0.05, "bundle_discount": 0.20},
    cp_atten=0.6,
    lam=1.0,
    effect_days=90, spend_days=30,
)


class State:
    def __init__(self, n: int):
        self.absorbed = np.zeros(n, dtype=bool)
        self.true_churn_day = np.full(n, -10**6, dtype=np.int32)
        self.decline_start = np.full(n, -10**6, dtype=np.int32)
        self.declining = np.zeros(n, dtype=bool)
        self.decline_len = np.ones(n, dtype=np.int32)
        self.dorm_until = np.full(n, -10**6, dtype=np.int32)
        self.switch_until = np.full(n, -10**6, dtype=np.int32)
        self.w_low = np.ones(n)
        self.pack_data_until = np.full(n, -10**6, dtype=np.int32)
        self.pack_voice_until = np.full(n, -10**6, dtype=np.int32)
        self.treat_until = np.full(n, -10**6, dtype=np.int32)
        self.treat_hmult = np.ones(n)
        self.spend_until = np.full(n, -10**6, dtype=np.int32)
        self.spend_mult = np.ones(n)
        self.last_recharge = np.full(n, -10**6, dtype=np.int32)
        self.cum_amount = np.zeros(n)
        self.n_recharge = np.zeros(n, dtype=np.int64)

    def copy(self) -> "State":
        s = State.__new__(State)
        s.__dict__ = {k: v.copy() for k, v in self.__dict__.items()}
        return s


class Engine:
    def __init__(self, traits: Traits, cal: Calendar, params: dict | None = None):
        self.t = traits
        self.cal = cal
        self.p = dict(PARAMS, **(params or {}))
        self.n = len(traits.engagement)
        self.s = State(self.n)

    # ------------------------------------------------------------------ offers
    def responsiveness(self, offer: str, idx: np.ndarray, day: int) -> np.ndarray:
        t = self.t
        if offer == "bonus_data":
            return t.data_aff[idx]
        if offer == "recharge_cashback":
            return t.price_sens[idx]
        if offer == "tenure_reward":
            tenure_m = (day - t.activation_day[idx]) / 30.4
            return np.clip((tenure_m - 12) / 48, 0, 1) * (1 - t.engagement[idx])
        if offer == "bundle_discount":
            return t.pack_aff[idx]
        raise ValueError(offer)

    def true_delta(self, offer: str, idx: np.ndarray, day: int) -> tuple[np.ndarray, np.ndarray]:
        """Planted effect on log daily churn hazard (negative = retains) and responsiveness."""
        p, t = self.p, self.t
        r = self.responsiveness(offer, idx, day)
        delta = -p["kappa"][offer] * r * (1 - p["cp_atten"] * t.competitor_pull[idx]) \
            + p["lam"] * t.contact_fatigue[idx]
        return delta, r

    def apply_offer(self, offer: str, idx: np.ndarray, day: int):
        s, p = self.s, self.p
        delta, r = self.true_delta(offer, idx, day)
        s.treat_until[idx] = day + p["effect_days"]
        s.treat_hmult[idx] = np.exp(delta)
        s.spend_until[idx] = day + p["spend_days"]
        s.spend_mult[idx] = 1 + p["gamma"][offer] * r
        return delta, r

    def redemption_prob(self, offer: str, idx: np.ndarray, day: int) -> np.ndarray:
        r = self.responsiveness(offer, idx, day)
        return np.clip(0.15 + 0.6 * r * (0.5 + self.t.engagement[idx]), 0, 0.95)

    # ------------------------------------------------------------------ hazard
    def control_hazard(self, day: int, w: np.ndarray) -> np.ndarray:
        t, p = self.t, self.p
        age = day - t.activation_day
        log_h = (t.log_h_static + p["b_wallet"] * (1 - w)
                 - p["b_tenure"] * np.minimum(age / 365.0, 8.0))
        log_h = log_h + np.where(age < 90, p["log_new_sub"], 0.0)
        log_h = log_h + np.where(t.kiosk & (age < 180), p["log_kiosk"], 0.0)
        if self.cal.price_shock[self.cal.idx(day)]:
            log_h = log_h + np.log1p(p["b_price_shock"] * t.price_sens)
        return np.exp(log_h)

    def hazard_components(self, day: int) -> dict:
        """Per-subscriber log-hazard decomposition (ground truth 'churn drivers')."""
        t, p, s = self.t, self.p, self.s
        w = np.where(day < s.switch_until, s.w_low, t.w_base)
        age = day - t.activation_day
        return {
            "drv_base": t.log_h0,
            "drv_network_quality": -0.5 * t.network_quality,
            "drv_engagement": -1.2 * (t.engagement - 0.55),
            "drv_wallet_share": p["b_wallet"] * (1 - w),
            "drv_tenure": -p["b_tenure"] * np.minimum(age / 365.0, 8.0),
            "drv_new_sub": np.where(age < 90, p["log_new_sub"], 0.0),
            "drv_kiosk": np.where(t.kiosk & (age < 180), p["log_kiosk"], 0.0),
        }

    # ------------------------------------------------------------------ one day
    def step(self, day: int, rng: np.random.Generator, record: bool) -> dict:
        s, t, p, cal, n = self.s, self.t, self.p, self.cal, self.n
        ci = cal.idx(day)
        u_haz, u_dorm, u_sw, u_rech = rng.random(n), rng.random(n), rng.random(n), rng.random(n)

        # complete fade-outs -> absorbed (true churn)
        done = s.declining & (day >= s.decline_start + s.decline_len)
        if done.any():
            s.absorbed[done] = True
            s.declining[done] = False
            s.true_churn_day[done] = day
        exists = (t.activation_day <= day) & ~s.absorbed
        fade = np.ones(n)
        dl = s.declining
        fade[dl] = np.clip(1 - (day - s.decline_start[dl]) / s.decline_len[dl], 0, 1)

        # competitor switch episodes (multi-SIM only)
        p_sw = p["switch_rate"] * t.competitor_pull
        start = exists & (day >= s.switch_until) & (u_sw < p_sw)
        if start.any():
            v = u_sw[start] / p_sw[start]
            s.switch_until[start] = day + 1 + np.ceil(
                -p["switch_mean_days"] * np.log1p(-0.999 * v)).astype(np.int32)
            s.w_low[start] = 0.05 + 0.25 * ((v * 1000) % 1)
        w = np.where(day < s.switch_until, s.w_low, t.w_base)

        # churn decision
        h_ctrl = self.control_hazard(day, w)
        h = np.where(day < s.treat_until, h_ctrl * s.treat_hmult, h_ctrl)
        p_fire = -np.expm1(-h)
        fire = exists & ~s.declining & (u_haz < p_fire)
        if fire.any():
            v = u_haz[fire] / p_fire[fire]
            s.declining[fire] = True
            s.decline_start[fire] = day
            s.decline_len[fire] = p["decline_min"] + (v * (p["decline_max"] - p["decline_min"] + 1)).astype(np.int32)

        # dormancy spells
        in_dorm = day < s.dorm_until
        p_d = p["dorm_rate"] * (1.5 - t.engagement)
        startd = exists & ~in_dorm & ~s.declining & (u_dorm < p_d)
        if startd.any():
            v = u_dorm[startd] / p_d[startd]
            sh = p["dorm_long_share"]
            long_ = v < sh
            vv = np.clip((v - sh) / (1 - sh), 1e-6, 1 - 1e-6)
            length = np.where(
                long_,
                p["dorm_long_min"] + (v / sh) * (p["dorm_long_max"] - p["dorm_long_min"]),
                np.exp(np.log(p["dorm_median"]) + p["dorm_sigma"] * ndtri(vv)),
            )
            s.dorm_until[startd] = day + 1 + length.astype(np.int32)
            in_dorm = day < s.dorm_until

        # recharge
        r = t.base_recharge * w * cal.recharge_mult[ci] * fade
        r = np.where(day < s.spend_until, r * s.spend_mult, r)
        renew = (s.pack_data_until == day) | (s.pack_voice_until == day)
        r = np.minimum(np.where(renew, r * (1 + 2 * t.pack_aff), r), 0.95)
        rech = exists & ~in_dorm & (u_rech < r)
        idx = np.flatnonzero(rech)

        # pack decision derived from the recharge uniform (keeps CRN alignment)
        v = u_rech[idx] / r[idx]
        v2, v3 = (v * 1e3) % 1, (v * 1e6) % 1
        buy = v < t.p_pack[idx]
        ds = t.data_share[idx]
        ptype = np.where(v2 < ds, np.where(v2 < 0.25 * ds, 2, 1), 0)
        k = np.minimum(C.TYPE_COUNT[ptype] - 1,
                       (((0.5 * t.wealth[idx] + 0.5 * v3) ** 1.8) * C.TYPE_COUNT[ptype]).astype(int))
        pack = C.TYPE_OFFSET[ptype] + k
        bi, bp = idx[buy], pack[buy]
        val = C.PACK_VALIDITY[bp]
        is_data = C.PACK_TYPE_CODE[bp] >= 1
        is_voice = C.PACK_TYPE_CODE[bp] != 1
        s.pack_data_until[bi[is_data]] = day + val[is_data]
        s.pack_voice_until[bi[is_voice]] = day + val[is_voice]
        s.last_recharge[idx] = day

        out = {"rech_mask": rech, "h": h, "h_ctrl": h_ctrl}
        if not record:
            return out

        # ---------------- observable events (observed / burn-in mode only)
        m = len(idx)
        z, u_ch, u_dir = rng.normal(0, 1, m), rng.random(m), rng.random(m)
        chan = (u_ch[:, None] > t.chan_cum[idx]).sum(axis=1)
        amount = C.snap_to_denomination(np.exp(t.amount_mu[idx] + 0.55 * z))
        price = np.where(buy, C.PACK_PRICE[pack], 0)
        direct = buy & (chan >= 1) & (u_dir < 0.7)
        amount = np.where(direct, price, np.where(buy, np.maximum(amount, C.ceil_to_denomination(price)), amount))
        s.cum_amount[idx] += amount
        s.n_recharge[idx] += 1

        a = t.base_active * w ** 0.6 * fade
        active = rech | (exists & ~in_dorm & (rng.random(n) < a))
        ai = np.flatnonzero(active)
        voice = rng.gamma(1.5, (3 + 7 * t.voice_aff[ai]) / 1.5) * cal.voice_mult[ci]
        voice *= np.where(s.pack_voice_until[ai] >= day, 1.5, 1.0)
        tier_mult = np.array([0.0, 0.7, 1.0, 1.4])[t.tier[ai]]
        mean_mb = np.where(s.pack_data_until[ai] >= day,
                           (200 + 900 * t.data_aff[ai]) * tier_mult,
                           (8 + 25 * t.data_aff[ai]) * (tier_mult > 0))
        data = np.where(mean_mb > 0, rng.gamma(1.3, np.maximum(mean_mb, 1e-9) / 1.3), 0.0) * cal.data_mult[ci]
        sms = rng.poisson(0.25, len(ai))

        out.update(
            recharges=(idx, amount, chan, direct),
            packs=(bi, bp),
            usage=(ai, voice, data, sms),
        )
        return out

    def mean_amount(self) -> np.ndarray:
        """Per-subscriber mean observed recharge (used to value future recharges in ground truth)."""
        s, t = self.s, self.t
        fallback = np.exp(t.amount_mu + 0.5 * 0.55 ** 2)
        return np.where(s.n_recharge > 0, s.cum_amount / np.maximum(s.n_recharge, 1), fallback)
