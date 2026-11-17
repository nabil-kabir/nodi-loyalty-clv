import plotly.graph_objects as go
import streamlit as st

import lib

lib.page_setup("Budget allocator")
h = lib.headline()
scale = h["operator_scale"]

c1, c2 = st.columns([2, 1])
budget_cr = c1.slider("Quarterly retention budget (৳ crore)", 0.0, h["slider_max_bdt"] / 1e7,
                      h["budget_bdt"] / 1e7, 0.05, format="৳%.2f cr")
view = c2.radio("Cost offers at", ["network", "face"], horizontal=True,
                format_func=lambda v: "Network cost" if v == "network" else "Face value",
                help="Network cost: what Nodi really gives up (2 GB of data costs ~৳10). Face value: the retail "
                     "price of the data and minutes. Decision 0.5 uses network cost.")
B = budget_cr * 1e7
opt = lib.optimised(B, view)
bl, rk = lib.baseline("blanket", B), lib.baseline("highest_churn_risk", B)

c = st.columns(4)
c[0].metric("Spent", lib.bdt_short(opt["spend"]),
            f"{lib.bdt_short(B - opt['spend'])} unspent" if B - opt["spend"] > 1e5 else None, delta_color="off")
c[1].metric("Subscribers selected", lib.people_short(opt["targeted"]))
c[2].metric("Expected net margin (12m)", lib.bdt_short(opt["net"]),
            f"{lib.bdt_short(opt['net'] - bl['net'])} vs blanket" if B > 0 else None)
c[3].metric("Net per ৳1 spent", f"৳{opt['net'] / opt['spend']:.2f}" if opt["spend"] else "–")
if B > h["max_profitable_spend_bdt"]:
    st.info(f"Beyond {lib.bdt(h['max_profitable_spend_bdt'])} a quarter no remaining offer is expected to pay back, "
            "so the optimiser stops spending. Returning the rest is the right answer.")

# frontier
curve = lib.frontier(view)
fig = go.Figure()
for name, col, dash in [("Optimised", lib.TEAL, "solid"), ("Blanket cashback", "#6b7280", "dash"),
                        ("Cashback to highest churn risk", lib.AMBER, "dot")]:
    fig.add_scatter(x=curve.budget / 1e7, y=curve[name] / 1e7, name=name, mode="lines",
                    line=dict(color=col, dash=dash, width=3 if name == "Optimised" else 2))
fig.add_vline(x=budget_cr, line_color="#9ca3af")
fig.add_scatter(x=[budget_cr], y=[opt["net"] / 1e7], mode="markers", marker=dict(size=11, color=lib.TEAL),
                showlegend=False)
fig.update_xaxes(title="Quarterly budget (৳ crore)")
fig.update_yaxes(title="Expected net 12-month margin (৳ crore)")
st.plotly_chart(lib.plotly_layout(fig, height=380), width="stretch")
st.caption(f"At {lib.bdt(B)}: optimised {lib.bdt(opt['net'])} · blanket cashback {lib.bdt(bl['net'])} · "
           f"cashback to highest churn risk {lib.bdt(rk['net'])}. Model estimates from pilot-trained, calibrated uplift.")

# who gets what
st.subheader("Who gets what")
alloc = opt["allocation"]
if len(alloc):
    seg_names = lib.table("segments").set_index("segment_id").segment
    a = alloc.merge(lib.table("subscriber_segment"), on="sub_id")
    piv = a.groupby(["segment_id", "offer_id"], observed=True).size().unstack(fill_value=0) * scale
    fig = go.Figure()
    for o in [x for x in lib.OFFER_COLOR if x in piv.columns]:
        fig.add_bar(y=[f"{i}. {seg_names[i]}" for i in piv.index][::-1], x=piv[o][::-1], orientation="h",
                    name=lib.OFFER_LABEL[o], marker_color=lib.OFFER_COLOR[o])
    fig.update_xaxes(title="Subscribers receiving an offer")
    st.plotly_chart(lib.plotly_layout(fig, height=360, barmode="stack"), width="stretch")
    st.caption("Segments 6 and 7 never appear: guardrail B5.4 excludes no-spend segments from every plan.")
else:
    st.write("No offers at this budget.")

# proving it
st.subheader("How big a holdout?")
share = st.slider("Holdout share of the selected list (%)", 1, 20, int(round(h["holdout_share"] * 100)), 1,
                  format="%d%%",
                  help="Selected subscribers randomly kept back with no offer: the comparison group for the CMO metric.") / 100
st.caption(f"Decision B5.2 is {h['holdout_share']:.0%}.")
n_h = opt["targeted"] * share
if opt["targeted"]:
    gross = (opt["net"] + opt["spend"]) / opt["targeted"]
    m = lib.mde(h["sigma_margin_90d"], opt["targeted"] - n_h, n_h)
    c = st.columns(3)
    c[0].metric("Held back", lib.people_short(n_h))
    c[1].metric("Smallest effect we can detect", f"৳{m:.1f} per subscriber", help="80% power, 5% two-sided")
    c[2].metric("Expected margin forgone", lib.bdt_short(n_h / opt["targeted"] * opt["net"]))
    st.caption(f"The plan expects about ৳{gross:.0f} of extra 90-day margin per treated subscriber, "
               f"{'comfortably above' if gross > 2 * m else 'close to'} what the holdout can detect.")
