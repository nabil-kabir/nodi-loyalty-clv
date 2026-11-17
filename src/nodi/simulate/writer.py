"""Buffer daily event arrays and flush them as monthly Parquet partitions."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


class MonthlyWriter:
    def __init__(self, root: Path, table: str, schema: dict):
        self.dir = root / table
        self.dir.mkdir(parents=True, exist_ok=True)
        self.schema = schema  # column -> pyarrow type, or ("dict", labels) for categoricals
        self.buf: dict[str, list[np.ndarray]] = {c: [] for c in schema}
        self.month: str | None = None
        self.rows = 0

    def add(self, month: str, cols: dict[str, np.ndarray]):
        if self.month is not None and month != self.month:
            self.flush()
        self.month = month
        for c in self.schema:
            self.buf[c].append(cols[c])

    def flush(self):
        if self.month is None or not self.buf[next(iter(self.schema))]:
            return
        arrays = {}
        for c, typ in self.schema.items():
            data = np.concatenate(self.buf[c])
            if isinstance(typ, tuple) and typ[0] == "dict":
                arrays[c] = pa.DictionaryArray.from_arrays(
                    pa.array(data.astype(np.int8)), pa.array(list(typ[1])))
            else:
                arrays[c] = pa.array(data, type=typ)
        table = pa.table(arrays)
        part = self.dir / f"month={self.month}"
        part.mkdir(exist_ok=True)
        pq.write_table(table, part / "part-0.parquet", compression="zstd")
        self.rows += table.num_rows
        self.buf = {c: [] for c in self.schema}
