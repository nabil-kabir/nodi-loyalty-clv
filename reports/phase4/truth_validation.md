# Phase 4: segments vs planted truth (synthetic data)

| # | Segment | Pred churn | True churn | Pred CLV ৳ | True CLV ৳ | Pred % at risk | True % at risk |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | Fading high-value | 71% | 62% | 491 | 452 | 29% | 3% |
| 2 | Shaky newcomers | 23% | 24% | 1,169 | 1,056 | 13% | 19% |
| 3 | Slipping valuables | 23% | 20% | 1,523 | 1,274 | 5% | 3% |
| 4 | Valuable but exposed | 11% | 9% | 1,956 | 1,823 | 12% | 15% |
| 5 | Mid-value gone quiet | 36% | 28% | 682 | 760 | 4% | 3% |
| 6 | Low-value lapsers | 31% | 25% | 528 | 666 | 2% | 3% |
| 7 | Low-value wobblers | 9% | 9% | 1,029 | 1,035 | 6% | 10% |
| 8 | Stable core | 7% | 6% | 1,154 | 1,138 | 28% | 45% |

## Planted response mix by segment (validation only)

offer_id    bonus_data  bundle_discount  recharge_cashback  tenure_reward
segment_id                                                               
1                0.076            0.048              0.086          0.034
2                0.209            0.189              0.299          0.000
3                0.066            0.029              0.046          0.026
4                0.101            0.040              0.037          0.019
5                0.087            0.056              0.100          0.047
6                0.031            0.017              0.071          0.061
7                0.031            0.024              0.105          0.022
8                0.022            0.011              0.053          0.029

Sleeping-dog share:

offer_id    bonus_data  bundle_discount  recharge_cashback  tenure_reward
segment_id                                                               
1                0.127            0.088              0.081          0.153
2                0.167            0.087              0.085          0.293
3                0.090            0.079              0.075          0.097
4                0.073            0.079              0.085          0.120
5                0.120            0.084              0.078          0.139
6                0.138            0.094              0.081          0.112
7                0.133            0.087              0.075          0.140
8                0.125            0.091              0.078          0.109
