# Data quality report (synthetic data)

**28 of 28 checks pass.** 0 errors, 0 warnings. Errors fail the build; warnings need investigation before the affected metrics are trusted.

| Status | Check | Category | Violations | What it guards |
|---|---|---|---:|---|
| PASS | `dim_subscriber_pk` | uniqueness | 0 | sub_id is unique in dim_subscriber |
| PASS | `fct_recharge_no_exact_duplicates` | uniqueness | 0 | No fully duplicated recharge rows (double-loaded files) |
| PASS | `fct_daily_usage_pk` | uniqueness | 0 | One usage summary per subscriber per day |
| PASS | `fct_subscriber_month_pk` | uniqueness | 0 | One snapshot row per subscriber per month |
| PASS | `recharge_fk_subscriber` | referential | 0 | Every recharge belongs to a known subscriber |
| PASS | `usage_fk_subscriber` | referential | 0 | Every usage row belongs to a known subscriber |
| PASS | `pack_fk_dim_pack` | referential | 0 | Every pack purchase is a catalogue pack |
| PASS | `exposure_fk_dim_offer` | referential | 0 | Every offer exposure is a catalogue offer (or 'none' for control) |
| PASS | `fact_dates_in_dim_date` | referential | 0 | All recharge and usage dates exist in dim_date (inside the observed window) |
| PASS | `no_null_keys` | completeness | 0 | No NULL keys or amounts in the facts |
| PASS | `every_day_has_recharges` | completeness | 0 | No missing days of recharge data (a missing file would show up here) |
| PASS | `daily_volume_anomaly` | completeness | 0 | Daily recharge count outside 60%-170% of its trailing 28-day median (festival days excluded) |
| PASS | `recharge_amount_positive` | validity | 0 | Recharge amounts are positive |
| PASS | `recharge_amount_known_denomination` | validity | 0 | Recharge amount is a standard denomination or a catalogue pack price |
| PASS | `usage_non_negative` | validity | 0 | Voice minutes, data MB and SMS counts are non-negative |
| PASS | `feature_phone_no_data` | validity | 0 | Feature-phone subscribers record no mobile data (handset data or usage feed is wrong otherwise) |
| PASS | `no_events_before_activation` | consistency | 0 | No recharge or usage before the SIM was activated |
| PASS | `direct_pack_has_purchase` | consistency | 0 | Every direct (MFS/app) pack recharge has a matching pack purchase on the same day at the same price |
| PASS | `spell_lengths_consistent` | consistency | 0 | Churn spells are >= churn_days long; dormancy spells >= dormant_days |
| PASS | `raw_vs_warehouse_rows` | reconciliation | 0 | Row counts in the warehouse equal the raw files |
| PASS | `raw_vs_warehouse_value` | reconciliation | 0 | Total gross recharge (৳) in the warehouse equals the raw files |
| PASS | `snapshot_vs_fact_revenue` | reconciliation | 0 | Monthly snapshot revenue sums to the recharge fact |
| PASS | `active_base_roll_forward` | reconciliation | 0 | Active base(m+1) = active base(m) - churners(m) + new(m) + reactivated(m), every month |
| PASS | `pilot_arms_balanced` | experiment | 0 | Randomised pilot arms differ in size by at most 1 subscriber |
| PASS | `pilot_pre_period_balance` | experiment | 0 | Pilot arms have similar pre-pilot ARPU (max/min ratio < 1.10): randomisation sanity check |
| PASS | `plausible_arpu` | plausibility | 0 | Monthly arpu within ৳50-৳500 (metrics.yml definition) |
| PASS | `plausible_churn_rate` | plausibility | 0 | Monthly churn_rate within 0.5%-10% (metrics.yml definition) |
| PASS | `plausible_recharge_frequency` | plausibility | 0 | Monthly recharge_frequency within 1-15 per month (metrics.yml definition) |

## Do the checks actually fire? (fault injection)

Each fault was planted in a fresh copy of the warehouse and the full suite re-run.

| Planted fault | Caught | Checks that fired |
|---|---|---|
| Same day's recharge file loaded twice | yes | fct_recharge_no_exact_duplicates (FAIL), daily_volume_anomaly (WARN), raw_vs_warehouse_rows (FAIL), raw_vs_warehouse_value (FAIL), snapshot_vs_fact_revenue (FAIL) |
| A day of recharges missing (file never arrived) | yes | every_day_has_recharges (FAIL), raw_vs_warehouse_rows (FAIL), raw_vs_warehouse_value (FAIL), snapshot_vs_fact_revenue (FAIL) |
| Reversal booked as a negative recharge | yes | recharge_amount_positive (FAIL), recharge_amount_known_denomination (WARN), raw_vs_warehouse_value (FAIL), snapshot_vs_fact_revenue (FAIL) |
| Orphan subscriber IDs from a CRM mismatch | yes | usage_fk_subscriber (FAIL) |
| Handset table wrong: smartphone tagged as feature phone | yes | feature_phone_no_data (WARN) |
