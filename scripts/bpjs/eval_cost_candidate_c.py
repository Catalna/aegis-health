"""Evaluasi tunggal model biaya kandidat C (v2+context) pada test riil — OFFLINE ONLY.

Replikasi PERSIS pipeline `scripts/bpjs/retrain_cost_benchmark.py` varian C:
kolom sama, filter sama (FKL48==FKL47 & >0, LOS 0..365, INACBG terisi), join
kepesertaan + diagnosis sekunder sama, split subject crc32 sama, base_rate
train-only sama, kontrak 15 fitur sama. Prediksi dibangkitkan ulang dari model
tersimpan `models/xgboost_cost_real_v2_c.json` lalu DIBANDINGKAN dengan angka
test di `retrain_results.json` (parity check) sebelum artefak ditulis.

Output (ter-ignasi, backend/app/data/analysis/):
  eval_cost_c_test.parquet  — test rows saja, tanpa PII:
    actual, pred, dialysis, terbaru, inacbg, los, sev
  eval_cost_c_parity.json   — metrik per view (baru) vs retrain_results.json (lama)

Aturan proyek: tidak menyentuh skoring runtime; kandidat menunggu gate A3.
"""
from __future__ import annotations

import json
from pathlib import Path
from zlib import crc32

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = Path(r"C:\Users\Radith\E-Jak\backend\app\data\2025\Data Sampel Reguler Edisi 2025\data")
OUT = Path(r"C:\Users\Radith\E-Jak\backend\app\data\analysis")
MODEL_PATH = OUT / "models" / "xgboost_cost_real_v2_c.json"
FEATURES_PATH = OUT / "models" / "xgboost_cost_real_v2_c_features.json"
RETRAIN_JSON = OUT / "retrain_results.json"
PARITY_JSON = OUT / "eval_cost_c_parity.json"
TEST_PARQUET = OUT / "eval_cost_c_test.parquet"

try:
    from backend.app.data.synthetic_v2.generator import DIAGNOSIS_CATALOG
    V2_DIAG_ENC = {code: float(idx) for idx, code in enumerate(DIAGNOSIS_CATALOG)}
except Exception:
    V2_DIAG_ENC = {}

CHUNK = 500_000
TEST_MOD = {8, 9}
RNG = np.random.default_rng(42)

DIAG_MAP = {"J18": 1, "J44": 2, "I21": 3, "I10": 4, "E11": 5, "K35": 6, "O80": 7, "N18": 8,
            "C50": 9, "S72": 10}
EXPECTED_LOS = {"J18": (3, 5), "J44": (4, 7), "I21": (5, 10), "I10": (2, 5), "E11": (1, 3),
                "K35": (3, 6), "O80": (2, 3), "N18": (2, 4), "C50": (5, 8), "S72": (7, 12)}
UPCODE_DIAGS = {"A41.9", "Z87.39", "E46"}
V2_FEATURES = ["primary_diag_encoded", "num_secondary_diags", "num_procedures", "patient_age",
               "num_medications", "length_of_stay", "outpatient", "icu_indicator", "ventilator_used",
               "surgical_indicator", "facility_type", "facility_class", "region",
               "severity_level", "ina_cbg_base_rate"]


def region_bucket(prov: float) -> int:
    code = int(prov) if prov == prov else -1
    if 10 <= code <= 29:
        return 0
    if 30 <= code <= 39:
        return 1
    if 50 <= code <= 59:
        return 4
    if 60 <= code <= 69:
        return 2
    if 70 <= code <= 79:
        return 3
    if 80 <= code <= 99:
        return 5
    return -1


# == 1) FKRTL subset wajar — replikasi persis retrain ==
cols = ["PSTV01", "FKL02", "FKL03", "FKL04", "FKL05_NEW", "FKL09", "FKL13", "FKL15A",
        "FKL19", "FKL20", "FKL23", "FKL31", "FKL30", "FKL47", "FKL48"]
