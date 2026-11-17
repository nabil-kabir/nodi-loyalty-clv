# PLAN — Nodi Telecom: Prepaid Loyalty & CLV Decision Engine

> Status: **DRAFT, awaiting approval.** Nothing is built until this plan is signed off.

## The question this answers
"If I ran loyalty at a Bangladeshi prepaid operator with a ৳1 crore quarterly retention budget, who would I spend it on, with what offer, and how would I prove it worked?"

Everything below is there to answer that question for a Head of Loyalty / CVM, who will spend about 5 minutes on it. Anything that doesn't help answer it gets cut.

---

## Locked decisions (from clarifying questions, 2026-11-17)

| # | Topic | Decision | Consequence |
|---|---|---|---|
| 1 | Distribution | Public GitHub repo + Streamlit Community Cloud link | App reads only small precomputed outputs (`app_data/`, committed, target < 50 MB). Raw data is gitignored and rebuilt locally. |
| 2 | Usage grain | Daily usage summaries for all ~200k subs × ~540 days (~108M rows) | Generated in monthly chunks to partitioned Parquet. Full build is minutes, not seconds. A `--sample` flag (e.g. 20k subs) for fast dev and tests. |
| 3 | CLV definition | 12-month forward **contribution margin** (revenue × assumed margin %) | True CLV is planted by simulating 12 months *beyond* the observed 18. Models never see those months. |
| 4 | Churn | Churn = **90 days** with no revenue event; **30 days** = dormant early-warning. Both configurable. | 90-day basis to be verified and cited in `ASSUMPTIONS.md` (BTRC active-subscriber definition), otherwise marked as an assumption. |
| 5 | Offer cost | Bonus data at **marginal network cost** (৳/GB, assumption); cashback at full cash value; app shows both "economic" and "face value" cost views | Optimiser runs on economic cost. The face-value view is a sensitivity check. |

---

## Proposed repo structure

```
nodi-loyalty/
├── README.md                  # Phase 8: case study first, setup last
├── PLAN.md  DECISIONS.md  ASSUMPTIONS.md  LINKEDIN_POST.md  DEMO_SCRIPT.md
├── PROJECT_BRIEF.md           # renamed from PROJECT_BRIEF.md.txt
├── config.yaml                # seed, n_subs, months, churn_days, dormant_days, budget, model name, margin %
├── metrics.yml                # single source of truth for every KPI (Phase 2)
├── run.py                     # one command: `python run.py [--sample] [--from-phase N]`
├── pyproject.toml / requirements.txt
├── src/nodi/
│   ├── config.py
│   ├── simulate/              # Phase 1: latent traits → events; writes data/raw + data/ground_truth
│   ├── warehouse/             # Phase 2: DuckDB star schema, metrics loader, DQ checks
│   ├── models/                # Phase 3: churn (LightGBM), CLV (BG/NBD + Gamma-Gamma, baseline)
│   ├── segments/              # Phase 4
│   ├── offers/                # Phase 5: cost model, uplift, optimiser, experiment design
│   ├── messaging/             # Phase 6: Claude client, SMS length rules, number-check, cache
│   └── validate/              # the ONLY package allowed to read ground truth
├── app/                       # Phase 7: Streamlit, 4 pages, reads app_data/ only
├── app_data/                  # small committed outputs for the app + mock-mode LLM cache
├── data/                      # gitignored: raw/, ground_truth/, warehouse.duckdb
├── reports/                   # DQ report, validation report, exported PNG charts
└── tests/
```

---

## Key design choices

### 1. Simulation: latent traits drive behaviour
Each subscriber gets hidden traits: price sensitivity, data affinity, engagement, multi-SIM propensity, a "competitor pull" factor, a regional network-quality effect and a baseline churn hazard. Observable behaviour (recharges, packs, usage) is generated from those traits. That way the drivers can be *recovered* by the models rather than just read off a column.

Behaviours built in:
- small, frequent recharges (৳10–৳50 heavy) across MFS / retailer / app channels
- Eid-ul-Fitr / Eid-ul-Adha / Pohela Boishakh spikes
- multi-SIM switching: usage moves to a "phantom" second SIM, so you see falling share of wallet before churn
- pack-driven cycles: pack expiry → renew, downgrade or go silent

### 2. Planted ground truth, behind a firewall
Saved to `data/ground_truth/` and covering:
- each subscriber's true hazard and churn drivers
- true 12-month CLV (expected + one realised path)
- per-offer true treatment effect

The offer response groups are **persuadable**, **sure thing**, **lost cause** and **sleeping dog** (reacts badly).

Only `src/nodi/validate/` may read ground truth. A test fails the build if any other module references that path. This is what makes "the models recover the truth" claim honest.

### 3. A randomised pilot inside the data
Month 16 contains a simulated randomised pilot: ~40k subscribers, 4 offers + a control group, with outcomes observed through month 18. Uplift models train on this pilot. Business-as-usual offer exposures elsewhere in the history are *targeted*, not random. The README can show briefly why naïvely learning from targeted history would mislead. That's a strong interview point and costs little.

