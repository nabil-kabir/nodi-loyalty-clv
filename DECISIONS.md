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

> **Decided 2026-11-17: B3.1 = C, value-at-risk bands (you).**
> - **Ranking:** subscribers are ordered by expected margin at risk = predicted 12-month CLV × 90-day churn probability.
> - **Bands:** High = top 10%, Medium = next 20%, Low = the rest.
> - **What High contains:** 31% of margin at risk and 26% of expected churners. That is in exchange for 45% of churners under rank-based bands.
> - **Rationale:** budget follows margin, which is the Phase 5 objective. The risk-only view stays available as a secondary lens (`churn_decile`) so CVM can still see who is most likely to leave.

---

## Phase 4: Value × risk segmentation (2026-11-17)

### Correction (found while building Phase 4)

**4.1 Margin at risk was double-counting churn. Fixed.**
- **The flaw:** the B3.1 options were sized with *CLV × churn probability*. BG/NBD CLV already discounts for the chance of leaving, so high-risk subscribers were penalised twice.
- **The fix:** margin at risk = **churn probability × value if retained**, where value if retained = the BG/NBD expectation *conditional on still being a customer* × Gamma-Gamma margin. It is stored as `value_if_retained_12m`.
- **Effect:**
  - total margin at risk rises from ৳1.61 to **৳1.99 crore**
  - the riskiest 10% hold 34% of it, not 21%
  - their value if retained is ৳799, against ৳1,332 for low-risk subscribers
- **Your call:** I raised this and you kept option C with the corrected formula.
- **Truth:** the planted truth gained a matching "nobody newly churns for 12 months" arm. The prediction validates at Spearman 0.85, MAE ৳249, total bias −2.5%. The other arms are unchanged, because each one replays the same random numbers.

### Business calls (yours)

**4.2 Value-at-risk bands (B3.1 = C, corrected)**
Rank by churn probability × value if retained. High = top 10%, Medium = next 20%, Low = rest.

**4.3 Segmentation = value-at-risk band × churn stage (B4.1 = A)**
You chose this over a classic CLV × risk grid and over value-at-risk × usage profile. The stage axis comes first so the segment says *why and when*, which the optimiser can't. The *which offer* question is left to Phase 5.

- **Stages,** checked in this order: gone quiet (21+ days with no revenue event), new (under 6 months tenure), slipping (activity below 60% of the previous 30 days, or recharges below half), steady.
- **12 cells → 8 named segments,** each with a stance and a one-line action. The thresholds, names and actions live in `segments.yml` and can be edited without touching code.

### Technical choices

**4.4 Every size comes from metrics.yml**
`scores_subscriber` now carries the segment columns. New metrics: `scored_subscribers`, `expected_churners`, `value_if_retained`, `net_revenue_at_risk`. A test checks that segment totals reconcile to the governed totals.

**4.5 Profile uses the over-indexed division, not the most common one**
Dhaka is the most common division in every segment because it's the largest, so that told us nothing.

### What validation against truth says (a hypothesis for Phase 5, not acted on)

**4.6 Fading high-value looks like the biggest prize, but much of it is already gone.**

| Fading high-value | Model | Planted truth |
|---|---|---|
| Share of margin at risk | 29% | 3% |
| Already silently churned | — | 55% (still "active" under the 90-day rule) |
| Value if retained | ৳989 | ৳513 |

- **Planted incremental margin per subscriber** (before offer cost): ৳0–14 here, against ৳20–33 for Shaky newcomers and ৳26–30 for Valuable but exposed.
- **Why it matters:** this is the classic case for uplift modelling over risk × value targeting. **I have not changed the segment's stance**, because acting on hidden truth would be peeking.
- **Next:** Phase 5's uplift models, trained only on the observable pilot, should independently find that offers barely move "gone quiet" subscribers. If they do, segment 1's stance moves from *invest* to *test*, on observable evidence.

---

## Phase 5: Offer engine and budget allocation (2026-11-17)

### Business call (yours)

**B5.1 Budget scale = our base is a 1% sample of a ~13.3M-active operator.**
- **Effect:** ৳1 crore operator becomes ৳1 lakh on the sample, and the budget binds hard.
- **Rejected options:**
  - A 10% sample (the budget would cover about 82% of the base).
  - "The sample is the operator" (only ৳14.3 lakh of the crore could be spent profitably).

### Technical choices, including two mistakes caught and fixed

**5.1 Uplift is learned only from the randomised pilot, never from targeted campaigns**
Past win-back campaigns were targeted (1.8), so their outcomes are confounded.