frames, n_read = [], 0
with pd.read_stata(str(ROOT / "202403_fkrtl.dta"), columns=cols, chunksize=CHUNK,
                   convert_categoricals=False) as it:
    for ch in it:
        n_read += len(ch)
        t47 = pd.to_numeric(ch["FKL47"], errors="coerce")
        t48 = pd.to_numeric(ch["FKL48"], errors="coerce")
        keep = t48.eq(t47) & (t48 > 0)
        sub = ch.loc[keep].copy()
        los = (sub["FKL04"] - sub["FKL03"]).dt.days
        sub = sub.loc[los.between(0, 365)]
        los = los.loc[los.between(0, 365)]
        sub["los"] = los.astype("float32")
        inacbg = sub["FKL19"].fillna("").astype(str).str.strip()
        sub["inacbg"] = inacbg.where(inacbg.ne(""), np.nan)
        sub["primary3"] = sub["FKL15A"].fillna("").astype(str).str.strip()
        sub["has_proc"] = sub["FKL30"].fillna("").astype(str).str.strip().ne("").astype("float32")
        sub = sub.rename(columns={"FKL05_NEW": "prov", "FKL09": "tipe", "FKL13": "kelas",
                                  "FKL31": "reggrp", "FKL20": "grp", "FKL23": "sev",
                                  "FKL03": "svc_date", "FKL48": "cost"})
        frames.append(sub[["PSTV01", "FKL02", "svc_date", "los", "prov", "tipe", "kelas",
                           "reggrp", "inacbg", "grp", "sev", "primary3", "has_proc", "cost"]])

df = pd.concat(frames, ignore_index=True)
del frames
df["inacbg"] = df["inacbg"].astype("category")
df = df.loc[df["inacbg"].notna()].reset_index(drop=True)
print(f"[muat] diterima penuh & los 0..365: {len(df):,} dari {n_read:,}")

time_cut = pd.Timestamp(df["svc_date"].quantile(0.85))

# == 2) Kepesertaan: tahun lahir -> umur ==
pst_v01: list[str] = []
birth: list[int] = []
with pd.read_stata(str(ROOT / "2015202401_kepesertaan.dta"),
                   columns=["PSTV01", "PSTV03"], chunksize=CHUNK,
                   convert_categoricals=False) as it:
    for ch in it:
        by = pd.to_datetime(ch["PSTV03"]).dt.year
        pst_v01.extend(ch["PSTV01"].astype("int64").tolist())
        birth.extend(by.fillna(-1).astype("int16").to_numpy())

meta = pd.DataFrame({"PSTV01": pst_v01, "birth_year": birth})
meta = meta.drop_duplicates("PSTV01", keep="last")
df = df.merge(meta, on="PSTV01", how="left")
service_year = df["svc_date"].dt.year.astype("int16")
df["age"] = (service_year - df["birth_year"].astype("float32")).clip(-1, 120)
del pst_v01, birth, meta

# == 3) Diagnosis sekunder: jumlah + flag upcoding ==
sec_count: dict[str, int] = {}
sec_upcode: dict[str, int] = {}
with pd.read_stata(str(ROOT / "202405_diagnosissekunder.dta"), columns=["FKL02", "FKL24"],
                   chunksize=CHUNK, convert_categoricals=False) as it:
    for ch in it:
        k = ch["FKL02"].astype(str)
        vc = k.value_counts()
        for key, val in vc.items():
            sec_count[key] = sec_count.get(key, 0) + int(val)
        hit = k.loc[ch["FKL24"].astype(str).isin(UPCODE_DIAGS)].unique()
        for key in hit:
            sec_upcode[key] = 1

df["n_secondary"] = df["FKL02"].astype(str).map(sec_count).fillna(0).astype("float32")
df["has_upcode_diag"] = df["FKL02"].astype(str).map(sec_upcode).fillna(0.0).astype("float32")
del sec_count, sec_upcode

# == 4) Split subject-based (replikasi RNG holdout agar base_rate identik) ==
subj_hash = np.fromiter((crc32(str(s).encode()) for s in df["PSTV01"]), dtype="uint64",
                        count=len(df))
