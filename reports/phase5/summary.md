# Phase 5: offer engine and budget allocation (synthetic data)

Operator scale: our base is a 1% sample; ৳ and subscriber counts are x100 (DECISIONS B5.1).

## 1. What the randomised pilot proved (Jan 2026, 8,000 per arm)

| Offer | Extra 90-day margin / targeted sub | Retention uplift | Redemption | Cost / targeted (network) | Net (network) | Net (face value) | Personalised by |
|---|---:|---:|---:|---:|---:|---:|---|
| Bonus data | ৳7.0 ± 6.5 | +0.4 ± 1.1 pp | 30% | ৳3.3 | ৳+3.8 | ৳-15.4 | redemption |
| Recharge cashback | ৳23.2 ± 7.0 | +0.8 ± 1.1 pp | 49% | ৳12.5 | ৳+10.7 | ৳+10.7 | redemption |
| Tenure reward | ৳1.1 ± 7.0 | +0.8 ± 1.1 pp | 25% | ৳2.1 | ৳-1.1 | ৳-19.2 | none (average effect) |
| Bundle discount | ৳14.2 ± 6.5 | -0.0 ± 1.1 pp | 38% | ৳40.6 | ৳-26.3 | ৳-26.3 | redemption |

## 2. The ৳1 crore plan vs the alternatives (model estimates, operator scale)

| Plan | Subscribers targeted | Spend (network cost) | Spend (face value) | Expected net 12m margin | Net per ৳ spent |
|---|---:|---:|---:|---:|---:|
| Optimised | 1,656,700 | ৳1.00 cr | ৳7.04 cr | ৳3.11 cr | 3.11 |
| Blanket recharge_cashback | 787,000 | ৳1.00 cr | ৳1.00 cr | ৳0.81 cr | 0.81 |
| recharge_cashback to highest churn risk | 866,300 | ৳1.00 cr | ৳1.00 cr | ৳0.79 cr | 0.79 |

- The most that can be spent profitably is ৳11.9 crore a quarter (expected net ৳13.8 crore). At ৳1 crore, the budget binds and ranking matters.
- Offer mix in the plan (sample counts, excluding holdout): {'bonus_data': 15722}.
- **Pilot check (observable, inverse-propensity weighted):** optimised: ৳1.23 ± 7.29 net 90-day margin per pilot subscriber; blanket: ৳0.24 ± 3.28 net 90-day margin per pilot subscriber. Only 12% of subscribers are treated at this budget, so the pilot's 95% intervals overlap and it cannot separate the policies. That is why the plan launches with its own randomised holdout.

## 3. How we prove it worked: holdout and power

| Holdout | Holdout subs | MDE margin (৳/sub) | Power at expected effect | MDE retention (pp) | Forgone net margin |
|---:|---:|---:|---:|---:|---:|
| 1% | 16,567 | ৳4.98 | 100% | 0.81 | ৳3.1 lakh |
| 2% | 33,134 | ৳3.54 | 100% | 0.58 | ৳6.2 lakh |
| 5% | 82,835 | ৳2.28 | 100% | 0.37 | ৳15.6 lakh |
| 10% | 165,670 | ৳1.65 | 100% | 0.27 | ৳31.1 lakh |
| 20% | 331,340 | ৳1.24 | 100% | 0.20 | ৳62.3 lakh |

## 4. Uplift model selection (held-out BLP test per offer and outcome)

         offer_id   outcome    ate  ate_se             candidate  ate_shrunk  beta2_used  beta2_t
       bonus_data    margin  7.039   3.331            redemption       5.751      69.546    2.918
       bonus_data retention  0.004   0.006 none (average effect)       0.000       0.000      NaN
recharge_cashback    margin 23.197   3.595            redemption      22.653      51.881    1.772
recharge_cashback retention  0.008   0.006 none (average effect)       0.000       0.000      NaN
    tenure_reward    margin  1.083   3.592 none (average effect)       0.000       0.000      NaN
    tenure_reward retention  0.008   0.006 none (average effect)       0.000       0.000      NaN
  bundle_discount    margin 14.225   3.321            redemption      13.490     181.092    4.401
  bundle_discount retention -0.000   0.006 none (average effect)      -0.000       0.000      NaN
