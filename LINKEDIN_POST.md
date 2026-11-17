# LinkedIn post: draft for you to edit

**Attach:** `reports/linkedin/1_riskiest_not_best.png` (lead). You can optionally add charts 2–4 as a carousel.
**Word count:** 194, including hashtags (the limit you set was 200).

---

The customers most likely to churn are the worst place to spend a retention budget.

I built a loyalty decision engine for a fictional Bangladeshi prepaid operator to test that idea: 200,000 simulated subscribers over 18 months, with a hidden "ground truth" so every model can be checked against what really happened.

The question: with ৳1 crore a quarter for retention, who do you spend it on?

What I found:

• Sending cashback to the highest-risk customers lost money. Most of them were already gone in all but name.

• In a randomised pilot, offers barely moved retention. What they bought was extra top-ups.

• Targeting the people an offer actually changes is expected to return about ৳3 of margin per ৳1 spent, roughly 4× a blanket offer.

• My first uplift model over-promised by 50×. Calibrating it on held-out pilot data fixed that.

The proof plan matters as much as the model: a 5% randomised holdout, and one number for the CMO, which is net margin per taka against that holdout.

It's synthetic data, so the real test is a real operator.

Case study, code and app: [link]

#CustomerRetention #CLV #Telecom #Bangladesh #Analytics

---

**Checks before posting**
- Every number traces to the README: ৳3.11 per ৳1 (model estimate), 3.8× blanket, naive uplift ৳26.4 crore claimed vs ৳0.53 crore true (about 50×).
- The post says "expected", not "delivered", for the ৳3 figure. The ৳5.1 crore "truth" figure is from a simulation, so it isn't claimed as a real-world result.
- Replace [link] with the live app or the GitHub README.
