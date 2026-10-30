"""Scan sinyal cadence per-pasien dari FKRTL riil (analog L9, pra-gate, tanpa runtime).

Mengukur: distribusi gap antar-kunjungan FKRTL PER PAIREN, terpisah menurut strata
pasangan (dialisis-keduanya / non-dialisis / campuran) -> tabel usulan threshold
"near-repeat" untuk kalibrasi pilar relasional di gate A3.

Artefak -> backend/app/data/analysis/cadence_signal_scan.json (ter-ignasi).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(r"C:\Users\Radith\E-Jak\backend\app\data\2025\Data Sampel Reguler Edisi 2025\data")
AN = Path(r"C:\Users\Radith\E-Jak\backend\app\data\analysis")
CHUNK = 500_000
DIALYSIS = "Q-5-44-0"

BUCKET_LABELS = ["0_hari_sama", "1-3", "4-7", "8-14", "15-30", "31-60", "61+"]
BUCKET_EDGES = np.array([1, 4, 8, 15, 31, 61, 10 ** 9])
STRATA = ("dialisis_keduanya", "non_dialisis_keduanya", "campuran")


def bucket_counts(g: np.ndarray) -> np.ndarray:
    out = np.zeros(len(BUCKET_LABELS), dtype=np.int64)
    out[0] = int((g == 0).sum())
    idx = np.digitize(g[g > 0], BUCKET_EDGES[: len(BUCKET_LABELS) - 1], right=True)
    np.add.at(out[1:], np.minimum(idx, len(BUCKET_LABELS) - 2), 1)
    return out


def main() -> dict:
    frames = []
    with pd.read_stata(str(DATA / "202403_fkrtl.dta"), columns=["PSTV01", "FKL03", "FKL19"],
                       chunksize=CHUNK, convert_categoricals=False) as it:
        for ch in it:
            f = pd.DataFrame({
                "pid": ch["PSTV01"].astype("int64"),
                "date_ord": ch["FKL03"].values.astype("datetime64[D]").astype("int64"),
                "dial": ch["FKL19"].astype(str).str.strip().eq(DIALYSIS),
            })
            frames.append(f)
    t = pd.concat(frames, ignore_index=True)
    del frames
    t = t.sort_values(["pid", "date_ord", "dial"], kind="stable")
    pid = t["pid"].to_numpy()
    dates = t["date_ord"].to_numpy()
    dial = t["dial"].to_numpy()
    same = pid[1:] == pid[:-1]
    gaps = dates[1:] - dates[:-1]
    pair_mask = same & (gaps >= 0)
    g = gaps[pair_mask]
    d_left = dial[:-1][pair_mask]
    d_right = dial[1:][pair_mask]
    both = d_left & d_right
    mixed = d_left ^ d_right
    neither = ~d_left & ~d_right
    n_patients = int(len(np.unique(pid)))

    res = {
        "meta": {
            "tujuan": "baseline cadence FKRTL per strata pasangan -> usulan threshold near-repeat (pra-gate A3)",
            "pasangan": "pasangan kunjungan berurutan FKRTL per peserta (terurut tanggal)",
            "baris_fkrtl": int(len(t)),
            "pasien_unik": n_patients,
        },
        "pasangan_total": int(len(g)),
    }
    strata_masks = {"dialisis_keduanya": both, "non_dialisis_keduanya": neither, "campuran": mixed}
    for name, m in strata_masks.items():
        gs = g[m]
        arr = bucket_counts(gs)
        shares = [round(float(v / max(1, arr.sum()) * 100), 2) for v in arr]
        q = [int(np.percentile(gs, p)) if len(gs) else None for p in (10, 25, 50, 75, 90, 99)]
        res[name] = {
            "n_pasangan": int(len(gs)),
            "share_dari_pasangan_pct": round(float(len(gs) / max(1, len(g)) * 100), 2),
            "gap_p10_25_50_75_90_99": q,
            "bucket_share_pct": dict(zip(BUCKET_LABELS, shares)),
        }
    out = AN / "cadence_signal_scan.json"
    out.write_text(json.dumps(res, ensure_ascii=True, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=True, indent=1))
    print(f"\nsaved -> {out}")
    return res


if __name__ == "__main__":
    main()
