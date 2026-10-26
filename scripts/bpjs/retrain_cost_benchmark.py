"""Retraining benchmark biaya pada data riil BPJS Reguler — OFFLINE ONLY.

Aturan proyek: skoring runtime FROZEN sampai 1 Nov; hasil ini artefak kandidat,
promosi hanya lewat gate A3 (ablation) sesuai docs/MODELS.md. Tanpa PII di output.

Tiga varian diuji pada test-set subject-split yang sama:
  A. Model runtime LEGACY (backend/models_trained/xgboost_regressor.json) diuji
     dengan fitur kontrak legacy (COST_FEATURE_NAMES) yang dibangun dari data riil.
  B. Kontrak legacy sama, dilatih ulang di data riil -> isolasi "model vs distribusi".
  C. Kontrak konteks v2 (v2_features.build_cost_features, 15 fitur) dilatih ulang
     di data riil. Provenance nilai riil/proxy/konstanta-gap tercatat.

Subset wajar: FKL47 == FKL48 & FKL48 > 0 (klaim diterima penuh).
Split: subject-based, crc32(PSTV01) % 10 in {8,9} = test; pasien tak lintas split.
View tambahan: test terbaru (FKL03 >= kuantil-85 tanggal layanan), strata
hemodialisis (Q-5-44-0) vs lainnya, shares within ±5%/±10%.

Feature C: patient_age = tahun layanan - tahun lahir (join kepesertaan, riil)
          icu_indicator/ventilator_used/num_medications = KONSTANTA 0 (gap terdeklarasi)
          surgical_indicator & num_procedures = FKL30 terisi (proxy presence)
          outpatient = LOS == 0 (proxy day-care)
          facility_type = kode FKL09; facility_class = FKL13; region = bucket 6 area
          ina_cbg_base_rate = median TRAIN-only per (INACBG x severitas), unseen -> median nasional.

Artefak -> backend/app/data/analysis/ (ter-ignasi):
  retrain_results.json, base_rate_trainonly.csv, models/xgboost_cost_real_*.json
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
MODELS_OUT = OUT / "models"
MODELS_OUT.mkdir(parents=True, exist_ok=True)
LEGACY_MODEL = Path(r"C:\Users\Radith\E-Jak\backend\models_trained\xgboost_regressor.json")

try:  # parity dengan v2_features._DIAGNOSIS (katalog generator synthetic v2)
    from backend.app.data.synthetic_v2.generator import DIAGNOSIS_CATALOG
    V2_DIAG_ENC = {code: float(idx) for idx, code in enumerate(DIAGNOSIS_CATALOG)}
except Exception:  # bila import gagal → katalog tidak dikenal; dukdustri: enc = 0 semua
    V2_DIAG_ENC = {}

CHUNK = 500_000
TEST_MOD = {8, 9}
RNG = np.random.default_rng(42)

DIAG_MAP = {"J18": 1, "J44": 2, "I21": 3, "I10": 4, "E11": 5, "K35": 6, "O80": 7, "N18": 8,
            "C50": 9, "S72": 10}
EXPECTED_LOS = {"J18": (3, 5), "J44": (4, 7), "I21": (5, 10), "I10": (2, 5), "E11": (1, 3),
                "K35": (3, 6), "O80": (2, 3), "N18": (2, 4), "C50": (5, 8), "S72": (7, 12)}
UPCODE_DIAGS = {"A41.9", "Z87.39", "E46"}
LEGACY_FEATURES = [
    "primary_diag_encoded", "num_secondary_diags", "num_procedures", "num_medications",
    "severity_level", "length_of_stay", "has_high_cost_proc", "has_phantom_risk_proc",
    "has_upcoding_risk_diag", "severity_proc_mismatch", "severity_med_mismatch",
    "los_outlier", "num_total_codes", "proc_count_ratio", "medication_count"]
V2_FEATURES = [
    "primary_diag_encoded", "num_secondary_diags", "num_procedures", "patient_age",
    "num_medications", "length_of_stay", "outpatient", "icu_indicator", "ventilator_used",
    "surgical_indicator", "facility_type", "facility_class", "region",
    "severity_level", "ina_cbg_base_rate"]


def region_bucket(prov: float) -> int:
    code = int(prov) if prov == prov else -1
    if 10 <= code <= 29:
        return 0   # sumatra
    if 30 <= code <= 39:
        return 1   # java
    if 50 <= code <= 59:
        return 4   # bali_nusa
    if 60 <= code <= 69:
        return 2   # kalimantan
    if 70 <= code <= 79:
        return 3   # sulawesi
    if 80 <= code <= 99:
        return 5   # maluku_papua
    return -1


# ===========================================================================
# 1) FKRTL subset wajar
# ===========================================================================
cols = ["PSTV01", "FKL02", "FKL03", "FKL04", "FKL05_NEW", "FKL09", "FKL13", "FKL15A",
        "FKL19", "FKL20", "FKL23", "FKL31", "FKL30", "FKL47", "FKL48"]
frames, n_read, n_no_code, n_bad_los = [], 0, 0, 0
with pd.read_stata(str(ROOT / "202403_fkrtl.dta"), columns=cols, chunksize=CHUNK,
                   convert_categoricals=False) as it:
    for ch in it:
        n_read += len(ch)
        t47 = pd.to_numeric(ch["FKL47"], errors="coerce")
        t48 = pd.to_numeric(ch["FKL48"], errors="coerce")
        keep = t48.eq(t47) & (t48 > 0)
        sub = ch.loc[keep].copy()
        los = (sub["FKL04"] - sub["FKL03"]).dt.days
        ok_los = los.between(0, 365)
        n_bad_los += int((~ok_los).sum())
        sub = sub.loc[ok_los]
        sub["los"] = los.loc[ok_los].astype("float32")
        inacbg = sub["FKL19"].fillna("").astype(str).str.strip()
        n_no_code += int(inacbg.eq("").sum())
        sub["inacbg"] = inacbg.where(inacbg.ne(""), np.nan)
        sub["primary3"] = sub["FKL15A"].fillna("").astype(str).str.strip()
        sub["has_proc"] = sub["FKL30"].fillna("").astype(str).str.strip().ne("").astype("float32")
        sub = sub.rename(columns={"FKL05_NEW": "prov", "FKL09": "tipe", "FKL13": "kelas",
                                  "FKL31": "reggrp", "FKL20": "grp", "FKL23": "sev",
                                  "FKL03": "svc_date", "FKL48": "cost"})
        keep_cols = ["PSTV01", "FKL02", "svc_date", "los", "prov", "tipe", "kelas",
                     "reggrp", "inacbg", "grp", "sev", "primary3", "has_proc", "cost"]
        frames.append(sub[keep_cols])

df = pd.concat(frames, ignore_index=True)
del frames
df["inacbg"] = df["inacbg"].astype("category")
df = df.loc[df["inacbg"].notna()].reset_index(drop=True)
print(f"[muat] diterima penuh & los 0..365: {len(df):,} dari {n_read:,} (buang los: {n_bad_los:,}; "
      f"kdg-cbg kosong: {n_no_code:,})")
print(f"[muat] rentang layanan: {df['svc_date'].min()} .. {df['svc_date'].max()}")

# ===========================================================================
# 2) Kepesertaan: tahun lahir & jenis kelamin (kemudian umur)
# ===========================================================================
pst_v01: list[str] = []
birth: list[int] = []
sex: list[int] = []
with pd.read_stata(str(ROOT / "2015202401_kepesertaan.dta"),
                   columns=["PSTV01", "PSTV03", "PSTV05"], chunksize=CHUNK,
                   convert_categoricals=False) as it:
    for ch in it:
        by = pd.to_datetime(ch["PSTV03"]).dt.year
        pst_v01.extend(ch["PSTV01"].astype("int64").tolist())
        birth.extend(by.fillna(-1).astype("int16").to_numpy())
        sex.extend(pd.to_numeric(ch["PSTV05"], errors="coerce").fillna(-1).astype("int8").to_numpy())

meta = pd.DataFrame({"PSTV01": pst_v01, "birth_year": birth, "sex_code": sex})
n_meta = len(meta)
meta = meta.drop_duplicates("PSTV01", keep="last")
df = df.merge(meta, on="PSTV01", how="left")
service_year = df["svc_date"].dt.year.astype("int16")
df["age"] = (service_year - df["birth_year"].astype("float32")).clip(-1, 120)
age_hit = float(df["age"].notna().mean())
print(f"[join peserta] baris meta {n_meta:,} -> unik {len(meta):,}; umur terisi {age_hit:.1%}")
del pst_v01, birth, sex, meta

# ===========================================================================
# 3) Diagnosis sekunder: jumlah per klaim + flag kode risiko upcoding
# ===========================================================================
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
sec_hit = float(df["n_secondary"].gt(0).mean())
print(f"[join dx sekunder] klaim yang punya >=1 dx sekunder: {sec_hit:.1%}; "
      f"baris dx: {sum(sec_count.values()):,}")
del sec_count, sec_upcode

# ===========================================================================
# 4) Split subject-based (crc32(PSTV01)%10) — TANPA mem-print id
# ===========================================================================
subj_hash = np.fromiter((crc32(str(s).encode()) for s in df["PSTV01"]), dtype="uint64",
                        count=len(df))
is_test = pd.Series((subj_hash % 10).astype("uint8")).isin(TEST_MOD).to_numpy()
train_idx = np.where(~is_test)[0]
test_idx = np.where(is_test)[0]
# holdout internal untuk early stopping (10% train acak, tetap di dalam train)
hold = RNG.choice(train_idx, size=max(1, len(train_idx) // 10), replace=False)
fit_idx = np.setdiff1d(train_idx, hold, assume_unique=False)
print(f"[split] train/fit {len(fit_idx):,} + holdout {len(hold):,} + test {len(test_idx):,} "
      f"(subjek tak lintas)")

# ===========================================================================
# 5) base_rate proxy — median TRAIN-ONLY per (INACBG, severitas)
# ===========================================================================
tr = df.iloc[fit_idx]
base_tbl = (tr.groupby(["inacbg", "sev"], observed=True)["cost"].median()
            .rename("base_rate").reset_index())
base_glob = float(tr["cost"].median())
base_tbl.to_csv(OUT / "base_rate_trainonly.csv", index=False)
br = df[["inacbg", "sev"]].assign(inacbg=df["inacbg"].astype(str)).merge(
    base_tbl.assign(inacbg=base_tbl["inacbg"].astype(str)), on=["inacbg", "sev"], how="left")["base_rate"]
df["base_rate"] = br.fillna(base_glob).astype("float32")
print(f"[base_rate] sel train {len(base_tbl):,} antara? global median Rp {base_glob:,.0f}")

# ===========================================================================
# 6) Matriks fitur (float32)
# ===========================================================================
primary_enc_b = df["primary3"].str.split(".").str[0].map(DIAG_MAP).fillna(0).astype("float32")
exp_max = df["primary3"].map(lambda s: EXPECTED_LOS.get(s, (2, 7))[1]).astype("float32")
sev = df["sev"].astype("float32")
n_sec = df["n_secondary"]
has_proc = df["has_proc"].astype("float32")
los = df["los"]

matB = np.column_stack([
    primary_enc_b.to_numpy(), n_sec.to_numpy(), has_proc.to_numpy(),
    np.zeros(len(df), dtype="float32"),               # num_medications (absen)
    sev.to_numpy(), los.to_numpy(),
    np.zeros(len(df), dtype="float32"),               # has_high_cost_proc (absen)
    np.zeros(len(df), dtype="float32"),               # has_phantom_risk_proc (absen)
    df["has_upcode_diag"].to_numpy(),
    ((sev >= 3).to_numpy() & (has_proc.to_numpy() == 0)).astype("float32"),
    ((sev >= 3).to_numpy()).astype("float32"),        # med konstanta 0 -> mismatch med = sev>=3
    (los.to_numpy() > exp_max.to_numpy() * 2).astype("float32"),
    (1.0 + n_sec + has_proc).to_numpy("float32"),
    (has_proc.to_numpy() / np.maximum(sev.to_numpy() * 2.0, 1.0)).astype("float32"),
    np.zeros(len(df), dtype="float32"),
]).astype("float32")

region_enc = df["prov"].map(region_bucket).astype("float32")
primary_enc_v2 = df["primary3"].map(V2_DIAG_ENC if V2_DIAG_ENC else {}).fillna(0).astype("float32")
matC = np.column_stack([
    primary_enc_v2.to_numpy(), n_sec.to_numpy(), has_proc.to_numpy(),
    df["age"].astype("float32").to_numpy(),
    np.zeros(len(df), dtype="float32"),               # num_medications (gap)
    los.to_numpy(),
    (los == 0).astype("float32").to_numpy(),          # outpatient proxy day-care
    np.zeros(len(df), dtype="float32"),               # icu (gap)
    np.zeros(len(df), dtype="float32"),               # ventilator (gap)
    has_proc.to_numpy(),                              # surgical proxy (FKL30)
    df["tipe"].astype("float32").to_numpy(),
    df["kelas"].astype("float32").to_numpy(),
    region_enc.to_numpy(),
    sev.to_numpy(),
    df["base_rate"].to_numpy(),
]).astype("float32")

y = df["cost"].to_numpy("float32")
dialysis = (df["inacbg"] == "Q-5-44-0").to_numpy()
time_cut = pd.Timestamp(df["svc_date"].quantile(0.85))
print(f"[view] batas waktu test-terbaru = p85 tanggal layanan ({time_cut.date()})")


# ===========================================================================
# 7) Latih & evaluasi
# ===========================================================================
def evaluate(pred: np.ndarray, mask: np.ndarray) -> dict:
    p, a = pred[mask].astype("float64"), y[mask].astype("float64")
    err = np.abs(p - a)
    ape = err / a
    return {
        "n": int(mask.sum()),
        "mape_pct": round(float(ape.mean() * 100), 2),
        "medape_pct": round(float(np.median(ape) * 100), 2),
        "mae_rp": round(float(err.mean()), 0),
        "rmse_rp": round(float(np.sqrt(((p - a) ** 2).mean())), 0),
        "r2": round(float(1 - ((p - a) ** 2).sum() / ((a - a.mean()) ** 2).sum()), 4),
        "within5_pct": round(float((ape <= 0.05).mean() * 100), 1),
        "within10_pct": round(float((ape <= 0.10).mean() * 100), 1),
    }


def train_booster(mat: np.ndarray, names: list[str], tag: str) -> xgb.Booster:
    dfit = xgb.DMatrix(mat[fit_idx], label=y[fit_idx], feature_names=names)
    dhold = xgb.DMatrix(mat[hold], label=y[hold], feature_names=names)
    params = {"objective": "reg:squarederror", "tree_method": "hist", "eta": 0.05,
              "max_depth": 8, "subsample": 0.8, "colsample_bytree": 0.8,
              "eval_metric": "mae", "nthread": -1, "seed": 42}
    booster = xgb.train(params, dfit, num_boost_round=400, evals=[(dhold, "hold")],
                        verbose_eval=False)
    hold_mae = float(booster.eval(xgb.DMatrix(mat[hold], label=y[hold], feature_names=names)).split(":")[-1])
    booster.save_model(str(MODELS_OUT / f"xgboost_cost_real_{tag}.json"))
    (MODELS_OUT / f"xgboost_cost_real_{tag}_features.json").write_text(
        json.dumps({"features": names}, ensure_ascii=False), encoding="utf-8")
    print(f"[latih] {tag}: hold MAE Rp {float(hold_mae):,.0f}")
    return booster


boosterB = train_booster(matB, LEGACY_FEATURES, "legacy_b")
boosterC = train_booster(matC, V2_FEATURES, "v2_c")

preds: dict[str, np.ndarray] = {}
legacy_booster = xgb.Booster()
legacy_booster.load_model(str(LEGACY_MODEL))
legacy_note = f"booster.feature_names={'ada' if legacy_booster.feature_names else 'tidak ada'}"
try:
    dmat = xgb.DMatrix(matB, feature_names=LEGACY_FEATURES)
    preds["A_runtime_legacy"] = legacy_booster.predict(dmat, validate_features=False)
except Exception as exc:  # dokumentasi jujur bila kontrak tidak cocok
    print(f"[ujung-atau!?] model legacy gagal prediksi: {exc}")
    legacy_note += f"; error: {exc}"
preds["B_legacy_real"] = boosterB.predict(xgb.DMatrix(matB, feature_names=LEGACY_FEATURES))
preds["C_v2_real"] = boosterC.predict(xgb.DMatrix(matC, feature_names=V2_FEATURES))

test_time = is_test & (df["svc_date"] >= time_cut).to_numpy()
results: dict = {
    "meta": {
        "sumber": "Data Sampel Reguler Edisi 2025 (FKRTL, subset wajar FKL47==FKL48)",
        "split": "subject crc32(PSTV01)%10 in {8,9}; holdout internal 10% train untuk early-stop",
        "test_time_view": f"svc_date >= {time_cut.date()} (p85)",
        "legacy_note": legacy_note,
        "fitur_provenance": {
            "riil": ["n_secondary (202405)", "sev (FKL23)", "los (FKL04-FKL03)",
                     "primary diag (FKL15A)", "tipe (FKL09)", "kelas (FKL13)",
                     "region (FKL05_NEW)", "age (kepesertaan)", "has_proc/surgical (FKL30)",
                     "base_rate (median train-only per INACBG x sev)"],
            "konstanta_gap": ["num_medications=0", "icu=0", "ventilator=0",
                              "has_high_cost_proc=0", "has_phantom_risk_proc=0"],
            "proxy": ["outpatient = LOS==0", "D 15 legacy kontrak identical to runtime"]},
    },
}
views = {"test_semua": is_test, "test_terbaru": test_time,
         "test_dialisis": is_test & dialysis, "test_non_dialisis": is_test & ~dialysis}
for variant, pred in preds.items():
    results[variant] = {name: evaluate(pred, mask) for name, mask in views.items()}

gains = boosterC.get_score(importance_type="total_gain")
importances = {k: round(float(v), 1) for k, v in
               sorted(gains.items(), key=lambda kv: kv[1], reverse=True)[:10]}
results["C_v2_real"]["feature_gain_top10"] = importances

(OUT / "retrain_results.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

print("\n== hasil (test_semua) ==")
for variant in preds:
    m = results[variant]["test_semua"]
    print(f"  {variant:18s} MAPE {m['mape_pct']:6.2f}%  medAPE {m['medape_pct']:6.2f}%  "
          f"MAE Rp {m['mae_rp']:,.0f}  R2 {m['r2']:.4f}  <=10% {m['within10_pct']:5.1f}%")
print("\n== hasil (test_terbaru / strata) untuk C_v2_real ==")
for name in ("test_terbaru", "test_dialisis", "test_non_dialisis"):
    m = results["C_v2_real"][name]
    print(f"  {name:18s} n {m['n']:>9,}  MAPE {m['mape_pct']:6.2f}%  medAPE {m['medape_pct']:6.2f}%  "
          f"MAE Rp {m['mae_rp']:,.0f}  R2 {m['r2']:.4f}")
print("\n== hasil strata B_legacy_real ==")
for name in ("test_dialisis", "test_non_dialisis"):
    m = results["B_legacy_real"][name]
    print(f"  {name:18s} n {m['n']:>9,}  MAPE {m['mape_pct']:6.2f}%  medAPE {m['medape_pct']:6.2f}%")
print("\n" + f"saved -> {OUT / 'retrain_results.json'}")
