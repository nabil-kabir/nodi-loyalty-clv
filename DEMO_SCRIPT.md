# 90-second demo script (screen recording of the app)

**Setup:** run `streamlit run app/streamlit_app.py`, or open the deployed link. Use the browser at 1280 px wide with zoom at 100%. Start on **Executive summary**, scrolled to the top.

| Time | On screen | Say (about 220 words in total) |
|---|---|---|
| **0:00–0:10** | Executive summary. Hold on the title and the green recommendation box. | "If you had one crore taka a quarter to keep prepaid customers, who would you spend it on? Most teams pick the customers most likely to churn. That turns out to be the worst place to spend it." |
| **0:10–0:30** | Point at the plan tiles (16.6 L subscribers, ৳3.11 cr, ৳3.11 per ৳1). Click the **"Show what really happened"** toggle. | "This is a fictional operator with simulated data and a hidden ground truth. The plan sends two gigabytes of bonus data to 16.6 lakh subscribers a randomised pilot says will respond, and expects about three taka of margin back for every taka spent. Cashback to the highest-risk customers? In the hidden truth, it loses money." |
| **0:30–0:45** | **Segment explorer.** Show the bar chart, then pick **1. Fading high-value** in the dropdown. | "Here's why. This segment holds nearly a third of the margin at risk and has a 71% churn probability, yet the optimiser gives offers to only 8% of it. Most of these customers are already gone." |
| **0:45–1:05** | **Budget allocator.** Drag the budget slider from 1 to 2.5 crore, then flip **Face value** and back. Move the holdout slider. | "The allocation re-runs live. The optimiser always beats both baselines, and it stops spending once nothing pays back. Cost data at retail price instead of network cost and the answer flips to cashback, which is the assumption to agree with Finance first. A five percent holdout proves the result within one quarter." |
| **1:05–1:20** | **Campaign studio.** Show the three Bangla variants. In *Try the validator*, change ২ জিবি to ৩ জিবি: it shows **Rejected**. | "Claude writes the SMS in Bangla and English, but it never invents the facts. Change two gigabytes to three and the validator blocks it." |
| **1:20–1:30** | Back to **Executive summary**. Open *How do we know the models work?* | "Every model was checked against the planted truth, including the mistake I caught along the way. The code, the decisions and the assumptions are all on GitHub." |

**Recording tips**
- Record at 1080p and trim the dead time while pages load.
- Keep the cursor still while you talk over a number.
- The synthetic-data banner should be visible on every page. Don't crop it out.
