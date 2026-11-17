# Phase 1 summary (synthetic data)

KPIs from metrics.yml; truth_* rows from planted ground truth.

## Headline numbers

- **subscribers_total**: 200,000
- **active_base_end**: 132,473
- **arpu_paying_net_bdt**: 147.560
- **arpu_active_net_bdt**: 132.833
- **recharges_per_paying_sub_month**: 4.544
- **median_recharge_bdt**: 30.000
- **share_recharges_le_50**: 0.812
- **monthly_churn_rate**: 0.032
- **smartphone_share**: 0.555
- **data_gb_per_smartphone_user_month**: 3.680
- **churned_spells_reactivated**: 0.113
- **mfs_share_of_recharges**: 0.371
- **truth_alive_at_end**: 126,623
- **truth_median_clv_margin_12m**: 1,024.894
- **truth_p90_clv_margin_12m**: 2,120.143
- **truth_mean_p_churn_90d**: 0.089

## Monthly KPIs (metrics.yml)

month_start  active_base    arpu  arpu_active_base  churn_rate  recharge_frequency  reactivations  churners
 2025-01-01       129397 144.178           128.802       0.029               4.455            207      3768
 2025-02-01       129970 133.554           117.547       0.036               4.117            336      4658
 2025-03-01       129221 160.239           145.828       0.035               4.947            416      4511
 2025-04-01       129678 143.075           128.302       0.031               4.420            394      3980
 2025-05-01       129793 146.420           131.567       0.032               4.522            481      4189
 2025-06-01       129942 148.134           133.479       0.032               4.567            481      4142
 2025-07-01       130149 147.168           132.494       0.033               4.541            551      4261
 2025-08-01       130241 146.195           130.928       0.032               4.506            542      4167
 2025-09-01       130579 143.589           126.696       0.033               4.422            527      4274
 2025-10-01       130683 148.190           130.967       0.039               4.561            505      5153
 2025-11-01       129933 144.763           128.972       0.041               4.457            508      5336
 2025-12-01       128889 148.949           134.742       0.034               4.581            541      4403
 2026-01-01       128868 151.566           137.919       0.030               4.650            503      3843
 2026-02-01       129398 137.008           123.072       0.027               4.223            442      3479
 2026-03-01       129855 165.447           152.201       0.029               5.072            530      3815
 2026-04-01       130973 147.727           134.162       0.028               4.537            493      3679
 2026-05-01       131543 153.859           140.810       0.028               4.735            531      3747
 2026-06-01       132473 146.020           132.513       0.028               4.483            506      3743

## Planted response groups (share by offer)

response_group     persuadable  sure_thing  low_responder  lost_cause  sleeping_dog
offer_id                                                                           
bonus_data                 5.1        65.3           14.8         2.6          12.3
bundle_discount            3.2        66.7           18.6         2.6           8.9
recharge_cashback          7.9        67.2           14.5         2.5           7.9
tenure_reward              2.7        65.6           16.2         2.6          13.0