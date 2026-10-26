"""Dump label & dtype kolom file .dta sampel BPJS — alat bantu desain skrip (tanpa isi baris).

Pemakaian: python scripts/bpjs/dump_labels.py <nama_file.dta>
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

DATA = Path(r"C:\Users\Radith\E-Jak\backend\app\data\2025\Data Sampel Reguler Edisi 2025\data")


def main(name: str) -> None:
    f = DATA / name
    it = pd.read_stata(str(f), chunksize=1, convert_categoricals=False)
    ch = next(it)
    labels = it.variable_labels()
    it.close()
    print(f"== {name} ==")
    for col in sorted(ch.columns):
        label = labels.get(col, "")
        print(f"{col:12s} {str(ch[col].dtype):16s} {label}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("nama file .dta wajib")
    main(sys.argv[1])
