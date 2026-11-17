# Phase 5: plans vs planted truth (synthetic data)

## At the ৳1 crore budget (operator scale)

| Plan | Model estimate | TRUE net 12m margin |
|---|---:|---:|
| optimised | ৳3.11 cr | ৳5.12 cr |
| naive_uplift | ৳26.40 cr | ৳0.53 cr |
| blanket | - | ৳0.99 cr |
| highest_churn_risk | - | ৳-0.60 cr |

## Uplift: predicted vs true incremental 12m margin per subscriber (before cost)

         offer_id  pred_value_mean  true_value_mean  spearman  true_retention_uplift_pp  true_persuadable  true_sleeping_dog
       bonus_data            6.912            9.633     0.471                     0.231             0.054              0.121
recharge_cashback           23.010           25.867     0.219                     0.789             0.076              0.079
    tenure_reward            0.000           -0.181       NaN                    -0.041             0.025              0.130
  bundle_discount           15.328           14.738     0.432                     0.348             0.034              0.089

## Who the plan targets, in truth

 segment_id              segment  targeted  true_inc_per_sub  sleeping_dog
          1    Fading high-value       765            21.250         0.034
          2      Shaky newcomers      1867            69.011         0.082
          3   Slipping valuables       767            33.794         0.052
          4 Valuable but exposed      5414            40.851         0.060
          5 Mid-value gone quiet       274            41.976         0.029
          8          Stable core      7480            29.285         0.066
