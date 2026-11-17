# DECISIONS — log of choices and trade-offs

This file separates **business judgements** (yours to own) from **technical choices** (mine, open to challenge). When a decision changes later, the original entry stays and a new one is added.

---

## Phase 0: Scoping (2026-11-17)

| # | Decision | Who | Why / trade-off |
|---|---|---|---|
| 0.1 | Public repo + Streamlit Community Cloud | Business (you) | A live link gets clicked; a repo gets skimmed. The cost is that the app must run on small, precomputed outputs. |
| 0.2 | Daily usage for all subscribers | Business (you) | Most realistic. The cost is a slower full build (timed below). A 20k `--sample` mode keeps development fast. |
| 0.3 | CLV = 12-month forward contribution margin | Business (you) | Matches the "incremental margin" objective. 12 months fits prepaid churn speed. |
| 0.4 | Churn = 90 days without a revenue event; dormant = 30 days | Business (you) | Aligns with the ITU-style 90-day active definition. BTRC wording not yet verified (see ASSUMPTIONS A01). |
| 0.5 | Offer cost: data at marginal network cost; cashback at cash value | Business (you) | This is the real economics. The app will also show the face-value view. |

---

## Phase 1: Synthetic subscriber universe (2026-11-17)

### Technical choices

**1.1 Stay on Python 3.14**
All pinned dependencies install cleanly on 3.14.8 (`requirements.txt`). `pyproject.toml` declares 3.11+.

**1.2 Latent-trait simulation, not column-by-column sampling**
Each subscriber has hidden traits (engagement, price sensitivity, data affinity, competitor pull, network quality, contact fatigue, base hazard). Observable behaviour is generated from them day by day. That lets the models later *recover* drivers instead of reading them off a column. It also makes "the model found the truth" a meaningful claim.

**1.3 Churn is a decision followed by a fade-out**
When the hidden hazard fires, the subscriber's recharging and usage fade over 14–45 days before going silent (true churn). This creates realistic leading indicators (declining recharge frequency). The trade-off is that models will partly detect churn already in progress, which inflates naïve accuracy. Phase 3 will report how much lift comes before the fade starts.

**1.4 Dormancy is separate from churn**
Travel, migrant work and resting SIMs create silent spells. About 3% of these spells run longer than 90 days, so **12% of 90-day "churners" later come back**. This is a real feature of BD prepaid, and it is where the churn definition itself is tested.

**1.5 What counts as a revenue event**
A revenue event is a recharge. Direct pack purchases through MFS/app arrive as recharges of the pack price. Activation, plus a pre-window "last revenue date" snapshot, also count, so subscribers aren't misclassified at the window edges. Usage drawn from balance is not modelled separately (simplification).

**1.6 90-day burn-in**
Simulated but not written. Without it, the first months would show artificially low churn and nobody mid-switch or mid-dormancy. The subscriber table carries the operator-style snapshot `last_revenue_date_pre_window`.

**1.7 Pilot moved from month 16 (in PLAN.md) to month 13 (2026-01-01)**
**This is a deviation from the approved plan.** A month-16 pilot ends on the last observed day, so nobody's 90-day churn outcome could be observed. Starting on 2026-01-01 means the 90-day window ends 2026-03-31 and the 90-day silence test is observable by 2026-06-30.

The pilot has 40,000 subscribers in 5 equal arms (control + 4 offers). Pilot subscribers are excluded from all other campaigns during the window.

**1.8 Business-as-usual campaigns are targeted, not random**
They follow the existing rule: recharges in the last 30 days fell below half of the prior 30 days. There is also a pre-Eid bonus-data blast to 20% of smartphone users. This history is deliberately confounded, so Phase 5 can show why learning only from past campaigns misleads.

**1.9 How ground truth is defined (hidden 12 months)**
From the end-of-window state, the simulation is run 365 days under each of the 5 arms. It uses 4 Monte Carlo paths and **common random numbers**, so each path's arms differ only by the treatment. Definitions:
- **True 90-day churn probability** = 1 − exp(−Σ daily hazard) along each path, averaged.
- **True CLV** = mean simulated 12-month gross recharge × 0.72 (net) × 0.78 (contribution margin).
- **True uplift** = difference between arms.

The trade-off is that 4 paths leaves some individual-level noise in the expected CLV. That noise averages out at segment level, which is where it is used.

**1.10 Ground-truth firewall**
Truth lives in `data/ground_truth/`. A test fails if any module outside `nodi.simulate` (writer) or `nodi.validate` (validator) references it, or if hidden trait columns appear in `data/raw`.

**1.11 Treatment effects are tied to nominal offer designs**
For example, bonus data = 2 GB for 7 days (`catalog.py`). Phase 5 attaches the ৳ cost model. If you redesign an offer materially in Phase 5, the planted effect no longer describes it, and I'll flag that.

**1.12 matplotlib for static charts, Plotly for the app**
The plan had Plotly + kaleido for PNG export. kaleido v1 needs a Chrome install, which is fragile on reviewers' machines. matplotlib is a lighter dependency for static PNGs.

