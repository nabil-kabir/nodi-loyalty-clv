# Phase 1 summary (synthetic data)

## Headline numbers

- **subscribers_total**: 200,000
- **active_base_end**: 132,473
- **gross_arpu_bdt_month**: 185.076
- **net_arpu_bdt_month**: 133.255
- **recharges_per_recharger_month**: 4.552
- **median_recharge_bdt**: 30.000
- **share_recharges_le_50**: 0.812
- **monthly_churn_rate**: 0.032
- **smartphone_share**: 0.555
- **data_gb_per_smartphone_user_month**: 3.961
- **churned_spells_reactivated**: 0.113
- **mfs_share_of_recharges**: 0.371
- **truth_alive_at_end**: 126,623
- **truth_median_clv_margin_12m**: 1,024.894
- **truth_p90_clv_margin_12m**: 2,120.143
- **truth_mean_p_churn_90d**: 0.089

## Monthly KPIs (provisional SQL; governed versions arrive in Phase 2)

     month  active_base  gross_recharge  n_recharges  recharging_subs  churners  gross_arpu  recharges_per_recharger  churn_rate
2025-01-01       129397      23147959.0       514947           115597      3768  178.891002                 4.454674    0.029120
2025-02-01       129970      21218872.0       470953           114393      4658  163.259768                 4.116974    0.035839
2025-03-01       129221      26172211.0       581735           117599      4511  202.538372                 4.946768    0.034909
2025-04-01       129678      23108339.0       513954           116289      3980  178.197836                 4.419627    0.030691
2025-05-01       129793      23717262.0       527353           116626      4189  182.731442                 4.521745    0.032274
2025-06-01       129942      24089669.0       534714           117087      4142  185.387858                 4.566809    0.031876
2025-07-01       130149      23949925.0       532126           117172      4261  184.019278                 4.541409    0.032739
2025-08-01       130241      23683581.0       525551           116640      4167  181.844281                 4.505753    0.031995
2025-09-01       130579      22977479.0       509483           115216      4274  175.966112                 4.421981    0.032731
2025-10-01       130683      23771037.0       526808           115495      5153  181.898464                 4.561306    0.039431
2025-11-01       129933      23274523.0       515976           115759      5336  179.127112                 4.457329    0.041067
2025-12-01       128889      24120558.0       534107           116596      4403  187.142099                 4.580835    0.034161
2026-01-01       128868      24685281.0       545323           117265      3843  191.554777                 4.650348    0.029821
2026-02-01       129398      22118455.0       490820           116236      3479  170.933515                 4.222616    0.026886
2026-03-01       129855      27450123.0       605909           119459      3815  211.390574                 5.072108    0.029379
2026-04-01       130973      24405069.0       539648           118947      3679  186.336642                 4.536878    0.028090
2026-05-01       131543      25725733.0       570015           120386      3747  195.569000                 4.734894    0.028485
2026-06-01       132473      24381152.0       538957           120219      3743  184.046198                 4.483127    0.028255

## Offer exposures

campaign_type          offer_id     n   redeem
  bau_winback        bonus_data 29333 0.425596
  bau_winback   bundle_discount 25548 0.393690
  bau_winback recharge_cashback 88652 0.485956
  bau_winback     tenure_reward  6467 0.358899
    eid_blast        bonus_data 24754 0.435081
        pilot        bonus_data  8000 0.303750
        pilot   bundle_discount  8000 0.384000
        pilot              none  8000 0.000000
        pilot recharge_cashback  8000 0.491625
        pilot     tenure_reward  8000 0.253000

## Planted response groups (share by offer)

response_group     persuadable  sure_thing  low_responder  lost_cause  sleeping_dog
offer_id                                                                           
bonus_data                 5.1        65.3           14.8         2.6          12.3
bundle_discount            3.2        66.7           18.6         2.6           8.9
recharge_cashback          7.9        67.2           14.5         2.5           7.9
tenure_reward              2.7        65.6           16.2         2.6          13.0