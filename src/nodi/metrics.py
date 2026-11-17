"""Governed metrics layer: render and run KPI SQL from metrics.yml.

    m = Metrics(con)
    m.get("churn_rate")                                   # by month
    m.get("arpu", by=["month_start", "division"])
    m.get("incremental_revenue", by=[])                   # by experiment arm
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from nodi.config import ROOT

REF = re.compile(r"\{\{\s*(\w+)\s*\}\}")
REQUIRED = {"name", "label", "unit", "owner", "model", "definition"}


class MetricNotAvailable(RuntimeError):
    pass


class Metrics:
    def __init__(self, con: duckdb.DuckDBPyConnection, path: Path | None = None):
        self.con = con
        with open(path or ROOT / "metrics.yml", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        self.owners = spec["owners"]
        self.defs = {m["name"]: m for m in spec["metrics"]}
        self.validate()

    # ------------------------------------------------------------------ validation
    def validate(self):
        for name, m in self.defs.items():
            missing = REQUIRED - set(m)
            if missing:
                raise ValueError(f"metric {name} missing {missing}")
            if m["owner"] not in self.owners:
                raise ValueError(f"metric {name}: unknown owner {m['owner']}")
            if m.get("type", "aggregate") == "aggregate":
                if "expression" not in m:
                    raise ValueError(f"metric {name} has no expression")
                for ref in REF.findall(m["expression"]):
                    if ref not in self.defs:
                        raise ValueError(f"metric {name} references unknown metric {ref}")
                    if self.defs[ref]["model"] != m["model"]:
                        raise ValueError(f"metric {name} references {ref} on a different model")
            elif m["type"] == "experiment_lift":
                for k in ("arm_column", "control", "outcome", "scale"):
                    if k not in m:
                        raise ValueError(f"metric {name} missing {k}")
            else:
                raise ValueError(f"metric {name}: unknown type {m['type']}")

    def expression(self, name: str, _depth: int = 0) -> str:
        if _depth > 10:
            raise ValueError("circular metric reference")
        expr = self.defs[name]["expression"]
        return REF.sub(lambda mo: f"({self.expression(mo.group(1), _depth + 1)})", expr)

    def available(self, name: str) -> bool:
        model = self.defs[name]["model"]
        return bool(self.con.execute(
            "SELECT COUNT(*) FROM duckdb_tables() WHERE table_name = ? "
            "UNION ALL SELECT COUNT(*) FROM duckdb_views() WHERE view_name = ?", [model, model]
        ).df().iloc[:, 0].sum())

    # ------------------------------------------------------------------ rendering
    def sql(self, name: str, by: list[str] | tuple = ("month_start",), where: str | None = None) -> str:
        m = self.defs[name]
        if not self.available(name):
            raise MetricNotAvailable(f"{name} needs model {m['model']} (phase {m.get('available_from')})")
        by = list(by)
        conds = [c for c in (m.get("filter"), where) if c]
        wh = f"WHERE {' AND '.join(f'({c})' for c in conds)}" if conds else ""
        if m.get("type", "aggregate") == "experiment_lift":
            return self._experiment_sql(name, m, by, wh)
        dims = ", ".join(by)
        sel = f"{dims}, " if dims else ""
        grp = f"GROUP BY {dims} ORDER BY {dims}" if dims else ""
        return f"SELECT {sel}{self.expression(name)} AS {name} FROM {m['model']} {wh} {grp}"

    def _experiment_sql(self, name, m, by, wh) -> str:
        arm, ctrl = m["arm_column"], m["control"]
        dims = [d for d in by if d != arm]
        dsel = "".join(f"{d}, " for d in dims)
        join = " AND ".join([f"c.{arm} = '{ctrl}'"] + [f"t.{d} IS NOT DISTINCT FROM c.{d}" for d in dims])
        value = "(t.mean_outcome - c.mean_outcome)"
        if m["scale"] == "total":
            value += " * t.n"
        order = ", ".join([f"t.{d}" for d in dims] + [f"t.{arm}"])
        return f"""
        WITH a AS (
            SELECT {dsel}{arm}, AVG({m['outcome']}) AS mean_outcome, COUNT(*) AS n
            FROM {m['model']} {wh} GROUP BY ALL
        )
        SELECT {''.join(f't.{d}, ' for d in dims)}t.{arm}, t.n AS treated, c.n AS control_n,
               {value} AS {name}
        FROM a t JOIN a c ON {join}
        WHERE t.{arm} <> '{ctrl}' ORDER BY {order}"""

    def get(self, name: str, by=("month_start",), where: str | None = None) -> pd.DataFrame:
        return self.con.execute(self.sql(name, by, where)).df()

    def many(self, names: list[str], by=("month_start",), where: str | None = None) -> pd.DataFrame:
        """Several aggregate metrics side by side (must share dimensions)."""
        out = None
        for n in names:
            df = self.get(n, by, where)
            out = df if out is None else out.merge(df, on=list(by), how="outer")
        return out

    def catalog(self) -> pd.DataFrame:
        rows = []
        for m in self.defs.values():
            rows.append({
                "metric": m["name"], "label": m["label"], "unit": m["unit"],
                "owner": self.owners[m["owner"]], "model": m["model"],
                "type": m.get("type", "aggregate"),
                "definition": " ".join(m["definition"].split()),
                "decision": m.get("decision", ""),
                "available_from_phase": m.get("available_from", 2),
            })
        return pd.DataFrame(rows)