**1.13 Calibration (tuned on 10k runs, then confirmed on the 200k build)**
Targets were net ARPU near ৳140 (Robi reported ৳140 in Q1 2024) and monthly churn near 3%. Parameters tuned:
- recharge amount level
- pack choice skew toward cheaper packs
- base hazard level and spread
- contact-fatigue share
- new-subscriber share

Gross adds were raised (initial base 65%, 35% acquired during the window). The active base ends roughly flat (129k → 133k). That is slightly kinder than the 2024 sector trend; see ASSUMPTIONS A07.

**1.14 Full build performance**
The 200k build takes about 8 minutes on this machine: 6.3 minutes of simulation, most of it the 20 hidden-future runs (5 arms × 4 paths), plus about 1.5 minutes for the report. It writes 322 MB to `data/`, including 44.2M daily-usage rows, 9.6M recharges and 2.7M pack purchases.

### Business calls for you (defaults set so the build runs; please confirm or change)

**B1.1 Planted response-group mix**
Persuadable / sure thing / lost cause / sleeping dog per offer. This is the "world" the models will be judged against. Current default is roughly 7–15% persuadable, about 70% sure things, 2% lost causes and 4–10% sleeping dogs. Options are below.

> **Decided 2026-11-17: "Harder world" (you).** You chose this over keeping the original mix or an easier world.
>
> **What changed:** `truth_world.effect_scale` = 0.6 (every offer's planted retention effect cut by 40%) and `contact_fatigue_share` from 6% to 9%. On a 10k sweep this gives about 5% persuadables (cashback ~8%, tenure reward ~2%) and about 11% sleeping dogs.
>
> **Trade-off you're accepting:**
> - The gap between smart targeting and a blanket offer gets bigger, which makes for a stronger story.
> - The uplift models in Phase 5 will be noisier, and validation against the truth will be less clean.
> - Some offers may not pay back at any budget.
>
> **Interview line:** "I deliberately made the world hard: most people don't need an offer, and one in ten is pushed out by one."
>
> The sweep options were (effect scale, fatigue share): (0.6, 0.10) → 4.6% / 11.5%; (0.5, 0.10) → 3.4% / 11.0%; (0.45, 0.11) → 2.6% / 11.7%.

**B1.2 Region and handset mix**
Division shares come from Census 2022. Urban share and handset tiers are assumptions (see ASSUMPTIONS.md). Changing them reshapes segments in Phase 4.

---

## Phase 2: Governed data model (2026-11-17)

### Business calls (yours)

**2.1 Headline ARPU = net revenue ÷ paying subscribers (ARPPU)**
You chose this over ARPU per active subscriber and over gross recharge per active subscriber.
- On the 200k build: **৳148 per paying subscriber** vs ৳133 per active subscriber.
- **Trade-off:** it is steadier and reflects what a paying customer is worth. It is *not* comparable with operators' published ARPU (Robi: ৳140, per active subscriber).
- `arpu_active_base` is kept as a clearly labelled secondary metric. Any external comparison must use it, and the metric definition says so.

**2.2 Active subscriber = revenue event in the prior 90 days**
You chose this over 30-day revenue-active and over 90-day any-activity. It is consistent with the churn definition. As a result, the active base reconciles exactly every month:

`active(m+1) = active(m) − churners(m) + new(m) + reactivated(m)`

That identity is enforced as a data-quality error check.

### Technical choices

**2.3 Star schema**
- **Dimensions:** date (with festival periods), subscriber, pack, offer, campaign.
- **Facts:** recharge, pack purchase, daily usage, offer exposure, inactivity spell, plus a **monthly subscriber snapshot**: 200k × 18 months, about 3M rows. The snapshot is the standard CVM grain and will feed the Phase 3 models.

Metrics query only three `mart_*` views. The facts can change underneath without touching any KPI.

**2.4 An in-house metrics layer instead of dbt / MetricFlow / Cube**
`metrics.yml` plus about 150 lines of Python (`nodi/metrics.py`). Each KPI is defined once:
- Composite KPIs reference others (`{{ net_revenue }} / {{ paying_subscribers }}`).
- Any KPI can be sliced by any column of its model.
- Experiment lifts are a metric type.

**Trade-off:** no caching or access control. That's fine at portfolio scale, and it avoids a heavy dependency a reviewer would have to install.

**2.5 Economics applied once at load time**
Net revenue (×0.72) and margin (×0.78) are columns in `fct_recharge`, so no query re-applies them inconsistently.

**2.6 Inactivity spells are re-derived when the warehouse is built**
Changing `churn.churn_days` in config takes effect without re-simulating.

**2.7 Pilot outcome definition (observable)**
"Churned" = went silent before the 90-day pilot window ended **and** stayed silent 90 days. That is observable by 2026-06-30.
- **Known bias:** subscribers who decide to leave late in the window still have revenue near its end, so they aren't counted. This is an undercount, and it is the same in every arm, so lifts are unbiased.
- **Preview** (offer cost not yet deducted; Phase 5): blanket offers move retention by only **−0.0 to +0.8pp** versus control. That is the "harder world" showing.

**2.8 Data quality**
- **28 checks** across uniqueness, referential integrity, completeness, validity, temporal consistency, reconciliation, experiment integrity and KPI plausibility (the plausibility checks run through the governed metrics).
- **Severity:** errors fail the build; warnings are reported.
- **Fault injection:** 5 realistic faults are planted in copies of the warehouse (double-loaded file, missing day, negative reversal, orphan IDs, mis-tagged handsets). The report shows which checks fire for each. **All 5 are caught.** A test enforces this.

**2.9 Phase 1 report moved onto governed metrics**
The provisional SQL is gone. Phase 1 headlines now read net ARPPU ৳148 and net active-base ARPU ৳133. Previously the report showed gross recharge per active subscriber, ৳185. The data is unchanged; only the definitions are.

**2.10 Warehouse size**
394 MB DuckDB file, built in about 25 seconds from raw Parquet. It is gitignored and rebuilt by `run.py`. The Streamlit app will read small precomputed outputs, not the warehouse.

---

## Phase 3: Churn and CLV models (2026-11-17)

### Technical choices

**3.1 What we predict**

`churn_90d` = the subscriber goes silent within the next 90 days **and** stays silent for 90 days. It covers subscribers already slowing down as well as those who will start to.
- It is the same definition as the pilot outcome (2.7), so the churn model and the uplift models in Phase 5 measure the same thing.
- **Trade-off:** labels need 180 days of future data, so the latest labelled snapshot is 2026-01-01.
- About 16–19% of the active base is in this state in any quarter.

**3.2 Strictly out-of-time backtest**

| Role | Snapshots | Notes |
|---|---|---|
| Train | Apr–Jun 2025 | |
| Calibrate (isotonic) | Jul 2025 | |
| Test | Jan 2026 | Every training and calibration label is observable before the test date |

Production retrains on Apr–Oct 2025, calibrates on Jan 2026 and scores the active base on 2026-07-01.

**3.3 LightGBM vs logistic regression**

LightGBM wins, but narrowly: AUC 0.798 vs 0.790 and top-decile lift 4.5 vs 4.3. **I keep LightGBM** for its slightly better ranking and native SHAP, and I'll say plainly in interviews that a logistic regression gets about 95% of the way there. The real gain is over **today's win-back rule**: contacting the same number of people, the model reaches 54% of churners against the rule's 24%.

**3.4 Honest limitation: early warning is hard**

Among subscribers who recharged in the last 14 days (78% of the base), AUC drops to 0.66 and top-decile lift to 2.6. Most of the model's power comes from behaviour that is already declining: "activity falling off" is 48% of its signal. This is expected because planted churn decisions are partly random. It also means the campaign window is short.

**3.5 Drivers explained in business language, not SHAP plots**

Feature SHAP values are grouped into 8 business themes. Each theme gets a measured contrast on the test set and a CVM action, for example "No pack bought in 90 days: 34% churn vs 10% for regular pack buyers". See `reports/phase3/summary.md`.

**3.6 CLV: BG/NBD + Gamma-Gamma implemented in scipy**

- **Inputs:** transactions are recharge days, measured in weeks. Monetary value is contribution margin per recharge.
- **Left truncation:** existing subscribers are "born" at their first recharge in the window. Their pre-2025 tenure is ignored, which is a known simplification.
- **Testing:** the plan said "test against published reference results", but that dataset can't be fetched offline. Instead, tests **simulate customers from known parameters and check the fit recovers them**. That's a stronger correctness test.
- **Gamma-Gamma assumption:** monetary value is independent of frequency (measured correlation −0.03).

**3.7 CLV baseline = run-rate**

Average monthly margin over the last 6 months × 12, which is what most operators use. Results:

| Model | Holdout MAE (H1 2026) | Holdout total error | Rank vs true CLV |
|---|---|---|---|
| BG/NBD + GG | ৳169 | −3.0% | 0.82 |
| Run-rate | ৳212 | +4.5% | 0.71 |

The run-rate baseline **overstates total 12-month CLV by 10.8% against the planted truth**, because it assumes nobody leaves.

**3.8 Validation against planted truth**

On the production scores (2026-07-01), compared with the hidden 12 months:
- **Every observable planted driver is recovered.** Rank correlation with model risk: engagement +0.51, tenure +0.41, first-90-days +0.34, kiosk +0.19, second SIM +0.18, network +0.13.
- **Division ranking:** model risk orders the 8 divisions exactly by planted network quality (rank correlation 1.00).
- **Pure-noise base hazard:** weakly correlated at +0.05, as it should be.

### Business call for you

**B3.1 Risk-band cut-offs** (used by the Phase 4 segmentation). Options are below. **Key fact:** the riskiest 10% hold 45% of expected churners but only 21% of the margin at risk. Their average 12-month CLV is ৳454, against ৳1,310 for low-risk subscribers.
