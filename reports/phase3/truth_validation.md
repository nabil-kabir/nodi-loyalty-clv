# Phase 3: validation against planted truth (synthetic data)

Production scores at 2026-07-01 compared with the hidden 12-month future that no model saw.

## Churn

- Rank correlation between predicted and true 90-day churn probability: **0.48**.
- Mean predicted 15.8% vs mean true 13.9%. The definitions differ slightly: the model predicts *going silent*, the truth is the *decision* to leave.
- The model's riskiest 10% hold **45%** of expected churners.

## Were the planted churn drivers recovered?

| Planted driver | Rank corr. with model risk | Recovered? |
|---|---:|---|
| Losing wallet share to a second SIM | +0.18 | yes |
| Low engagement (hidden trait) | +0.51 | yes |
| Weak network in their area | +0.13 | yes |
| Short tenure | +0.41 | yes |
| First 90 days after activation | +0.34 | yes |
| Activation-kiosk acquisition (first 6 months) | +0.19 | yes |
| Idiosyncratic base hazard (pure noise to the model) | +0.05 | weak |

- Division ranking: weak-network divisions carry higher model risk (rank corr. +1.00 across the 8 divisions).

## CLV

| Model | Spearman vs truth | MAE ৳ | Total bias | True value in predicted top 20% |
|---|---:|---:|---:|---:|
| BG/NBD + Gamma-Gamma | 0.823 | 263 | +2.8% | 38% |
| Run-rate baseline | 0.711 | 401 | +10.8% | 36% |
| Perfect foresight (ceiling) | 1.000 | 0 | 0% | 41% |
