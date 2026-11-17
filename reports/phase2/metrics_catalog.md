# Metric catalogue

Generated from `metrics.yml`. Every number in this project comes from one of these.

### `active_base`: Active base

- **Definition:** Subscribers with at least one revenue event in the 90 days before the first day of the month. A revenue event is a recharge (including packs bought directly via MFS/app); activation counts as the first event. This is the denominator for churn, so active base and churners reconcile.
- **Owner:** BI & Analytics  |  **Unit:** subscribers  |  **Model:** `mart_subscriber_month`
- **Decision:** DECISIONS 2.2: 90-day revenue-active (you, 2026-11-17)

### `paying_subscribers`: Paying subscribers

- **Definition:** Subscribers with at least one recharge in the calendar month.
- **Owner:** BI & Analytics  |  **Unit:** subscribers  |  **Model:** `mart_subscriber_month`

### `new_subscribers`: New subscribers

- **Definition:** Subscribers whose first-ever revenue event (activation) falls in the month.
- **Owner:** BI & Analytics  |  **Unit:** subscribers  |  **Model:** `mart_subscriber_month`

### `gross_recharge`: Gross recharge

- **Definition:** Total value of recharges in the month as paid by customers, including VAT, SD and surcharge.
- **Owner:** Finance: Revenue Assurance  |  **Unit:** bdt  |  **Model:** `mart_subscriber_month`

### `net_revenue`: Net revenue

- **Definition:** Gross recharge after VAT, supplementary duty and surcharge (gross x 0.72, ASSUMPTIONS D01). Recharge is used as the revenue proxy; balance consumption timing is not modelled.
- **Owner:** Finance: Revenue Assurance  |  **Unit:** bdt  |  **Model:** `mart_subscriber_month`

### `contribution_margin`: Contribution margin

- **Definition:** Net revenue after BTRC revenue share, SOF, channel commission and variable network cost (net x 0.78, ASSUMPTIONS D02). This is the currency for CLV and offer ROI.
- **Owner:** Finance: Revenue Assurance  |  **Unit:** bdt  |  **Model:** `mart_subscriber_month`

### `arpu`: ARPU (per paying subscriber)

- **Definition:** HEADLINE ARPU. Monthly net revenue divided by subscribers who recharged in that month (sometimes called ARPPU). Steadier than active-base ARPU, but NOT directly comparable with operators' published ARPU, which is per active subscriber (use arpu_active_base for that).
- **Owner:** Finance: Revenue Assurance  |  **Unit:** bdt  |  **Model:** `mart_subscriber_month`
- **Decision:** DECISIONS 2.1: ARPPU as headline (you, 2026-11-17)

### `arpu_active_base`: ARPU (per active subscriber)

- **Definition:** Secondary ARPU: monthly net revenue divided by the 90-day active base at the start of the month. Use only for comparison with published operator ARPU (Robi Q1 2024: Tk140).
- **Owner:** Finance: Revenue Assurance  |  **Unit:** bdt  |  **Model:** `mart_subscriber_month`

### `recharge_frequency`: Recharges per paying subscriber

- **Definition:** Average number of recharges in the month per subscriber who recharged at least once.
- **Owner:** CVM & Loyalty (Head of CVM)  |  **Unit:** per_month  |  **Model:** `mart_subscriber_month`

### `avg_recharge_size`: Average recharge

- **Definition:** Average gross value of a single recharge.
- **Owner:** CVM & Loyalty (Head of CVM)  |  **Unit:** bdt  |  **Model:** `mart_subscriber_month`

### `recharge_count`: Recharge transactions

- **Definition:** Number of recharge transactions. Transaction-level, so it can be sliced by date, amount (gross_bdt) or channel.
- **Owner:** BI & Analytics  |  **Unit:** count  |  **Model:** `mart_recharge`

### `recharge_value`: Recharge value (gross)

- **Definition:** Gross value of recharge transactions. Transaction-level twin of gross_recharge, for daily or per-denomination views; the two reconcile (DQ check snapshot_vs_fact_revenue).
- **Owner:** Finance: Revenue Assurance  |  **Unit:** bdt  |  **Model:** `mart_recharge`

### `mfs_recharge_share`: MFS share of recharges

- **Definition:** Share of recharge transactions made through mobile financial services (bKash-style wallets).
- **Owner:** CVM & Loyalty (Head of CVM)  |  **Unit:** pct  |  **Model:** `mart_recharge`

### `data_gb_per_smartphone_user`: Data per smartphone user

- **Definition:** Average monthly mobile data (GB) per smartphone subscriber with any usage in the month.
- **Owner:** CVM & Loyalty (Head of CVM)  |  **Unit:** gb  |  **Model:** `mart_subscriber_month`

### `churners`: Churners

- **Definition:** Subscribers who reach 90 consecutive days without a revenue event during the month (churn date = last revenue event + 90 days). The window is config churn.churn_days.
- **Owner:** CVM & Loyalty (Head of CVM)  |  **Unit:** subscribers  |  **Model:** `mart_subscriber_month`

### `churn_rate`: Monthly churn rate

- **Definition:** Churners in the month divided by the active base at the start of the month.
- **Owner:** CVM & Loyalty (Head of CVM)  |  **Unit:** pct  |  **Model:** `mart_subscriber_month`

### `dormancy_rate`: Dormancy rate (early warning)

- **Definition:** Subscribers reaching 30 days without a revenue event during the month, as a share of the active base. Roughly 1 in 3 dormant subscribers goes on to churn.
- **Owner:** CVM & Loyalty (Head of CVM)  |  **Unit:** pct  |  **Model:** `mart_subscriber_month`

