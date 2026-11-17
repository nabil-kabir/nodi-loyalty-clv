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

**B1.2 Region and handset mix**
Division shares come from Census 2022. Urban share and handset tiers are assumptions (see ASSUMPTIONS.md). Changing them reshapes segments in Phase 4.
