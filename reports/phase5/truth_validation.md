# Phase 5: plans vs planted truth (synthetic data)

## At the ৳1 crore budget (operator scale)

| Plan | Model estimate | TRUE net 12m margin |
|---|---:|---:|
| optimised | ৳3.13 cr | ৳5.15 cr |
| naive_uplift | ৳27.37 cr | ৳0.35 cr |
| blanket | - | ৳0.97 cr |
| highest_churn_risk | - | ৳-0.70 cr |

## Uplift: predicted vs true incremental 12m margin per subscriber (before cost)

         offer_id  pred_value_mean  true_value_mean  spearman  true_retention_uplift_pp  true_persuadable  true_sleeping_dog
       bonus_data            6.231            8.829     0.472                     0.184             0.051              0.123
recharge_cashback           23.038           25.573     0.220                     0.814             0.079              0.079
    tenure_reward            0.000           -0.157       NaN                    -0.041             0.026              0.130
  bundle_discount           14.573           14.071     0.431                     0.335             0.033              0.089

## Who the plan targets, in truth

 segment_id              segment  targeted  true_inc_per_sub  sleeping_dog
          1    Fading high-value       674            22.629         0.034
          2      Shaky newcomers      1743            68.712         0.084
          3   Slipping valuables       720            35.342         0.053
          4 Valuable but exposed      5145            41.408         0.059
          5 Mid-value gone quiet       246            43.711         0.033
          6    Low-value lapsers       136            21.375         0.037
          7   Low-value wobblers       886            32.724         0.064
          8          Stable core      6936            30.057         0.064
