# Phase 1 summary (synthetic data)

## Headline numbers

- **subscribers_total**: 200,000
- **active_base_end**: 133,403
- **gross_arpu_bdt_month**: 185.168
- **net_arpu_bdt_month**: 133.321
- **recharges_per_recharger_month**: 4.547
- **median_recharge_bdt**: 30.000
- **share_recharges_le_50**: 0.812
- **monthly_churn_rate**: 0.031
- **smartphone_share**: 0.555
- **data_gb_per_smartphone_user_month**: 3.948
- **churned_spells_reactivated**: 0.116
- **mfs_share_of_recharges**: 0.371
- **truth_alive_at_end**: 127,624
- **truth_median_clv_margin_12m**: 1,025.041
- **truth_p90_clv_margin_12m**: 2,119.228
- **truth_mean_p_churn_90d**: 0.088

## Monthly KPIs (provisional SQL; governed versions arrive in Phase 2)

     month  active_base  gross_recharge  n_recharges  recharging_subs  churners  gross_arpu  recharges_per_recharger  churn_rate
2025-01-01       129397      23147959.0       514947           115597      3768  178.891002                 4.454674    0.029120
2025-02-01       129970      21218872.0       470953           114393      4658  163.259768                 4.116974    0.035839
2025-03-01       129221      26169691.0       581707           117621      4509  202.518871                 4.945605    0.034894
2025-04-01       129682      23109182.0       512470           116255      3960  178.198840                 4.408154    0.030536
2025-05-01       129789      23765090.0       527848           116869      4134  183.105579                 4.516578    0.031852
2025-06-01       129996      24046948.0       533938           117258      4139  184.982215                 4.553532    0.031839
2025-07-01       130148      24025225.0       532166           117166      4215  184.599264                 4.541983    0.032386
2025-08-01       130289      23721355.0       526442           116632      4087  182.067212                 4.513701    0.031369
2025-09-01       130723      23048115.0       510459           115303      4270  176.312623                 4.427109    0.032664
2025-10-01       130856      23795452.0       527000           115804      5243  181.844562                 4.550793    0.040067
2025-11-01       130023      23357600.0       517334           115987      5197  179.642063                 4.460276    0.039970
2025-12-01       129121      24155322.0       535373           117038      4391  187.075085                 4.574352    0.034007
2026-01-01       129108      24578288.0       546271           117511      3835  190.369985                 4.648680    0.029704
2026-02-01       129667      22245352.0       492473           116907      3404  171.557544                 4.212519    0.026252
2026-03-01       130273      27437196.0       608282           120381      3836  210.613066                 5.052973    0.029446
2026-04-01       131410      24523215.0       541915           119656      3537  186.616049                 4.528941    0.026916
2026-05-01       132137      25925866.0       573648           121211      3447  196.204439                 4.732640    0.026087
2026-06-01       133403      24590546.0       542388           121046      3753  184.332781                 4.480842    0.028133

## Offer exposures

campaign_type          offer_id     n   redeem
  bau_winback        bonus_data 29468 0.427311
  bau_winback   bundle_discount 25543 0.392475
  bau_winback recharge_cashback 88532 0.484604
  bau_winback     tenure_reward  6457 0.361933
    eid_blast        bonus_data 24789 0.433458
        pilot        bonus_data  8000 0.311375
        pilot   bundle_discount  8000 0.390000
        pilot              none  8000 0.000000
        pilot recharge_cashback  8000 0.494750
        pilot     tenure_reward  8000 0.256875

## Planted response groups (share by offer)

response_group     persuadable  sure_thing  low_responder  lost_cause  sleeping_dog
offer_id                                                                           
bonus_data                10.9        64.9           11.6         2.5          10.0
bundle_discount            9.5        68.4           13.4         2.5           6.3
recharge_cashback         17.7        67.1            8.4         2.5           4.3
tenure_reward              6.6        65.7           14.5         2.6          10.7