**5.2 First attempt failed: raw uplift scores plus an optimiser is a money-losing machine**
- **What happened:** T-learner uplift scores fed straight to the optimiser claimed ৳27.4 crore of net margin at ৳1 crore. The truth was **৳0.35 crore**.
- **Why:** with 8,000 subscribers per arm and effects of a few taka, the scores are mostly noise, and an optimiser hunts noise (the winner's curse). Cheap offers make it worse: a ৳2 tenure reward with noisy +৳5 value looks like a 150% return.
- **I keep this naive plan in the report as a cautionary comparison.**

**5.3 Fix part 1: let held-out pilot data decide how much personalisation is real**
- Three candidate scores, all cross-fitted: a T-learner, a DR-learner with a ridge final stage on 12 interpretable features, and predicted redemption probability.
- For each offer and outcome, a **Best Linear Predictor test** (Chernozhukov et al., 2018) on out-of-fold predictions estimates β₂: how much of a score's predicted variation is real.
- The candidate with the strongest significant β₂ (t > 1.64) is used. If none passes, everyone gets the average effect.
- **Result:** the T-learner never passes. Predicted redemption passes for the margin effect of bonus data (t = 2.9), cashback (t = 1.8) and bundle discount (t = 4.4). People likely to redeem also gain more. No retention effect is personalisable.

**5.4 Fix part 2: act only on effects the pilot can distinguish from zero**
- An average effect is used only if one-sided significant at 5%, then shrunk by ate²/(ate² + se²).
- **Effect:** every retention uplift drops to 0 (all are below 1pp ± 1.1pp), and so does the tenure reward's margin uplift.
- **Truth check:** true retention uplifts are 0.0–0.8pp. Treating them as zero costs almost nothing and stops the optimiser multiplying noise by ৳1,200 of value-if-retained.

**5.5 Value of an offer**
- **Formula:** extra 90-day margin (measured directly in the pilot) + retention uplift × value-if-retained × 0.75 (months 4–12 carried forward). Nothing is counted twice.
- **What drives it:** after 5.4, value is driven by **spend lift**. The pilot's main finding is that offers make people top up more, not stay longer.

**5.6 Optimiser = LP relaxation of a multiple-choice knapsack, solved greedily**
- **Method:** each subscriber's options form a concave hull of (cost, net). The hull's incremental steps are ranked by net per taka across the base.
- **Optimality:** exact for the LP relaxation, and within one item per subscriber of the integer optimum.
- **Speed:** steps are precomputed, so any budget is a cumulative-sum lookup. That is what makes the app slider live.

**5.7 Fair baselines**
- Both send the pilot's best single offer (recharge cashback, the best average net) either to the highest churn-risk subscribers or at random.
- Neither baseline uses hidden information, and they are the plans a sensible manager would run from the pilot readout.

**5.8 Evidence, observable and validated**

| At ৳1 crore | Model estimate | True net 12-month margin |
|---|---:|---:|
| **Optimised** | ৳3.13 cr | **৳5.15 cr** |
| Blanket cashback | ৳0.81 cr | ৳0.97 cr |
| Cashback to highest churn risk | ৳0.79 cr | **−৳0.70 cr** |
| Raw uplift scores (5.2) | ৳27.4 cr | ৳0.35 cr |

- **The model is conservative,** which is the purpose of the shrinkage.
- **Highest-risk targeting loses money:** the riskiest subscribers are mostly "gone quiet" lost causes. That confirms the Phase 4 hypothesis (4.6) from observable data: the plan gives offers to only 7% of Fading high-value, the segment's lowest true return.
- **The pilot cannot tell the policies apart:** inverse-propensity weighting gives overlapping ±৳13 intervals per pilot subscriber. The plan's own holdout is what will prove it.

**5.9 The headline recommendation depends on decision 0.5**
- At network cost, bonus data costs about ৳3.4 per targeted subscriber and is the plan's only offer at ৳1 crore.
- At face value, it costs about ৳22 and loses ৳15 per head, and the plan would switch to cashback.
- That is a real point to defend with Finance.

**5.10 Reproducibility bug found and fixed**
- **Bug:** DuckDB returns rows in a non-deterministic order. The cross-fitted uplift scores are positional, so one run silently mismatched them to the wrong subscribers.
- **Fix:** frames are sorted by `sub_id` before any positional step.
- **Lesson:** a sort is required before any positional step on DuckDB output.

**5.11 An empty plan is a valid answer**
- On the tiny test sample, nothing passes the significance rule, so the plan is "spend nothing".
- The code and tests treat that as correct, not as an error.
