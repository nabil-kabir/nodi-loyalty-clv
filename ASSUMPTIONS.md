# ASSUMPTIONS: every market number, and where it comes from

**Nodi Telecom is fictional and every data point in this project is synthetic.** The numbers below set the *shape* of the synthetic world so it behaves like Bangladeshi prepaid. They are not claims about any real operator.

**Status key**
- **Sourced:** a public figure, quoted.
- **Partly sourced:** a public figure plus my own adjustment.
- **Assumption:** my judgement; no public figure found.
- **Fictional:** a deliberately invented design element.

> Sources were found by web search on 2026-11-17 and summarised from search results. Open each link and check the exact figure before quoting it in an interview.

## A. Market structure

| ID | Item | Value used | Status | Source / reasoning | Config / code |
|---|---|---|---|---|---|
| A01 | Churn definition | 90 days with no revenue event; 30 days = dormant | Partly sourced | The ITU basis for counting mobile subscribers is "90 days active". Pakistan's regulator instructed operators to report on that basis ([Dawn](https://www.dawn.com/news/amp/1192245)). Kenya's regulator counts only revenue-generating activity ([CA ICT Indicators Manual](https://www.ca.go.ke/sites/default/files/2023-06/ICT-Indicators-Manual-2020.pdf)). **BTRC's own wording is not yet verified.** | `churn.*` |
| A02 | ARPU benchmark | Target net ARPU around ৳140/month | Sourced | Robi ARPU was BDT140 in Q1 2024 and BDT142 for FY2023 ([Axiata Q1 2024](https://www.axiata.com/media/news/2024/axiata-reports-strong-operational-start-fy2024-1q24-performance-double-digit-growth)). A Grameenphone figure from search results (BDT253, Q3 2024) conflicts with older reported values, so it isn't used. | calibration |
| A03 | Division mix | Dhaka 26.9%, Chattogram 20.1%, Rajshahi 12.2%, Rangpur 10.6%, Khulna 10.5%, Mymensingh 7.4%, Sylhet 6.7%, Barishal 5.5% | Sourced | Census 2022: the first five are adjusted shares as reported in the press; the last three are from the preliminary counts ([Wikipedia: 2022 Bangladeshi census](https://en.wikipedia.org/wiki/2022_Bangladeshi_census), [TBS](https://www.tbsnews.net/bangladesh/countrys-total-population-stands-1698-crore-613834)). Assumes subscriber mix follows population. | `population.DIVISION_SHARE` |
| A04 | Urban share | About 33% urban, varying by division (Dhaka 55%) | Partly sourced | The census reports about 68% of people live in villages ([Dhaka Tribune](https://www.dhakatribune.com/bangladesh/332419/report-68%25-bangladeshis-live-in-villages)). The split by division is my assumption. | `population.URBAN_SHARE` |
| A05 | Handset tiers | About 55% smartphone (urban 70%, rural 48%); feature / low / mid / high = 45/32/17/6% | Partly sourced | GSMA 2024 puts smartphone *ownership* at 41% of urban and 26% of rural adults ([Financial Express](https://thefinancialexpress.com.bd/national/bd-bottom-among-12-lmics-in-usage-of-phone-net)). The share among active SIMs is set higher because owners skew towards being SIM holders and multi-SIM users (assumption). | `population.HANDSET_P` |
| A06 | Multi-SIM | About 55% of subscribers also hold another operator's SIM; 70–80% of handsets are dual-SIM capable | Partly sourced | GSMA reports 170m connections against 90m unique subscribers in Bangladesh (Dec 2020), about 1.9 SIMs per person ([GSMA](https://www.gsma.com/mobilefordevelopment/wp-content/uploads/2021/03/Achieving-mobile-enabled-digital-inclusion-in-Bangladesh.pdf)). The split into a per-subscriber probability is my assumption. | `population` |
| A07 | Base trend | Active base roughly flat: 129k → 133k (+3%) over 18 months | Assumption (differs from sector) | The real sector shrank in 2024: Robi's base fell 3.3% ([Daily Star](https://www.thedailystar.net/node/3826946)), and national connections fell from 196.1m (Jun 2024) to 188.7m (Nov 2024) (Daily Star, via search). A flat base keeps the retention story about *who* to save, not a market in decline. To make it shrink, lower `initial_base_share` gross adds. | `initial_base_share` |
| A08 | Acquisition channel | Retail 58–70%, activation kiosk 14–16%, care centre 10–14%, digital 4–14% | Assumption | No public split found. Kiosk (street activation drive) subscribers are given higher early churn, a common pattern for incentive-driven SIM sales. | `population.CHANNEL_P` |

## B. Recharge and usage behaviour

| ID | Item | Value (simulated, 200k build) | Status | Reasoning | Config / code |
|---|---|---|---|---|---|
| B01 | Recharge frequency | About 4.6 recharges per recharging subscriber per month | Assumption | Small, frequent top-ups are typical of BD prepaid. No public frequency figure found. | `base_recharge` |
| B02 | Recharge size | Median ৳30; about 80% of recharges are ৳50 or less | Assumption | Denominations ৳10–৳1,000. Odd amounts (৳29, ৳59…) are packs bought directly via MFS/app. | `catalog.DENOMINATIONS`, `amount_mu` |
| B03 | Recharge channel | Retailer ~55%, MFS ~37%, operator app ~8% | Assumption | MFS (bKash-style) recharge is widespread; no published channel split found. | `chan_cum` |
| B04 | Pack catalogue | 10 fictional packs (৳29–৳499; 3–30 day validity) | Fictional, within public ranges | Public reporting puts the per-GB price of BD data packs at ৳16–143 depending on the pack ([Future Startup](https://futurestartup.com/2025/09/11/how-complexity-became-telecos-most-profitable-product/)). BTRC has set minimum validities (≥3 days; [Daily Star](https://www.thedailystar.net/node/1696087)). Rules have since changed, but Nodi's catalogue stays within these bounds. | `catalog.PACKS` |
| B05 | Data usage | About 4 GB per smartphone user per month, growing about 1% per month | Assumption | Not calibrated to a public figure. | `engine` usage block |
| B06 | Seasonality | Recharges ramp to about 2× in the 7 days before Eid-ul-Fitr and about 1.5× before Eid-ul-Adha; small Pohela Boishakh bump; salary-week +7%; Friday −10% | Assumption | The direction is well known; the magnitudes are mine. | `calendar.py` |
| B07 | Festival dates | Eid-ul-Fitr 2025-03-31 / 2026-03-21; Eid-ul-Adha 2025-06-07 / 2026-05-27 | Approximate | BD dates depend on moon sighting, ±1 day. | `calendar.py` |
| B08 | Tariff shock | Fictional price increase on 2025-07-01 raises churn hazard for price-sensitive subscribers for 60 days | Fictional | Inspired by the 2024–25 increase in supplementary duty on mobile services ([Financial Express](https://today.thefinancialexpress.com.bd/print/mobile-talk-to-be-costlier-1717697907)). | `price_shock_*` |

## C. Churn and dormancy

| ID | Item | Value (simulated) | Status | Reasoning |
|---|---|---|---|---|
| C01 | Monthly churn, 90-day definition | About 3% of the active base per month | Assumption | No BD operator publishes a comparable churn rate (searched; none found). 3% per month is a judgement call for a prepaid-heavy market. |
| C02 | Reactivation | About 12% of 90-day churners recharge again later | Assumption | Migrant workers, travel and rested secondary SIMs. Plausible; no public figure. |
| C03 | Churn drivers (hidden) | Lost wallet share to a second SIM, weak network quality (by division), low engagement, short tenure, kiosk acquisition, price shock | Fictional design | These are the drivers the Phase 3 models must recover. |

## D. Economics

| ID | Item | Value | Status | Source / reasoning | Config |
|---|---|---|---|---|---|
| D01 | Net revenue per ৳1 recharged | 0.72 | Partly sourced | Mobile services carry VAT 15–18%, SD 20% and a 1% surcharge; sources differ on the exact stack ([Prothom Alo](https://en.prothomalo.com/bangladesh/emydqj4nz9), [Financial Express](https://today.thefinancialexpress.com.bd/print/mobile-talk-to-be-costlier-1717697907)). 1 / (1.20 × 1.15 × 1.01) ≈ 0.72. | `economics.net_revenue_ratio` |
| D02 | Contribution margin on net revenue | 0.78 | Partly sourced | Deducts the 5.5% BTRC revenue share and 1% SOF ([Financial Express](https://today.thefinancialexpress.com.bd/print/btrc-asks-58-tvas-licensees-to-pay-dues-to-sof-1720461338)). Also deducts about 3.5% channel commission and about 12% variable network / interconnect cost, both assumptions. **Margin on gross recharge ≈ 56%.** | `economics.contribution_margin_on_net` |
| D03 | Marginal network cost of data | ৳5 per GB | Assumption | Used to cost bonus-data offers in Phase 5 (decision 0.5). It should be tested with a sensitivity check. | `economics.network_cost_per_gb_bdt` |

## E. Planted ground truth (design choices, not market facts)

| ID | Item | Value | Notes |
|---|---|---|---|
| E01 | Offer responsiveness | Bonus data ↔ data affinity; cashback ↔ price sensitivity; tenure reward ↔ long tenure and low engagement; bundle discount ↔ pack affinity | See `engine.true_delta` |
| E02 | Sleeping dogs | 6% of subscribers have high "contact fatigue": any offer raises their churn hazard | The share is adjustable; this is business call B1.1 |
| E03 | Lost causes | Subscribers already fading out when treated get no effect; heavy multi-SIM users get weaker effects | |
| E04 | Response-group labels | Persuadable if uplift ≥ +3pp; sleeping dog if ≤ −0.5pp; sure thing if baseline churn < 8%; lost cause if baseline churn ≥ 50% | `truth_labels` |
