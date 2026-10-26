"""Profil perilaku peserta dari sampel Reguler BPJS — HANYA AGREGAT, tanpa PII.

Mengukur (dari file FKTP + FKRTL):
 1. kunjungan per peserta per jalur (distribusi)
 2. gap antar-kunjungan (FKTP & FKRTL terpisah) + bucket
 3. cadence hemodialisis (Q-5-44-0): kunjungan/pasien + distribusi gap (ekspektasi ~14 hari)
 4. penutupan rujukan: FKP02 (FKRTL) vs ID kunjungan FKTP (FKP02 di file FKTP)
 5. pasangan hari-sama FKTP->FKRTL (hash pasangan pasien+tanggal)
 6. switch stratum (prov, tipe faskes) per peserta (FKTP)

Identifier di-hash (crc32), tidak pernah dicetak; konsep diharapkan konsisten in-run.
Artefak -> backend/app/data/analysis/profile_behavioral.json (ter-ignasi).
"""
from __future__ import annotations

import json
from pathlib import Path
from zlib import crc32

import numpy as np
import pandas as pd

ROOT = Path(r"C:\Users\Radith\E-Jak\backend\app\data\2025\Data Sampel Reguler Edisi 2025\data")
OUT_DIR = Path(r"C:\Users\Radith\E-Jak\backend\app\data\analysis")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CHUNK = 500_000
BUCKETS = [0, 1, 4, 15, 31, 61, 10**9]
BUCKET_LABELS = ["0_hari-sama", "1-3", "4-14", "15-30", "31-60", "61+"]


def id_hash(s: pd.Series) -> np.ndarray:
    values = s.fillna("").astype(str).str.strip()
    mask = values.ne("")
    return np.fromiter((crc32(x.encode()) for x in values[mask]), dtype="uint64", count=int(mask.sum()))


def pair_hash(pid: np.ndarray, date_ord: np.ndarray) -> np.ndarray:
    return pid.astype("uint64") * 1_000_000 + date_ord.astype("uint64")


def gap_bucket(g: np.ndarray) -> dict:
    out = {"n": int(len(g)), "p10_p50_p90_p99": [int(np.percentile(g, q)) for q in (10, 50, 90, 99)]}
    for i, lab in enumerate(BUCKET_LABELS):
        out[lab] = round(float(((g >= BUCKETS[i]) & (g < BUCKETS[i + 1])).mean() * 100), 2)
    return out


def sebaran_kunjungan(counts: np.ndarray) -> dict:
    return {
        "pasien_unik": int(len(counts)),
        "per_pasien_p50_p90_p99_max": [int(np.percentile(counts, q)) for q in (50, 90, 99)]
        + [int(counts.max()) if len(counts) else 0],
        "share_pasien_ge2_pct": round(float((counts >= 2).mean() * 100), 2),
    }


def load_frame(fname: str, rename: dict) -> pd.DataFrame:
    frames = []
    with pd.read_stata(str(ROOT / fname), columns=list(rename), chunksize=CHUNK,
                       convert_categoricals=False) as it:
        for ch in it:
            frames.append(ch.rename(columns=rename))
    df = pd.concat(frames, ignore_index=True)
    del frames
    n0 = len(df)
    df = df.loc[df["tgl"].notna()].copy()
    df["pid"] = df["pid"].astype("int64")
    df["date_ord"] = df["tgl"].values.astype("datetime64[D]").astype("int64")
    df = df.drop(columns=["tgl"])
    print(f"[muat] {fname}: {n0:,} baris ({n0 - len(df):,} tanpa tgl dikeluarkan)")
    return df


def gaps(df: pd.DataFrame) -> np.ndarray:
    df = df.sort_values(["pid", "date_ord"], kind="stable")
    same = df["pid"].to_numpy()[1:] == df["pid"].to_numpy()[:-1]
    g = df["date_ord"].to_numpy()[1:] - df["date_ord"].to_numpy()[:-1]
    return g[same & (g >= 0)]


