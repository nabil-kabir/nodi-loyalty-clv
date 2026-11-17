# Nodi Telecom: Prepaid Loyalty & CLV Decision Engine

> **Work in progress.** Nodi Telecom is a **fictional** operator and **all data is synthetic**.

The question: *if I ran loyalty at a Bangladeshi prepaid operator with a ৳1 crore quarterly retention budget, who would I spend it on, with what offer, and how would I prove it worked?*

The full case study will replace this page when the project is complete. Until then:

- [PLAN.md](PLAN.md) covers the approach and phases.
- [ASSUMPTIONS.md](ASSUMPTIONS.md) lists every market number and its source.
- [DECISIONS.md](DECISIONS.md) logs the choices and trade-offs.

## Rebuild

```bash
py -3.14 -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows
python run.py            # full 200k-subscriber build (~8 min)
python run.py --sample   # 20k build into data_sample/
python -m pytest
```
