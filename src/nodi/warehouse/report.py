"""Phase 2 report: metric catalogue, governed KPI trends, DQ results (incl. fault injection)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from nodi.metrics import Metrics  # noqa: E402
from nodi.viz import ACCENT, ACCENT2, GRID, INK, MUTED, footer, style  # noqa: E402
from nodi.warehouse.build import connect  # noqa: E402
from nodi.warehouse.dq import run_dq, write_dq_report  # noqa: E402
from nodi.warehouse.faults import run_fault_injection  # noqa: E402


class DataQualityError(RuntimeError):
    pass


def phase2_report(cfg: dict, fault_injection: bool = True) -> dict:
    out = Path(cfg["paths"]["reports"]) / "phase2"
    out.mkdir(parents=True, exist_ok=True)
    con = connect(cfg)
    m = Metrics(con)

    # ---------------- metric catalogue
    cat = m.catalog()
    lines = ["# Metric catalogue", "", "Generated from `metrics.yml`. Every number in this project comes from one of these.", ""]
    for r in cat.itertuples():
        lines += [f"### `{r.metric}`: {r.label}", "",
                  f"- **Definition:** {r.definition}",
                  f"- **Owner:** {r.owner}  |  **Unit:** {r.unit}  |  **Model:** `{r.model}`"
                  + (f"  |  **Available from:** Phase {r.available_from_phase}" if r.available_from_phase != 2 else "")]
        if r.decision:
            lines.append(f"- **Decision:** {r.decision}")
        lines.append("")
    (out / "metrics_catalog.md").write_text("\n".join(lines), encoding="utf-8")

    # ---------------- KPIs
    kpi_names = ["active_base", "paying_subscribers", "net_revenue", "arpu", "arpu_active_base",
                 "churn_rate", "dormancy_rate", "recharge_frequency", "avg_recharge_size",
                 "data_gb_per_smartphone_user", "reactivations"]
    k = m.many(kpi_names)
    k.to_csv(out / "kpi_monthly.csv", index=False)
    pilot = m.get("pilot_retention_uplift", by=[]).merge(
        m.get("incremental_revenue", by=[])[["arm", "incremental_revenue"]], on="arm")
    pilot.to_csv(out / "pilot_preview.csv", index=False)

    x = pd.to_datetime(k.month_start)
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.4))
    ax = axes[0, 0]
    ax.bar(x, k.active_base / 1000, width=20, color="#99d5cf")
    style(ax, "Active base ('000)", "Revenue event in the prior 90 days")
    ax = axes[0, 1]
    ax.plot(x, k.arpu, color=ACCENT, lw=2, label="ARPU per paying sub (headline)")
    ax.plot(x, k.arpu_active_base, color=MUTED, lw=1.2, ls="--", label="ARPU per active sub")
    ax.set_ylim(k.arpu_active_base.min() * 0.85, k.arpu.max() * 1.08)
    ax.legend(fontsize=7, frameon=False, loc="upper left", ncol=2)
    style(ax, "ARPU, net ৳ / month", "Headline = per paying subscriber (decision 2.1)")
    ax = axes[1, 0]
    ax.plot(x, k.churn_rate * 100, color=ACCENT2, lw=2, marker="o", ms=3, label="Churn (90 days silent)")
    ax.plot(x, k.dormancy_rate * 100, color=MUTED, lw=1.2, ls="--", label="Dormancy (30 days silent)")
    ax.set_ylim(0, None)
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    style(ax, "Churn and early-warning dormancy, % of active base")
    ax = axes[1, 1]
    ax.plot(x, k.recharge_frequency, color=ACCENT, lw=2)
    ax.set_ylim(0, None)
    style(ax, "Recharges per paying subscriber / month")
    for a in axes.flat:
        a.tick_params(axis="x", labelrotation=0)
        a.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b\n%y"))
    fig.suptitle("Nodi Telecom base health: every line is a metrics.yml definition", x=0.01, ha="left",
                 fontsize=12, fontweight="bold", color=INK)
    footer(fig)
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    fig.savefig(out / "kpi_overview.png", dpi=160)
    plt.close(fig)

    # ---------------- data quality
    dq = run_dq(con, cfg)
    con.close()
    path = write_dq_report(dq, out)
    if fault_injection:
        fi = run_fault_injection(cfg)
        fi.to_csv(out / "fault_injection.csv", index=False)
        extra = ["", "## Do the checks actually fire? (fault injection)", "",
                 "Each fault was planted in a fresh copy of the warehouse and the full suite re-run.", "",
                 "| Planted fault | Caught | Checks that fired |", "|---|---|---|"]
        extra += [f"| {r.fault} | {'yes' if r.caught else '**NO**'} | {r.checks_fired} |" for r in fi.itertuples()]
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(extra) + "\n")

    def avg(col):
        return float(k[col].mean())

    summary = {
        "dq_checks_passed": f"{(dq.status == 'PASS').sum()}/{len(dq)}",
        "arpu_paying_bdt": avg("arpu"),
        "arpu_active_bdt": avg("arpu_active_base"),
        "churn_rate": avg("churn_rate"),
        "dormancy_rate": avg("dormancy_rate"),
        "recharge_frequency": avg("recharge_frequency"),
        "active_base_end": int(k.active_base.iloc[-1]),
    }
    lines = ["# Phase 2 summary (synthetic data)", "",
             *[f"- **{a}**: {b:,.3f}" if isinstance(b, float) else f"- **{a}**: {b}" for a, b in summary.items()],
             "", "## Monthly KPIs (metrics.yml)", "", k.round(3).to_string(index=False),
             "", "## Randomised pilot, preview (full analysis in Phase 5)", "", pilot.round(4).to_string(index=False)]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    if (dq.status == "FAIL").any():
        raise DataQualityError(f"DQ errors: {dq[dq.status == 'FAIL'].name.tolist()} (see {path})")
    return summary