def main() -> dict:
    res: dict = {"meta": {"sumber": "Data Sampel Reguler Edisi 2025",
                          "proses": "agregat; identifier crc32-hash, tidak pernah dicetak"}}

    # ---- FKTP ----
    t = load_frame("202402_fktpkapitasi.dta",
                   {"PSTV01": "pid", "FKP02": "cid", "FKP03": "tgl", "FKP05_NEW": "prov",
                    "FKP09": "tipe", "FKP22": "jenis"})
    n_fktp = len(t)
    counts_t = t.groupby("pid", sort=False).size().to_numpy()
    res["fktp"] = {"kunjungan": int(n_fktp), **sebaran_kunjungan(counts_t)}
    res["fktp"]["jenis_kunjungan_mix"] = {str(k): int(v) for k, v in t["jenis"].value_counts().head(5).items()}

    t["tipe_key"] = t["prov"].astype("int64") * 1000 + t["tipe"].astype("int64")
    t_sorted = t.sort_values(["pid", "date_ord"], kind="stable")
    pid_arr = t_sorted["pid"].to_numpy()
    first_pos = np.ones(len(t_sorted), dtype=bool)
    first_pos[1:] = pid_arr[1:] != pid_arr[:-1]
    # pasangkan tipe_key pertama tiap pasien ke seluruh barisnya
    first_key_per_pid = pd.Series(t_sorted["tipe_key"].to_numpy()[first_pos], index=pid_arr[first_pos])
    row_first = first_key_per_pid.reindex(t_sorted["pid"].to_numpy()).to_numpy()
    diverge = t_sorted["tipe_key"].to_numpy() != row_first
    divergent_patients = int(pd.Series(diverge).groupby(pid_arr).any().sum())
    res["fktp"]["share_pasien_switch_stratum_pct"] = round(float(divergent_patients / len(counts_t) * 100), 2)

    res["fktp"]["gap_antar_kunjungan"] = gap_bucket(gaps(t))

    fktp_ids = np.unique(id_hash(t["cid"]))
    pair_fktp = np.unique(pair_hash(t["pid"].to_numpy(), t["date_ord"].to_numpy()))
    t = None

    # ---- FKRTL ----
    r = load_frame("202403_fkrtl.dta",
                   {"PSTV01": "pid", "FKL03": "tgl", "FKL19": "inacbg", "FKL05_NEW": "prov",
                    "FKL09": "tipe"})
    n_fkrtl = len(r)
    counts_r = r.groupby("pid", sort=False).size().to_numpy()
    res["fkrtl"] = {"kunjungan": int(n_fkrtl), **sebaran_kunjungan(counts_r)}
    res["fkrtl"]["gap_antar_kunjungan"] = gap_bucket(gaps(r))

    dial = r.loc[r["inacbg"].astype(str).str.strip().eq("Q-5-44-0")].copy()
    n_dial = len(dial)
    counts_d = dial.groupby("pid", sort=False).size().to_numpy()
    g_dial_main = gaps(dial)
    g_dial = g_dial_main[g_dial_main <= 60]
    res["hemodialisis"] = {
        "kunjungan": int(n_dial),
        "share_fkrtl_pct": round(float(n_dial / n_fkrtl * 100), 2),
        **sebaran_kunjungan(counts_d),
        "gap_dialisis": gap_bucket(g_dial),
        "share_gap_12_16d_pct": round(float(((g_dial >= 12) & (g_dial <= 16)).mean() * 100), 2),
    }
    r = None

    # ---- rujukan: FKP02 (FKRTL) vs ID FKTP ----
    refs = {}
    with pd.read_stata(str(ROOT / "202403_fkrtl.dta"), columns=["FKP02"], chunksize=CHUNK,
                       convert_categoricals=False) as it:
        parts, n_rows = [], 0
        for ch in it:
            n_rows += len(ch)
            parts.append(id_hash(ch["FKP02"]))
    ref_hash = np.concatenate(parts) if parts else np.array([], dtype="uint64")
    ref_unique = np.unique(ref_hash)
    matched = np.intersect1d(ref_unique, fktp_ids, assume_unique=True)
    res["rujukan_fktp_ke_fkrtl"] = {
        "baris_fkrtl_dgn_asal_rujukan": int(len(ref_hash)),
        "share_fkrtl_pct": round(float(len(ref_hash) / n_fkrtl * 100), 2),
        "origin_unik": int(len(ref_unique)),
        "origin_ada_di_fktp_pct": round(float(len(matched) / max(1, len(ref_unique)) * 100), 2),
        "share_fktp_yang_dirujuk_pct": round(float(len(matched) / max(1, len(fktp_ids)) * 100), 2),
    }

    # ---- hari-sama FKTP->FKRTL ----
    pairs_r = []
    with pd.read_stata(str(ROOT / "202403_fkrtl.dta"), columns=["PSTV01", "FKL03"],
                       chunksize=CHUNK, convert_categoricals=False) as it:
        for ch in it:
            pid = ch["PSTV01"].astype("int64").to_numpy().astype("uint64")
            dord = ch["FKL03"].values.astype("datetime64[D]").astype("int64").astype("uint64")
            pairs_r.append(pair_hash(pid, dord))
    pair_fkrtl = np.unique(np.concatenate(pairs_r))
    same_day = int(np.intersect1d(pair_fkrtl, pair_fktp, assume_unique=True).size)
    res["hari_sama_fktp_fkrtl"] = {
        "pasangan_unik_fktp": int(len(pair_fktp)),
        "fkrtl_berpasangan_hari_sama": same_day,
        "share_fkrtl_pct": round(float(same_day / n_fkrtl * 100), 2),
    }

    print(f"[ringkas] FKTP {n_fktp:,} / {len(counts_t):,} pasien | FKRTL {n_fkrtl:,} / {len(counts_r):,} | "
          f"dialisis {n_dial:,} ({len(counts_d):,} pasien) | rujukan {len(ref_hash):,} | "
          f"hari-sama {same_day:,}")
    return res


if __name__ == "__main__":
    payload = main()
    out = OUT_DIR / "profile_behavioral.json"
    out.write_text(json.dumps(payload, ensure_ascii=True, indent=1, default=str), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True, indent=1, default=str))
    print(f"\nsaved -> {out}")
