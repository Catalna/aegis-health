"""Scan karakteristik operasi sinyal deviasi-vs-peer pada subset wajar (PRA-GATE, evaluasi saja).

TIDAK mengubah runtime apa pun. Bukan validasi fraud (data tidak punya label fraud):
ini mengukur "kalau threshold X dipakai, berapa klaim/ke % yang akan ditandai?" —
input untuk penetapan threshold gate A3 pasca-1-Nov.

Metode:
 - benchmark = median peer per sel (prov × tipe faskes × INACBG × sev) dari
   `peer_baseline_reguler_main.csv` (n >= 10), fallback `(INACBG × sev)` n >= 10,
   terakhir median global (aproksimasi weighted-median per n dari file fallback).
 - subset wajar: FKL47 == FKL48 (klaim tarked sama dengan terverif).
 - rasio r = biaya/median; band: <0.5, 0.5-0.9, 0.9-1.1, 1.1-1.25, 1.25-1.5, 1.5-2, >=2.

Artefak -> backend/app/data/analysis/peer_signal_scan.json (ter-ignasi). Tanpa PII.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from numpy import nan

DATA = Path(r"C:\Users\Radith\E-Jak\backend\app\data\2025\Data Sampel Reguler Edisi 2025\data")
AN = Path(r"C:\Users\Radith\E-Jak\backend\app\data\analysis")
CHUNK = 500_000
N_MIN = 10
EDGES = np.array([0.5, 0.9, 1.1, 1.25, 1.5, 2.0, 10 ** 9])
BUCKET_LABELS = ["<0.5", "0.5-0.9", "0.9-1.1", "1.1-1.25", "1.25-1.5", "1.5-2.0", ">=2"]
DIALYSIS = "Q-5-44-0"


def load_lookups() -> tuple[dict, dict, float]:
    main: dict[str, float] = {}
    m = pd.read_csv(AN / "peer_baseline_reguler_main.csv")
    keep = m.loc[m["n"] >= N_MIN]
    for prov, tipe, cbg, sev, med in zip(keep["FKL05_NEW"], keep["FKL09"], keep["FKL19"].astype(str),
                                         keep["FKL23"], keep["median"]):
        main[f"{int(prov)}|{int(tipe)}|{cbg.strip()}|{int(sev)}"] = float(med)
    fb_rows = pd.read_csv(AN / "peer_baseline_reguler_fallback.csv")
    fallback: dict[str, float] = {}
    for cbg, sev, med in zip(fb_rows["FKL19"].astype(str), fb_rows["FKL23"], fb_rows["median"]):
        fallback[f"{cbg.strip()}|{int(sev)}"] = float(med)
    # median global = weighted-median dari median-level-fallback, dibobot n
    order = np.argsort(fb_rows["median"].to_numpy())
    meds = fb_rows["median"].to_numpy()[order]
    wts = fb_rows["n"].to_numpy()[order].astype(float)
    cum = np.cumsum(wts) / wts.sum()
    global_median = float(meds[np.searchsorted(cum, 0.5)])
    return main, fallback, global_median


def main() -> dict:
    main_lk, fb_lk, g_med = load_lookups()
    counts = np.zeros(len(BUCKET_LABELS), dtype=np.int64)
    strata = {k: np.zeros(len(BUCKET_LABELS), dtype=np.int64) for k in ("dialisis", "non-dialisis")}
    thr_rows = np.zeros(4, dtype=np.int64)  # 1.1 1.25 1.5 2.0
    cell_flag = Counter()
    n_wajar = n_no_src = 0
    r_stats = []  # simpan rasio non-dialisis utk persentil ringkas (per chunk)

    with pd.read_stata(str(DATA / "202403_fkrtl.dta"),
                       columns=["FKL05_NEW", "FKL09", "FKL19", "FKL23", "FKL47", "FKL48"],
                       chunksize=CHUNK, convert_categoricals=False) as it:
        for ch in it:
            w = ch.loc[ch["FKL47"].astype(float) == ch["FKL48"].astype(float)]
            if w.empty:
                continue
            n_wajar += len(w)
            cbg = w["FKL19"].astype(str).str.strip()
            sev = w["FKL23"].astype(int)
            key_main = [f"{int(p)}|{int(t)}|{c}|{s}"
                        for p, t, c, s in zip(w["FKL05_NEW"].astype(int), w["FKL09"].astype(int), cbg, sev)]
            is_dial = cbg.eq(DIALYSIS).to_numpy()
            meds = np.empty(len(w), dtype=float)
            for i, k in enumerate(key_main):
                v = main_lk.get(k)
                if v is None:
                    v = fb_lk.get(f"{cbg.iloc[i]}|{sev.iloc[i]}", None)
                if v is None:
                    meds[i] = nan
                    n_no_src += 1
                else:
                    meds[i] = v
            ok = np.isfinite(meds)
            r_all = w["FKL47"].to_numpy()[ok].astype(float) / meds[ok]
            b = np.digitize(r_all, EDGES, right=True)
            np.add.at(counts, b, 1)
            np.add.at(strata["dialisis"], b[is_dial[ok]], 1)
            np.add.at(strata["non-dialisis"], b[~is_dial[ok]], 1)
            for j, thr in enumerate((1.1, 1.25, 1.5, 2.0)):
                thr_rows[j] += int((r_all >= thr).sum())
            flagged = (~is_dial[ok]) & (b >= 3)  # r >= 1.25, hanya non-dialisis agar tidak berisik tarif-terkunci
            if flagged.any():
                for c, s in zip(cbg.to_numpy()[ok][flagged], sev.to_numpy()[ok][flagged]):
                    cell_flag[f"{c}|{int(s)}"] += 1
            if (~is_dial[ok]).any():
                r_stats.append(r_all[~is_dial[ok]])

    r_nd = np.concatenate(r_stats)
    res = {
        "meta": {
            "tujuan": "karakteristik operasi sinyal deviasi-vs-peer (pra-gate); BUKAN validasi fraud",
            "subset": "FKL47 == FKL48 (wajar)",
            "benchmark": "median main n>=10 -> fallback n>=10 -> global(weighted)",
            "global_median_rp": g_med,
            "baris_tanpa_sumber_benchmark": n_no_src,
        },
        "baris_wajar": int(n_wajar),
        "band_share_pct": {lab: round(float(counts[i] / max(1, n_wajar) * 100), 2)
                           for i, lab in enumerate(BUCKET_LABELS)},
        "band_share_pct_per_strata": {st: {lab: round(float(arr[i] / max(1, arr.sum()) * 100), 2)
                                          for i, lab in enumerate(BUCKET_LABELS)}
                                      for st, arr in strata.items()},
        "threshold_naik": {"1.10": int(thr_rows[0]), "1.25": int(thr_rows[1]),
                           "1.50": int(thr_rows[2]), "2.00": int(thr_rows[3])},
        "threshold_naik_share_pct": {t: round(float(int(thr_rows[j]) / max(1, n_wajar) * 100), 2)
                                     for j, t in enumerate(("1.10", "1.25", "1.50", "2.00"))},
        "rasio_non_dialisis_p50_p90_p99": [float(np.percentile(r_nd, q)) for q in (50, 90, 99)],
        "top_cell_non_dialisis_flagged_ge1_25": [
            {"inacbg_sev": k, "n_flag": v} for k, v in cell_flag.most_common(15)],
    }
    out = AN / "peer_signal_scan.json"
    out.write_text(json.dumps(res, ensure_ascii=True, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=True, indent=1))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