### `reactivations`: Reactivations

- **Definition:** Previously churned subscribers (90+ days silent) who recharge again in the month.
- **Owner:** CVM & Loyalty (Head of CVM)  |  **Unit:** subscribers  |  **Model:** `mart_subscriber_month`

### `pilot_retention_uplift`: Retention uplift vs control

- **Definition:** Retention rate of an offer arm minus the randomised control arm in the Jan-2026 pilot. Churned = went silent before the 90-day pilot window ended and stayed silent 90 days.
- **Owner:** Data Science  |  **Unit:** pp  |  **Model:** `mart_pilot_outcome`

### `incremental_revenue`: Incremental net revenue

- **Definition:** (Average 90-day net revenue per treated subscriber minus the same for control) x treated subscribers. Only randomised comparisons count as incremental, never pre/post or vs. untargeted.
- **Owner:** Data Science  |  **Unit:** bdt  |  **Model:** `mart_pilot_outcome`

### `incremental_margin_before_cost`: Incremental margin (before offer cost)

- **Definition:** Incremental contribution margin within the 90-day window, before deducting what the offer cost. Offer cost is added in Phase 5; the long-term value of retained subscribers comes from CLV.
- **Owner:** Data Science  |  **Unit:** bdt  |  **Model:** `mart_pilot_outcome`

### `clv_12m`: Predicted 12-month CLV

- **Definition:** Model-predicted contribution margin a subscriber will generate over the next 12 months (BG/NBD + Gamma-Gamma, Phase 3). Shown as an average when aggregated.
- **Owner:** Data Science  |  **Unit:** bdt  |  **Model:** `scores_subscriber`  |  **Available from:** Phase 3

### `revenue_at_risk`: Margin at risk (12m)

- **Definition:** Sum over subscribers of 90-day churn probability x the 12-month margin they would bring if they stay (BG/NBD + Gamma-Gamma, conditional on being alive). This is the value the retention budget is trying to protect, and the ranking used for value-at-risk bands (DECISIONS B3.1, 4.2). Not CLV x churn probability: CLV already discounts for leaving, so that would double-count.
- **Owner:** CVM & Loyalty (Head of CVM)  |  **Unit:** bdt  |  **Model:** `scores_subscriber`  |  **Available from:** Phase 3

### `value_if_retained`: Value if retained (12m)

- **Definition:** Average predicted 12-month contribution margin a subscriber brings if they do not churn. This is what a successful save is worth, before offer cost.
- **Owner:** Data Science  |  **Unit:** bdt  |  **Model:** `scores_subscriber`  |  **Available from:** Phase 3

### `targeted_subscribers`: Subscribers targeted

- **Definition:** Subscribers who receive an offer under the optimised plan (excludes the randomised holdout).
- **Owner:** CVM & Loyalty (Head of CVM)  |  **Unit:** subscribers  |  **Model:** `mart_plan`  |  **Available from:** Phase 5

### `holdout_subscribers`: Holdout subscribers

- **Definition:** Subscribers the optimiser selected but who are randomly held back (no offer) to measure true incremental impact. Share set by config budget.holdout_share (DECISIONS B5.2).
- **Owner:** Data Science  |  **Unit:** subscribers  |  **Model:** `mart_plan`  |  **Available from:** Phase 5

### `planned_spend`: Planned offer spend (network cost)

- **Definition:** Expected cost of the plan: SMS contact cost for everyone targeted plus predicted redemption x cost per redeemer, with data valued at network cost and cash at face (decision 0.5, ASSUMPTIONS F).
- **Owner:** Finance: Revenue Assurance  |  **Unit:** bdt  |  **Model:** `mart_plan`  |  **Available from:** Phase 5

### `planned_spend_face`: Planned offer spend (face value)

- **Definition:** Same plan costed at the retail (face) value of data and minutes. A sensitivity view only.
- **Owner:** Finance: Revenue Assurance  |  **Unit:** bdt  |  **Model:** `mart_plan`  |  **Available from:** Phase 5

### `expected_net_margin`: Expected incremental margin, net of cost

- **Definition:** Expected 12-month incremental contribution margin from the plan, minus expected offer cost. Uplift comes from models trained only on the randomised pilot, calibrated and shrunk (DECISIONS 5.x).
- **Owner:** Data Science  |  **Unit:** bdt  |  **Model:** `mart_plan`  |  **Available from:** Phase 5

### `plan_roi`: Net margin per ৳ spent

- **Definition:** Expected net incremental margin returned per ৳1 of offer cost.
- **Owner:** Finance: Revenue Assurance  |  **Unit:** ratio  |  **Model:** `mart_plan`  |  **Available from:** Phase 5

### `net_revenue_at_risk`: Net revenue at risk (12m)

- **Definition:** revenue_at_risk expressed as net revenue instead of contribution margin (divided by the contribution margin ratio, ASSUMPTIONS D02). Use when Finance asks "how much revenue".
- **Owner:** Finance: Revenue Assurance  |  **Unit:** bdt  |  **Model:** `scores_subscriber`  |  **Available from:** Phase 4

### `scored_subscribers`: Scored subscribers

- **Definition:** Active subscribers (90-day revenue-active) scored by the churn and CLV models on the score date.
- **Owner:** Data Science  |  **Unit:** subscribers  |  **Model:** `scores_subscriber`  |  **Available from:** Phase 3

### `expected_churners`: Expected churners (90 days)

- **Definition:** Sum of calibrated 90-day churn probabilities, i.e. how many scored subscribers we expect to lose.
- **Owner:** Data Science  |  **Unit:** subscribers  |  **Model:** `scores_subscriber`  |  **Available from:** Phase 3
