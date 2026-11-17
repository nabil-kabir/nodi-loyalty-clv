# Phase 3 summary (synthetic data)

## Churn model: out-of-time test (scored 2026-01-01, trained on Apr-Jun 2025)

| Model | AUC | PR-AUC | Brier | Top-decile lift | Churners reached, top 10% | top 20% |
|---|---:|---:|---:|---:|---:|---:|
| LightGBM + isotonic | 0.798 | 0.610 | 0.093 | 4.49 | 45% | 60% |
| Logistic regression | 0.790 | 0.596 | 0.096 | 4.34 | 43% | 59% |
| Days since last recharge | 0.738 | | | | | |

- Base rate: 16.1% of the active base churns in the quarter.
- **Today's win-back rule** flags 15% of the base and reaches 24% of churners (precision 24%). **The model, contacting the same number of people, reaches 54%.**
- **Early warning is harder:** among subscribers who recharged in the last 14 days (78% of the base), AUC is 0.658 and top-decile lift is 2.6.

### Risk deciles (test)

 decile  subscribers  churners  churn_rate  avg_predicted  lift  cum_capture
      1        12887      9314       0.723          0.745 4.488        0.449
      2        12887      3102       0.241          0.281 1.495        0.598
      3        12887      1790       0.139          0.181 0.863        0.685
      4        12887      1339       0.104          0.145 0.645        0.749
      5        12886      1157       0.090          0.123 0.558        0.805
      6        12887      1000       0.078          0.109 0.482        0.853
      7        12887       918       0.071          0.093 0.442        0.897
      8        12887       827       0.064          0.086 0.399        0.937
      9        12887       722       0.056          0.074 0.348        0.972
     10        12886       582       0.045          0.055 0.280        1.000

## Churn drivers in business language

| Theme | Share of model signal |
|---|---:|
| Activity falling off | 48% |
| Gone quiet on recharges | 17% |
| Tenure and how they joined | 12% |
| Recharge slowdown | 8% |
| Where they live (network) | 7% |
| Handset and spend level | 4% |
| Pack habit | 2% |
| History (dormancy, offers) | 1% |

- **Activity falling off.** Subscribers active on fewer than half as many days as the month before: 66% churn next quarter vs 13% for those holding steady (5.1x). *Action:* Trigger a contact in the week activity halves, not after recharges stop.
- **Gone quiet on recharges.** No recharge for 3+ weeks: 51% churn next quarter vs 9% for those who recharged in the last week (5.9x). *Action:* Silence is the strongest signal but arrives late; treat 21+ days as last-chance win-back.
- **Recharge slowdown.** Recharges more than halved vs the previous month: 24% churn next quarter vs 9% for steady rechargers (2.8x). *Action:* Today's win-back rule uses this; the model ranks within it far better.
- **Tenure and how they joined.** Subscribers in their first 6 months: 29% churn next quarter vs 12% for 5+ year customers (2.5x). *Action:* Invest in onboarding (first 90 days) rather than late rescue for new SIMs.
- **Tenure and how they joined.** Street activation-kiosk acquisitions: 19% churn next quarter vs 16% for all other channels (1.2x). *Action:* Review kiosk incentives: they buy SIMs, not customers.
- **Where they live (network).** Sylhet, Barishal and Rangpur: 18% churn next quarter vs 15% for Dhaka (1.2x). *Action:* A network problem, not a marketing one: share this with the network team before buying offers.
- **Pack habit.** No pack bought in 90 days: 34% churn next quarter vs 10% for regular pack buyers (3+) (3.2x). *Action:* Pack habits anchor people; a first-pack nudge is a cheap retention lever.
- **History (dormancy, offers).** Two or more 30-day silences in the past year: 21% churn next quarter vs 11% for never dormant (1.9x). *Action:* Serial sleepers: likely secondary SIMs; don't spend premium offers on them.

## CLV: holdout (calibrate 2025, predict Jan-Jun 2026)

| Model | MAE ৳ | Total bias | Spearman | Top-20% value capture |
|---|---:|---:|---:|---:|
| BG/NBD + Gamma-Gamma | 169 | -3.0% | 0.824 | 44% |
| Run-rate baseline | 212 | +4.5% | 0.746 | 42% |

- Total recharges predicted vs actual: -3.1%.
- Frequency-monetary correlation -0.030 (Gamma-Gamma assumes ~0: OK).

## Production scores (2026-07-01)

- Scored 132,947 active subscribers.
- Predicted 12-month CLV: total ৳15.19 crore, median ৳1,012.
- Margin at risk (CLV x churn probability): ৳1.61 crore.
