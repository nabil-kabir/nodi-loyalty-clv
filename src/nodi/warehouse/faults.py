"""Fault injection: prove the data-quality checks actually fire on realistic breakages."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from nodi.warehouse.build import db_path
from nodi.warehouse.dq import run_dq

FAULTS = [
    ("Same day's recharge file loaded twice",
     "INSERT INTO fct_recharge SELECT * FROM fct_recharge WHERE date = (SELECT MIN(date) FROM fct_recharge)"),
    ("A day of recharges missing (file never arrived)",
     "DELETE FROM fct_recharge WHERE date = (SELECT MIN(date) + INTERVAL 40 DAY FROM fct_recharge)"),
    ("Reversal booked as a negative recharge",
     "UPDATE fct_recharge SET gross_bdt = -gross_bdt WHERE rowid IN (SELECT rowid FROM fct_recharge LIMIT 5)"),
    ("Orphan subscriber IDs from a CRM mismatch",
     "UPDATE fct_daily_usage SET sub_id = sub_id + 10000000 WHERE rowid IN (SELECT rowid FROM fct_daily_usage LIMIT 5)"),
    ("Handset table wrong: smartphone tagged as feature phone",
     """UPDATE dim_subscriber SET handset_tier = 'feature_phone'
        WHERE sub_id IN (SELECT sub_id FROM fct_daily_usage WHERE data_mb > 0 LIMIT 3)"""),
]


def run_fault_injection(cfg: dict) -> pd.DataFrame:
    """Apply each fault to a fresh copy of the warehouse; report which checks fire."""
    src = db_path(cfg)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for label, sql in FAULTS:
            dst = Path(tmp) / "wh.duckdb"
            shutil.copyfile(src, dst)
            con = duckdb.connect(str(dst))
            con.execute(sql)
            res = run_dq(con, cfg)
            con.close()
            fired = res[res.status != "PASS"]
            rows.append({
                "fault": label,
                "caught": len(fired) > 0,
                "checks_fired": ", ".join(f"{r.name} ({r.status})" for r in fired.itertuples()) or "NONE",
            })
            dst.unlink()
    return pd.DataFrame(rows)
