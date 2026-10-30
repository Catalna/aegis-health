"""Ekstraksi peer baseline biaya dari FKRTL Paket Reguler (hanya agregat).

Subset wajar: FKL47 == FKL48 (diterima penuh tanpa potongan) dan FKL48 > 0.
Output (ke backend/app/data/analysis/, ter-ignasi; tanpa identifier perorangan):
- peer_baseline_reguler_main.csv     (prov x tipe faskes x INACBG x severitas)
- peer_baseline_reguler_fallback.csv (INACBG x severitas, nasional)
- peer_baseline_reguler_kelas.csv    (INACBG x severitas x kelas rawat, nasional)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\Radith\E-Jak\backend\app\data\2025\Data Sampel Reguler Edisi 2025\data\202403_fkrtl.dta")
OUT_DIR = Path(r"C:\Users\Radith\E-Jak\backend\app\data\analysis")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COLS = ["FKL05_NEW", "FKL09", "FKL13", "FKL19", "FKL23", "FKL47", "FKL48"]
CHUNK = 500_000
QUANT = [0.25, 0.5, 0.75, 0.9]
QLAB = ["q25", "median", "q75", "p90"]

frames = []
n_read = n_no_code = 0
with pd.read_stata(str(ROOT), columns=COLS, chunksize=CHUNK, convert_categoricals=False) as it:
    for ch in it:
        n_read += len(ch)
        t47 = pd.to_numeric(ch["FKL47"], errors="coerce")
        t48 = pd.to_numeric(ch["FKL48"], errors="coerce")
        keep = t48.eq(t47) & (t48 > 0)
        sub = ch.loc[keep].copy()
        bad = sub["FKL19"].astype(str).str.strip().isin(["", "nan", "None"])
        n_no_code += int(bad.sum())
        frames.append(sub.loc[~bad, COLS])

df = pd.concat(frames, ignore_index=True)
df["FKL19"] = df["FKL19"].astype("category")
total = len(df)
print(f"baris wajar: {total:,} dari {n_read:,} ({total / n_read:.2%}); dikeluarkan tanpa kode inacbg: {n_no_code:,}")


def build(keys, fname) -> pd.DataFrame:
    g = df.groupby(keys, observed=True)["FKL48"]
    q = g.quantile(QUANT).unstack()
    q.columns = QLAB
    out = pd.concat([g.size().rename("n"), g.mean().rename("mean"), q], axis=1).reset_index()
    out = out.sort_values("n", ascending=False)
    out.to_csv(OUT_DIR / fname, index=False)
    return out


main = build(["FKL05_NEW", "FKL09", "FKL19", "FKL23"], "peer_baseline_reguler_main.csv")
fallback = build(["FKL19", "FKL23"], "peer_baseline_reguler_fallback.csv")
kelas = build(["FKL19", "FKL23", "FKL13"], "peer_baseline_reguler_kelas.csv")

print("\n== cakupan sel (pangsa baris yang berada pada sel dengan n >= ambang) ==")
for name, tab in (("__utama", main), ("_fallback", fallback)):
    print(f"granularitas{name}: {len(tab):,} sel")
    for thr in (5, 10, 30):
        dense = tab[tab["n"] >= thr]
        print(f"  n>={thr}: {len(dense):,} sel, tercakup {dense['n'].sum() / total:.1%} baris")

print("\n== klasifikasi 10 sel utama terbesar ==")
print(main.head(10)[["FKL05_NEW", "FKL09", "FKL19", "FKL23", "n", "median", "q25", "q75"]].to_string(index=False))
print(f"\nsaved -> {OUT_DIR}")