### 4. Time discipline
- **Churn model:** features as of cutoff T, label = 90-day churn after T. Train on earlier cutoffs, test on a later one.
- **CLV models:** calibrate on months 1–18, compare against the hidden months 19–30.
- **No future leakage:** checked by tests.

### 5. Metrics defined once
`metrics.yml` holds the following for each KPI:
- name and plain-English definition
- owner
- SQL against the star schema
- grain

A small loader renders the SQL. Models, app and charts call `metric("arpu", ...)` and never hand-write a KPI.

### 6. Optimiser objective
Expected incremental margin, where:

expected incremental margin = Σ [ uplift(retention) × CLV margin + incremental spend − expected offer cost ]

- Offer cost includes cost on sure things, who take the offer but wouldn't have churned.
- One offer per subscriber, under the budget: a multiple-choice knapsack, solved greedily on the efficient frontier. Fast enough to re-run live on the slider.
- Baselines: "target highest churn risk" and "blanket offer".

### 7. LLM safety by construction
- Offer terms are injected from structured records.
- A validator pulls every number from the copy (Bangla and English digits) and checks it against the record. Any mismatch is a rejection.
- SMS length is enforced in code: GSM-7 = 160 / 153 chars per part, UCS-2 (Bangla) = 70 / 67 chars per part.
- All outputs are cached. **Mock mode** (no API key) reads the cache.
- Model name comes from config, default `claude-sonnet-5-5`.

### 8. Money formatting
৳ with lakh/crore throughout (৳1,00,00,000 = ৳1 crore).

---

## Phases, deliverables and where I'll bring you options

| Phase | Builds | Key outputs shown at review | Business calls you'll decide |
|---|---|---|---|
| 1. Synthetic universe | `simulate/`, raw Parquet, ground truth, `ASSUMPTIONS.md` v1 | Base size, ARPU, recharge distribution, monthly churn curve, Eid spike chart | Response-group mix (how many persuadables vs sleeping dogs); regional / handset mix assumptions |
| 2. Governed data model | DuckDB star schema, `metrics.yml`, DQ report | KPI table from `metrics.yml`; DQ pass/fail summary | ARPU definition (per active vs per base); "active" definition for reporting |
| 3. Churn & CLV | LightGBM churn + calibration + lift/gains; BG/NBD + GG vs baseline | Top-decile lift; calibration; CLV error vs planted truth; drivers in plain language | Risk-band cut-offs |
| 4. Segmentation | 6–10 named segments with sizing and ৳ at risk | Segment table with subscribers, ৳ revenue at risk, one-line action | Segmentation axes and cut-offs (2–3 options) |
| 5. Offers & budget | Cost model, T-learner uplift, optimiser, experiment design | Uplift Qini vs planted truth; optimiser vs 2 baselines at ৳1 crore; holdout size + power | Offer catalogue & ৳ values; holdout %; the CMO success metric |
| 6. Campaign messages | Claude SMS generator, validators, cache, `review/bangla_review.csv` | Sample cells; validator pass rate; part counts | Tone / brand voice for Nodi |
| 7. Streamlit app | 4 pages + synthetic-data banner | Screenshots of each page | Exec summary headline numbers |
| 8. Packaging | README case study, 4 PNGs, LinkedIn draft, 90-sec demo script | Drafts for your edit | Final narrative framing |

**Every phase ends with:**
1. tests run
2. short summary + 2–3 key outputs
3. `DECISIONS.md` entry
4. git commit
5. **STOP** for your review

---

## Dependencies (lean)

**Core:**
- `duckdb`
- `pandas`
- `pyarrow`
- `numpy` / `scipy`
- `scikit-learn`
- `lightgbm`: gradient boosting, so the churn model is honest on tabular data; small wheel
- `pyyaml`
- `streamlit`
- `plotly`: interactive charts in the app; `kaleido` for PNG export
- `anthropic`
- `pytest`

**CLV:** I propose implementing BG/NBD and Gamma-Gamma directly with `scipy` (each is a short, well-documented likelihood). Reasons:
- `lifetimes` is unmaintained and may not install on Python 3.14.
- `pymc-marketing` is a heavy dependency for this job.

The implementation is validated two ways: unit tests against the published reference dataset results, and against planted truth.

---

## Runtime and size (estimates, to be confirmed in Phase 1)
- **Full build:** minutes. Daily usage dominates. Exact timing will be reported after Phase 1.
- **Raw data:** around 1 GB Parquet on disk (gitignored).
- **`app_data/`:** < 50 MB, so it fits Streamlit Cloud.

---

## Open items before I start (need your answer)
1. **GitHub:** proposed repo name `nodi-loyalty-clv`, public. Should I create the remote and push after each phase, or commit locally and you push?
2. **Python version:** stay on your installed **3.14** (with the scipy-based CLV above), or should you install 3.12 for maximum library compatibility? I recommend staying on 3.14 unless a wheel is missing; I'll flag it immediately if one is.
3. **Brief filename:** OK to rename `PROJECT_BRIEF.md.txt` → `PROJECT_BRIEF.md`?