is_test = pd.Series((subj_hash % 10).astype("uint8")).isin(TEST_MOD).to_numpy()
train_idx = np.where(~is_test)[0]
hold = RNG.choice(train_idx, size=max(1, len(train_idx) // 10), replace=False)
fit_idx = np.setdiff1d(train_idx, hold, assume_unique=False)

# == 5) base_rate train-only per (INACBG, sev) — dihitung ulang (paritas penuh) ==
tr = df.iloc[fit_idx]
base_tbl = (tr.groupby(["inacbg", "sev"], observed=True)["cost"].median()
            .rename("base_rate").reset_index())
base_glob = float(tr["cost"].median())
br = df[["inacbg", "sev"]].assign(inacbg=df["inacbg"].astype(str)).merge(
    base_tbl.assign(inacbg=base_tbl["inacbg"].astype(str)), on=["inacbg", "sev"], how="left")["base_rate"]
df["base_rate"] = br.fillna(base_glob).astype("float32")

# == 6) Kontrak fitur v2 (15 fitur) ==
region_enc = df["prov"].map(region_bucket).astype("float32")
primary_enc_v2 = df["primary3"].str.split(".").str[0].map(V2_DIAG_ENC if V2_DIAG_ENC else {}).fillna(0).astype("float32")
n_sec = df["n_secondary"]
has_proc = df["has_proc"].astype("float32")
sev = df["sev"].astype("float32")
los = df["los"]
matC = np.column_stack([
    primary_enc_v2.to_numpy(), n_sec.to_numpy(), has_proc.to_numpy(),
    df["age"].astype("float32").to_numpy(),
    np.zeros(len(df), dtype="float32"),
    los.to_numpy(),
    (los == 0).astype("float32").to_numpy(),
    np.zeros(len(df), dtype="float32"),
    np.zeros(len(df), dtype="float32"),
    has_proc.to_numpy(),
    df["tipe"].astype("float32").to_numpy(),
    df["kelas"].astype("float32").to_numpy(),
    region_enc.to_numpy(),
    sev.to_numpy(),
    df["base_rate"].to_numpy(),
]).astype("float32")
names = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))["features"]
assert names == V2_FEATURES, f"kontrak fitur tidak cocok: {names}"

# == 7) Prediksi test dari model tersimpan ==
booster = xgb.Booster()
booster.load_model(str(MODEL_PATH))
pred_all = booster.predict(xgb.DMatrix(matC, feature_names=names))

y = df["cost"].to_numpy("float32")
dialysis = (df["inacbg"] == "Q-5-44-0").to_numpy()
terbaru = (df["svc_date"] >= time_cut).to_numpy()
views = {"test_semua": is_test, "test_terbaru": is_test & terbaru,
         "test_dialisis": is_test & dialysis, "test_non_dialisis": is_test & ~dialysis}


def evaluate(pred: np.ndarray, mask: np.ndarray) -> dict:
    p, a = pred[mask].astype("float64"), y[mask].astype("float64")
    err = np.abs(p - a)
    ape = err / a
    return {"n": int(mask.sum()),
            "mape_pct": round(float(ape.mean() * 100), 2),
            "medape_pct": round(float(np.median(ape) * 100), 2),
            "mae_rp": round(float(err.mean()), 0),
            "rmse_rp": round(float(np.sqrt(((p - a) ** 2).mean())), 0),
            "r2": round(float(1 - ((p - a) ** 2).sum() / ((a - a.mean()) ** 2).sum()), 4),
            "within5_pct": round(float((ape <= 0.05).mean() * 100), 1),
            "within10_pct": round(float((ape <= 0.10).mean() * 100), 1)}


fresh = {name: evaluate(pred_all, mask) for name, mask in views.items()}
old = json.loads(RETRAIN_JSON.read_text(encoding="utf-8"))["C_v2_real"]
mismatch = [(k, fresh[k], old[k]) for k in fresh if fresh[k] != old[k]]
if mismatch:
    print("[PARITAS GAGAL]", json.dumps(mismatch, indent=1))
    raise SystemExit(1)
print("[paritas] semua view cocok dengan retrain_results.json:")
for k, v in fresh.items():
    print(f"  {k:18s} MAPE {v['mape_pct']:6.2f}%  medAPE {v['medape_pct']:5.2f}%  "
          f"R2 {v['r2']:.4f}  <=5% {v['within5_pct']:5.1f}%  <=10% {v['within10_pct']:5.1f}%")

# == 8) Artefak test-only tanpa PII ==
test_rows = pd.DataFrame({
    "actual": y[is_test], "pred": pred_all[is_test],
    "dialysis": dialysis[is_test], "terbaru": terbaru[is_test],
    "inacbg": df["inacbg"].astype(str).to_numpy()[is_test],
    "los": los.to_numpy()[is_test], "sev": sev.to_numpy()[is_test],
})
test_rows.reset_index(drop=True).to_parquet(TEST_PARQUET, index=False)
PARITY_JSON.write_text(json.dumps(
    {"parity": "ok", "views": fresh, "time_cut": str(time_cut.date()),
     "model": str(MODEL_PATH.name)}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"saved -> {TEST_PARQUET.name} ({len(test_rows):,} baris), {PARITY_JSON.name}")
