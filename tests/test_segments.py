"""Phase 4 tests: segmentation rules, coverage, and reconciliation to governed metrics."""
import copy

import numpy as np
import pandas as pd
import pytest

from nodi.metrics import Metrics
from nodi.segments.build import assign, load_spec, segment_profile
from nodi.warehouse.build import connect


def test_spec_maps_every_cell_exactly_once(tmp_path):
    spec = load_spec()
    assert len(spec["segments"]) == 8
    bad = copy.deepcopy(spec)
    bad["segments"][0]["cells"].append(["Low", "steady"])  # duplicate a cell
    import yaml
    p = tmp_path / "bad.yml"
    p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_spec(p)


def test_stage_precedence_and_bands():
    spec = load_spec()
    n = 100
    d = pd.DataFrame({
        "value_if_retained_12m": np.linspace(100, 2000, n), "churn_prob_90d": np.full(n, 0.2),
        "days_since_last_event": 1, "tenure_months": 30, "active_days_30": 20, "active_days_prev30": 20,
        "rech_30": 4, "rech_prev30": 4,
    })
    d.loc[0, ["days_since_last_event", "tenure_months"]] = [30, 2]       # quiet AND new -> quiet wins
    d.loc[1, "tenure_months"] = 2                                        # new
    d.loc[2, ["active_days_30", "tenure_months"]] = [5, 2]               # new AND slipping -> new wins
    d.loc[3, "active_days_30"] = 5                                       # slipping on activity
    d.loc[4, ["rech_30", "rech_prev30"]] = [1, 4]                        # slipping on recharges
    out = assign(d, spec)
    assert out.stage.iloc[:5].tolist() == ["gone_quiet", "new", "new", "slipping", "slipping"]
    assert out.stage.iloc[5:].eq("steady").all()
    assert (out.var_band.value_counts() == pd.Series({"Low": 70, "Medium": 20, "High": 10})).all()
    assert out.loc[out.value_if_retained_12m.idxmax(), "var_band"] == "High"


def test_every_scored_subscriber_has_one_segment(segmented):
    con = connect(segmented)
    n_scores = con.execute("SELECT COUNT(*) FROM ml_scores").fetchone()[0]
    seg = con.execute("SELECT * FROM ml_segments").df()
    con.close()
    assert len(seg) == n_scores and seg.sub_id.is_unique
    assert seg.segment_id.between(1, 8).all()
    share = seg.var_band.value_counts(normalize=True)
    assert share["High"] == pytest.approx(0.10, abs=0.005)
    assert share["Medium"] == pytest.approx(0.20, abs=0.005)


def test_segment_profile_reconciles_to_metrics(segmented):
    p = segment_profile(segmented)
    con = connect(segmented)
    m = Metrics(con)
    total_risk = m.get("revenue_at_risk", by=[])["revenue_at_risk"].iloc[0]
    total_n = m.get("scored_subscribers", by=[])["scored_subscribers"].iloc[0]
    con.close()
    assert p.revenue_at_risk.sum() == pytest.approx(total_risk)
    assert p.scored_subscribers.sum() == total_n
    assert p.share_of_margin_at_risk.sum() == pytest.approx(1.0)
    assert p.action.str.len().min() > 20


def test_segment_truth_validation_runs(segmented):
    from nodi.validate.phase4 import phase4_validation
    s = phase4_validation(segmented)
    assert s.subs.sum() > 0
    assert s.true_mar_share.sum() == pytest.approx(1.0)
