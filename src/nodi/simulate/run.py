"""Phase 1 orchestrator: burn-in -> observed 18 months (with campaigns + randomised pilot)
-> hidden 12-month future for ground truth.

Writes observable tables to data/raw and planted truth to data/ground_truth.
"""
from __future__ import annotations

import shutil
import time

import numpy as np
import pandas as pd
import pyarrow as pa

from . import catalog as C
from .calendar import build_calendar
from .churn import derive_inactivity
from .engine import Engine
from .population import build_population
from .writer import MonthlyWriter

ARMS = ["control"] + C.OFFER_IDS


def _log(msg: str):
    print(f"[simulate {time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Campaigns:
    """Business-as-usual (targeted, non-random) campaigns + the randomised pilot."""

    def __init__(self, eng: Engine, cal, cfg, rng):
        self.eng, self.cal, self.cfg, self.rng = eng, cal, cfg, rng
        n = eng.n
        self.ring = np.zeros((60, n), dtype=np.int8)  # recharge counts, last 60 days
        self.rows: list[pd.DataFrame] = []
        pc = cfg["pilot"]
        self.pilot_day = cal.day_of(pc["start_date"])
        self.pilot_end = self.pilot_day + pc["window_days"]
        self.n_pilot = int(round(pc["n_subscribers"] * n / 200_000))
        self.pilot_ids = np.array([], dtype=np.int64)
        self.pilot_arm = np.array([], dtype=object)
        self.pilot_status = None
        from .calendar import EID_UL_FITR
        self.eid_blast_days = {cal.day_of(d) - 7 for d in EID_UL_FITR}

    def observe(self, day: int, rech_mask: np.ndarray):
        self.ring[day % 60] = rech_mask

    def _observable_active(self, day: int) -> np.ndarray:
        s, t = self.eng.s, self.eng.t
        return (t.activation_day <= day) & (
            (s.last_recharge >= day - 90) | (t.activation_day >= day - 90))

    def _log_exposure(self, ids, day, ctype, offers, randomised):
        eng = self.eng
        redeemed = np.zeros(len(ids), dtype=bool)
        for o in C.OFFER_IDS:
            m = offers == o
            if m.any():
                redeemed[m] = self.rng.random(m.sum()) < eng.redemption_prob(o, ids[m], day)
        self.rows.append(pd.DataFrame({
            "sub_id": ids.astype(np.int32),
            "exposure_date": self.cal.date(day),
            "campaign_id": f"{ctype}_{self.cal.date(day):%Y%m%d}",
            "campaign_type": ctype,
            "offer_id": offers,
            "randomised": randomised,
            "redeemed": redeemed,
        }))

    def _excluded(self, day: int) -> np.ndarray:
        ex = np.zeros(self.eng.n, dtype=bool)
        if self.pilot_day <= day < self.pilot_end:
            ex[self.pilot_ids] = True
        return ex

    def before_day(self, day: int):
        cal, eng, t = self.cal, self.eng, self.eng.t
        if day == self.pilot_day:
            self._run_pilot(day)
        if cal.date(day).day == 1 and day >= 60:
            self._bau_winback(day)
        if day in self.eid_blast_days:
            elig = np.flatnonzero(self._observable_active(day) & t.smart & ~self._excluded(day))
            ids = elig[self.rng.random(len(elig)) < 0.20]
            eng.apply_offer("bonus_data", ids, day)
            self._log_exposure(ids, day, "eid_blast", np.full(len(ids), "bonus_data", dtype=object), False)

    def _bau_winback(self, day: int):
        """Operator's existing rule: recharges in last 30 days < half of the 30 days before."""
        eng, t = self.eng, self.eng.t
        last30 = self.ring[[(day - k) % 60 for k in range(1, 31)]].sum(axis=0)
        prev30 = self.ring[[(day - k) % 60 for k in range(31, 61)]].sum(axis=0)
        elig = np.flatnonzero((prev30 >= 2) & (last30 < 0.5 * prev30) & ~self._excluded(day)
                              & (t.activation_day <= day))
        cap = int(0.05 * eng.n)
        if len(elig) > cap:
            elig = self.rng.choice(elig, cap, replace=False)
        u = self.rng.random(len(elig))
        tenure = day - t.activation_day[elig]
        offers = np.where(t.smart[elig] & (u < 0.35), "bonus_data",
                 np.where(u < 0.75, "recharge_cashback",
                 np.where(u < 0.92, "bundle_discount",
                 np.where(tenure > 730, "tenure_reward", "recharge_cashback")))).astype(object)
        for o in C.OFFER_IDS:
            m = offers == o
            if m.any():
                eng.apply_offer(o, elig[m], day)
        self._log_exposure(elig, day, "bau_winback", offers, False)

    def _run_pilot(self, day: int):
        eng = self.eng
        elig = np.flatnonzero(self._observable_active(day))
        ids = np.sort(self.rng.choice(elig, min(self.n_pilot, len(elig)), replace=False))
        arms = np.array(ARMS, dtype=object)[self.rng.permutation(len(ids)) % len(ARMS)]
        for o in C.OFFER_IDS:
            m = arms == o
            eng.apply_offer(o, ids[m], day)
        # control arm gets nothing (and no contact)
        self.pilot_ids, self.pilot_arm = ids, arms
        s = eng.s
        self.pilot_status = {"lost": s.declining[ids] | s.absorbed[ids]}
        self._log_exposure(ids, day, "pilot", np.where(arms == "control", "none", arms).astype(object), True)

    def exposures(self) -> pd.DataFrame:
        return pd.concat(self.rows, ignore_index=True)


def simulate(cfg: dict) -> dict:
    t0 = time.time()
    paths = cfg["paths"]
    for key in ("raw", "truth"):
        if paths[key].exists():
            shutil.rmtree(paths[key])
        paths[key].mkdir(parents=True)

    n = cfg["simulation"]["n_subscribers"]
    seed = cfg["seed"]
    cal = build_calendar(cfg)
    rng_pop = np.random.default_rng([seed, 1])
    rng_day = np.random.default_rng([seed, 2])
    rng_camp = np.random.default_rng([seed, 3])

    subscribers, traits = build_population(n, cfg, cal, rng_pop)
    from .engine import PARAMS
    scale = cfg["truth_world"]["effect_scale"]
    eng = Engine(traits, cal, params={"kappa": {k: v * scale for k, v in PARAMS["kappa"].items()}})
    camp = Campaigns(eng, cal, cfg, rng_camp)
    _log(f"population built: {n:,} subscribers")

    # ---------------- burn-in (state only, nothing written)
    for d in range(cal.first_day, 0):
        out = eng.step(d, rng_day, record=True)
        camp.observe(d, out["rech_mask"])
    pre_last = eng.s.last_recharge.copy()
    eng.s.cum_amount[:] = 0
    eng.s.n_recharge[:] = 0
    subscribers["last_revenue_date_pre_window"] = [
        cal.date(int(x)) if x > -10**5 else None for x in pre_last]

    # ---------------- observed window
    epoch = np.datetime64(cal.start, "D")
    W = {
        "recharges": MonthlyWriter(paths["raw"], "recharges", {
            "sub_id": pa.int32(), "recharge_date": pa.date32(), "amount_bdt": pa.int32(),
            "channel": ("dict", C.RECHARGE_CHANNELS), "is_pack_direct": pa.bool_()}),
        "pack_purchases": MonthlyWriter(paths["raw"], "pack_purchases", {
            "sub_id": pa.int32(), "purchase_date": pa.date32(),
            "pack_id": ("dict", C.PACKS["pack_id"].to_numpy()), "price_bdt": pa.int32()}),
        "daily_usage": MonthlyWriter(paths["raw"], "daily_usage", {
            "sub_id": pa.int32(), "usage_date": pa.date32(), "voice_min": pa.float32(),
            "data_mb": pa.float32(), "sms_count": pa.int16()}),
    }
    H_pilot = np.zeros(n)
    for d in range(0, cal.n_observed):
        camp.before_day(d)
        out = eng.step(d, rng_day, record=True)
        camp.observe(d, out["rech_mask"])
        if camp.pilot_day <= d < camp.pilot_end:
            H_pilot += out["h_ctrl"]
        month = f"{cal.date(d):%Y-%m}"
        date = epoch + np.timedelta64(d, "D")
        ri, amt, ch, direct = out["recharges"]
        W["recharges"].add(month, {"sub_id": ri, "recharge_date": np.full(len(ri), date),
                                   "amount_bdt": amt, "channel": ch, "is_pack_direct": direct})
        bi, bp = out["packs"]
        W["pack_purchases"].add(month, {"sub_id": bi, "purchase_date": np.full(len(bi), date),
                                        "pack_id": bp, "price_bdt": C.PACK_PRICE[bp]})
        ai, voice, data, sms = out["usage"]
        W["daily_usage"].add(month, {"sub_id": ai, "usage_date": np.full(len(ai), date),
                                     "voice_min": np.round(voice, 1), "data_mb": np.round(data, 1),
                                     "sms_count": sms})
        if d % 91 == 0:
            _log(f"observed day {d}/{cal.n_observed} ({cal.date(d)})")
    for w in W.values():
        w.flush()
    _log("observed window written: " + ", ".join(f"{k}={w.rows:,}" for k, w in W.items()))

    raw = paths["raw"]
    subscribers.to_parquet(raw / "subscribers.parquet", index=False)
    camp.exposures().to_parquet(raw / "offer_exposures.parquet", index=False)
    C.PACKS.to_parquet(raw / "catalog_packs.parquet", index=False)
    C.OFFERS.to_parquet(raw / "catalog_offers.parquet", index=False)
    spells = derive_inactivity(raw, cfg, cal)
    spells.to_parquet(raw / "inactivity_spells.parquet", index=False)

    # ---------------- ground truth
    truth = paths["truth"]
    end_day = cal.n_observed
    hidden = traits.hidden_frame()
    comps = eng.hazard_components(end_day - 1)
    for k, v in comps.items():
        hidden[k] = v
    hidden["true_churn_date"] = [cal.date(int(x)) if x > -10**5 else None for x in eng.s.true_churn_day]
    hidden["declining_at_end"] = eng.s.declining
    hidden["absorbed_at_end"] = eng.s.absorbed
    hidden.to_parquet(truth / "subscriber_truth.parquet", index=False)

    _write_pilot_truth(eng, camp, H_pilot, truth)
    _log("pilot truth written; simulating hidden future")
    _future_truth(eng, cal, cfg, truth)
    _log(f"done in {time.time() - t0:,.0f}s")
    return {k: w.rows for k, w in W.items()}


def _write_pilot_truth(eng: Engine, camp: Campaigns, H: np.ndarray, truth):
    ids, day = camp.pilot_ids, camp.pilot_day
    lost = camp.pilot_status["lost"]
    Hi = H[ids]
    p_ctrl = np.where(lost, 1.0, -np.expm1(-Hi))
    frames = []
    for o in C.OFFER_IDS:
        delta, r = eng.true_delta(o, ids, day)
        p_treat = np.where(lost, 1.0, -np.expm1(-np.exp(delta) * Hi))
        frames.append(pd.DataFrame({
            "sub_id": ids.astype(np.int32), "offer_id": o, "assigned_arm": camp.pilot_arm,
            "true_log_hazard_effect": delta, "responsiveness": r,
            "p_churn_90d_control": p_ctrl, "p_churn_90d_treated": p_treat,
            "true_uplift_retention": p_ctrl - p_treat,
        }))
    pd.concat(frames, ignore_index=True).to_parquet(truth / "pilot_truth.parquet", index=False)


def _future_truth(eng: Engine, cal, cfg: dict, truth):
    """Monte Carlo the hidden 12 months under each arm with common random numbers."""
    econ = cfg["economics"]
    margin = econ["net_revenue_ratio"] * econ["contribution_margin_on_net"]
    K = cfg["simulation"]["future_paths"]
    n, start = eng.n, cal.n_observed
    end_state = eng.s.copy()
    mean_amt = eng.mean_amount()
    exists0 = (eng.t.activation_day < start) & ~end_state.absorbed
    lost0 = end_state.declining.copy()
    alive_idx = np.flatnonzero(exists0)

    res = {a: {"rev365": np.zeros(n), "rev90": np.zeros(n), "p90": np.zeros(n)} for a in ARMS}
    realised = None
    deltas = {}
    for k in range(K):
        for a in ARMS:
            eng.s = end_state.copy()
            if a != "control":
                d_, _ = eng.apply_offer(a, alive_idx, start)
                deltas[a] = d_
            rng = np.random.default_rng([cfg["seed"], 7777, k])
            rev365, rev90, H = np.zeros(n), np.zeros(n), np.zeros(n)
            for d in range(start, start + cal.n_future):
                out = eng.step(d, rng, record=False)
                rev = out["rech_mask"] * mean_amt
                rev365 += rev
                if d < start + 90:
                    rev90 += rev
                    H += out["h"]
            p90 = np.where(lost0, 1.0, -np.expm1(-H))
            res[a]["rev365"] += rev365 / K
            res[a]["rev90"] += rev90 / K
            res[a]["p90"] += p90 / K
            if k == 0 and a == "control":
                realised = rev365.copy()
        _log(f"future path {k + 1}/{K} done")
    eng.s = end_state

    ctrl = res["control"]
    clv = pd.DataFrame({
        "sub_id": np.arange(n, dtype=np.int32),
        "alive_at_end": exists0,
        "declining_at_end": lost0,
        "true_clv_margin_12m": np.where(exists0, ctrl["rev365"] * margin, 0.0),
        "realised_margin_12m": np.where(exists0, realised * margin, 0.0),
        "true_gross_recharge_12m": np.where(exists0, ctrl["rev365"], 0.0),
        "true_p_churn_90d": np.where(exists0, ctrl["p90"], np.nan),
    })
    clv.to_parquet(truth / "clv_truth.parquet", index=False)

    lab = cfg["truth_labels"]
    frames = []
    for o in C.OFFER_IDS:
        tr = res[o]
        upl = ctrl["p90"] - tr["p90"]
        inc_margin = (tr["rev365"] - ctrl["rev365"]) * margin
        pc = ctrl["p90"]
        label = np.select(
            [upl <= lab["sleeping_dog_max_uplift"],
             upl >= lab["persuadable_min_uplift"],
             pc < lab["sure_thing_max_churn"],
             pc >= lab["lost_cause_min_churn"]],
            ["sleeping_dog", "persuadable", "sure_thing", "lost_cause"],
            default="low_responder",
        )
        df = pd.DataFrame({
            "sub_id": np.arange(n, dtype=np.int32), "offer_id": o,
            "true_log_hazard_effect": np.zeros(n), "p_churn_90d_control": pc,
            "p_churn_90d_treated": tr["p90"], "true_uplift_retention": upl,
            "true_incremental_margin_12m_before_cost": inc_margin, "response_group": label,
        })
        df.loc[alive_idx, "true_log_hazard_effect"] = deltas[o]
        frames.append(df[exists0])
    pd.concat(frames, ignore_index=True).to_parquet(truth / "treatment_truth.parquet", index=False)
