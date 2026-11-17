import plotly.graph_objects as go
import streamlit as st

import lib

lib.page_setup("Segment explorer")
h = lib.headline()
scale = h["operator_scale"]
seg = lib.table("segments").sort_values("segment_id").reset_index(drop=True)
spec = {s["id"]: s for s in lib.segments_spec()["segments"]}

st.markdown('<p class="nodi-muted">Value-at-risk band (churn probability × value if retained: top 10% / next 20% / rest) '
            '× churn stage (gone quiet / new / slipping / steady). Defined in segments.yml.</p>',
            unsafe_allow_html=True)

fig = go.Figure()
labels = [f"{i}. {n}" for i, n in zip(seg.segment_id, seg.segment)][::-1]
fig.add_bar(y=labels, x=(seg.share_of_base * 100)[::-1], orientation="h", name="% of active subscribers",
            marker_color="#d1d5db")
fig.add_bar(y=labels, x=(seg.share_of_margin_at_risk * 100)[::-1], orientation="h", name="% of margin at risk",
            marker_color=lib.TEAL, text=[f"{x:.0%}" for x in seg.share_of_margin_at_risk[::-1]], textposition="outside")
fig.update_xaxes(title="%")
st.plotly_chart(lib.plotly_layout(fig, height=420, barmode="group"), width="stretch")

show = seg.assign(
    subscribers=(seg.scored_subscribers * scale).map(lib.people),
    margin_at_risk=(seg.revenue_at_risk * scale).map(lib.bdt),
    per_subscriber=seg.margin_at_risk_per_sub.map(lambda x: f"৳{x:,.0f}"),
    churn=seg.avg_churn_prob.map(lambda x: f"{x:.0%}"),
    in_plan=(seg.plan_targeted / seg.scored_subscribers).map(lambda x: f"{x:.0%}"),
    stance=seg.stance.map(lib.STANCE_LABEL),
)[["segment_id", "segment", "subscribers", "churn", "margin_at_risk", "per_subscriber", "stance", "in_plan"]]
st.dataframe(show.rename(columns={"segment_id": "#", "churn": "90-day churn", "margin_at_risk": "Margin at risk",
                                  "per_subscriber": "At risk per sub", "in_plan": "Gets an offer (৳1 cr plan)"}),
             hide_index=True, width="stretch")

st.divider()
choice = st.selectbox("Look inside a segment", seg.segment_id,
                      format_func=lambda i: f"{i}. {seg.set_index('segment_id').segment[i]}")
r = seg.set_index("segment_id").loc[choice]
s = spec[choice]
c = st.columns(4)
c[0].metric("Subscribers", lib.people_short(r.scored_subscribers * scale), f"{r.share_of_base:.0%} of base", delta_color="off")
c[1].metric("Margin at risk (12m)", lib.bdt_short(r.revenue_at_risk * scale), f"{r.share_of_margin_at_risk:.0%} of total", delta_color="off")
c[2].metric("Avg 90-day churn probability", f"{r.avg_churn_prob:.0%}")
c[3].metric("Avg predicted 12-month CLV", f"৳{r.clv_12m:,.0f}")
st.markdown(f"**Stance: {lib.STANCE_LABEL[s['stance']]}.** {' '.join(s['action'].split())}")
st.markdown(
    f"- Smartphone share {r.smartphone_share:.0%} · median tenure {r.median_tenure_months:.0f} months · "
    f"activation-kiosk joiners {r.kiosk_share:.0%} · over-represented in **{r.over_indexed_division}** "
    f"({r.division_index:.2f}× its base share)\n"
    f"- Under the ৳1 crore plan: **{r.plan_targeted / r.scored_subscribers:.0%}** get an offer "
    f"({lib.people(r.plan_targeted * scale)}), spend {lib.bdt(r.plan_spend * scale)}, expected net margin "
    f"{lib.bdt(r.plan_net * scale)}.")
if s["stance"] == "no_spend":
    st.info("Guardrail (decision B5.4): this segment never receives paid offers; it gets free pack reminders only.")
if st.button("See this segment's messages in the Campaign studio", icon=":material/sms:"):
    st.session_state["studio_segment"] = int(choice)
    st.switch_page("pages/studio.py")
