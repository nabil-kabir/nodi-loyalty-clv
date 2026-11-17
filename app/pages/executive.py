import plotly.graph_objects as go
import streamlit as st

import lib

lib.page_setup("Where Nodi's ৳1 crore retention budget should go")
h, v = lib.headline(), lib.validation()
scale, b, p = h["operator_scale"], h["base"], h["plans"]
opt, blanket, risk = p["optimised"], p["blanket"], p["highest_churn_risk"]
holdout_n = opt["targeted"] * h["holdout_share"]
gross_per = (opt["expected_net_margin_bdt"] + opt["spend_bdt"]) / opt["targeted"]
mde = lib.mde(h["sigma_margin_90d"], opt["targeted"] - holdout_n, holdout_n)

st.markdown(
    f'<div class="nodi-callout"><b>Recommendation.</b> Spend the {lib.bdt(h["budget_bdt"])} on '
    f'<b>2 GB bonus data for {lib.people(opt["targeted"])} subscribers</b> the pilot-trained uplift models '
    f'expect to respond, not on the riskiest customers. Expected return: <b>{lib.bdt(opt["expected_net_margin_bdt"])} '
    f'of 12-month margin after offer cost (৳{opt["roi"]:.2f} per ৳1)</b>, about '
    f'{opt["expected_net_margin_bdt"] / blanket["expected_net_margin_bdt"]:.1f}× a blanket cashback. '
    f'A randomised {h["holdout_share"]:.0%} holdout proves it within one quarter.</div>',
    unsafe_allow_html=True)

st.subheader("Base health")
c = st.columns(4)
c[0].metric("Active subscribers", lib.people_short(b["active_base_end"] * scale), help="Revenue event in the last 90 days (metrics.yml: active_base)")
c[1].metric("ARPU, net / month", f"৳{b['arpu_last6']:.0f}", help=f"Per paying subscriber, last 6 months (metrics.yml: arpu). Per active subscriber: ৳{b['arpu_active_last6']:.0f}")
c[2].metric("Monthly churn", lib.pct(b["churn_rate_last6"]), help="90 days without a revenue event, last 6 months (metrics.yml: churn_rate)")
c[3].metric("Margin at risk, 12m", lib.bdt_short(b["revenue_at_risk"] * scale), help="Σ churn probability × value if retained (metrics.yml: revenue_at_risk)")

st.subheader(f"The plan at {lib.bdt(h['budget_bdt'])}")
c = st.columns(4)
c[0].metric("Subscribers selected", lib.people_short(opt["targeted"]), help=f"{lib.people(opt['targeted'])}, including a {h['holdout_share']:.0%} random holdout who get nothing")
c[1].metric("Offer spend", lib.bdt_short(opt["spend_bdt"]), help=f"Network cost. At face value of the data given: {lib.bdt(opt['spend_face_bdt'])}")
c[2].metric("Expected net margin", lib.bdt_short(opt["expected_net_margin_bdt"]), help="12 months, after offer cost (metrics.yml: expected_net_margin)")
c[3].metric("Net per ৳1 spent", f"৳{opt['roi']:.2f}", f"vs ৳{blanket['roi']:.2f} blanket", delta_color="normal")

show_truth = st.toggle("Show what really happened (planted truth)", value=False,
                       help="The synthetic world has a hidden counterfactual. Models never saw it; this is validation only.")
names = ["Optimised plan", "Blanket cashback", "Cashback to highest churn risk"][::-1]
model_vals = [opt["expected_net_margin_bdt"], blanket["expected_net_margin_bdt"], risk["expected_net_margin_bdt"]][::-1]
fig = go.Figure(go.Bar(y=names, x=[x / 1e7 for x in model_vals], name="Model estimate", orientation="h",
                       marker_color=lib.TEAL, text=[lib.bdt(x) for x in model_vals], textposition="outside"))
t = v.get("plans_vs_truth") or {}
if show_truth and t:
    tv = [t["optimised"]["truth"], t["blanket"]["truth"], t["highest_churn_risk"]["truth"]][::-1]
    fig.add_bar(y=names, x=[x / 1e7 for x in tv], name="Planted truth", orientation="h",
                marker_color=lib.TEAL_LIGHT, text=[lib.bdt(x) for x in tv], textposition="outside")
fig.add_vline(x=0, line_color="#9ca3af")
fig.update_xaxes(title="Expected net 12-month margin at ৳1 crore (৳ crore)")
st.plotly_chart(lib.plotly_layout(fig, height=300 if not show_truth else 380, barmode="group"), width="stretch")

left, right = st.columns(2)
with left:
    st.markdown("#### Why this plan")
    st.markdown(
        "- **Offers buy spend, not loyalty.** In the randomised pilot every offer moved retention by under "
        "1 percentage point. The measurable payoff is extra top-ups.\n"
        "- **The riskiest customers are mostly already gone.** Sending cashback to the highest churn risk "
        "barely pays in the model and *loses* money in the truth.\n"
        "- **Cheap data beats cash** when costed at network cost (decision 0.5). At face value the plan would "
        "switch to cashback; see the Budget allocator.\n"
        "- **Bundle discounts lose ~৳26 per head**: the discount goes mostly to people who'd buy anyway.")
with right:
    st.markdown("#### How we prove it")
    st.markdown(
        f"**Success metric for the CMO:** {h['cmo_metric']}\n\n"
        f"A {h['holdout_share']:.0%} holdout is {lib.people(holdout_n)} subscribers. It detects an effect of "
        f"**৳{mde:.1f} per subscriber**; the plan expects about **৳{gross_per:.0f}**.")

with st.expander("How do we know the models work? (validation against the planted truth)"):
    cb, cv, dr = v.get("churn_backtest") or {}, v.get("clv_vs_truth") or {}, v.get("drivers") or {}
    lg = cb.get("lightgbm", {})
    rule = cb.get("bau_rule", {})
    st.markdown(
        f"- **Churn model, out-of-time test:** AUC {lg.get('auc', float('nan')):.2f}; the riskiest 20% hold "
        f"{lg.get('capture_top20', float('nan')):.0%} of next quarter's churners. Contacting as many people as "
        f"today's win-back rule, it reaches {rule.get('model_recall_same_volume', float('nan')):.0%} of churners "
        f"vs {rule.get('recall', float('nan')):.0%}.\n"
        f"- **CLV (BG/NBD + Gamma-Gamma) vs true 12-month margin:** rank correlation "
        f"{cv.get('bgnbd_gg', {}).get('spearman', float('nan')):.2f} vs {cv.get('run_rate', {}).get('spearman', float('nan')):.2f} "
        f"for the run-rate baseline.\n"
        f"- **Planted churn drivers recovered:** "
        f"{sum(r['recovered'] == 'yes' for r in dr.get('table', []))} of {len(dr.get('table', []))}; "
        f"weak-network divisions rank exactly as planted.\n"
        f"- **Plans at ৳1 crore, model vs truth:** "
        + "; ".join(f"{k.replace('_', ' ')} {lib.bdt(x.get('model')) if x.get('model') is not None else '–'} → "
                    f"{lib.bdt(x['truth'])}" for k, x in (v.get("plans_vs_truth") or {}).items()))
    st.caption("Raw, uncalibrated uplift scores claim a huge return but truly earn little: "
               "that failure mode is why the plan uses calibrated, shrunk effects (DECISIONS 5.2-5.4).")

st.caption("Every number traces to metrics.yml or ASSUMPTIONS.md. Code, decisions and assumptions: "
           "github.com/nabil-kabir/nodi-loyalty-clv")
