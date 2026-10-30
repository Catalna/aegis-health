"""Profil sampel BPJS — Data Sampel Reguler Edisi 2025 (hanya agregat, tanpa data pribadi).

Output: backend/app/data/analysis/profile_reguler.json (ter-ignasi) + ringkasan konsol.
Aturan proyek: data riil tidak pernah masuk git; artefak profil berupa agregat tanpa identifier.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"C:\Users\Radith\E-Jak\backend\app\data\2025\Data Sampel Reguler Edisi 2025\data")
OUT_DIR = Path(r"C:\Users\Radith\E-Jak\backend\app\data\analysis")
OUT_DIR.mkdir(parents=True, exist_ok=True)

CHUNK = 500_000


def smart_date(s: pd.Series) -> pd.Series:
    """Stata bisa mengirim datetime asli, 'YYYYMMDD', string ISO, atau elapsed-days (origin 1960-01-01)."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    n_str = pd.to_datetime(s.astype(str), format="%Y%m%d", errors="coerce")
    if n_str.notna().mean() > 0.95 and s.astype(str).str.len().isin([8]).mean() > 0.95:
        return n_str
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.5 and num.median() > 1000 and num.median() < 50000:
        return pd.to_datetime(num, unit="D", origin="1960-01-01")
    num2 = pd.to_numeric(s, errors="coerce")
    if num2.notna().mean() > 0.5 and (num2 > 19000101).mean() > 0.95:
        return pd.to_datetime(num2.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def pct(x):
    return round(float(x) * 100, 2) if x is not None else None


def qs(series, props=(0.5, 0.9, 0.99)):
    if len(series) == 0:
        return None
    return [int(series.quantile(q)) for q in props]


result: dict = {"meta": {"sumber": "Data Sampel Reguler Edisi 2025 (BPJS Kesehatan)",
                          "proses": "agregat pola; tanpa identifier perorangan"}}

# --- FKRTL ---
f = ROOT / "202403_fkrtl.dta"
cols = ["FKL03", "FKL04", "FKL05_NEW", "FKL08", "FKL09", "FKL10", "FKL13", "FKL15A",
        "FKL17A", "FKL19", "FKL20", "FKL23", "FKL30", "FKL31", "FKL33", "FKL35",
        "FKL41", "FKL44", "FKL47", "FKL48"]
n = 0
prov, tipe, kelas, sev, proc, grp, inacbg = Counter(), Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
los_parts = []
same = has48 = tagih_pos = 0
tagih_sum = verif_sum = 0.0
sa = sp = si = sd = 0
with pd.read_stata(str(f), columns=cols, chunksize=CHUNK, convert_categoricals=False) as it:
    for ch in it:
        n += len(ch)
        prov.update(ch["FKL05_NEW"].dropna().astype(str).value_counts().to_dict())
        tipe.update(ch["FKL09"].dropna().astype(str).value_counts().to_dict())
        kelas.update(ch["FKL13"].dropna().astype(str).value_counts().to_dict())
        sev.update(ch["FKL23"].dropna().astype(str).value_counts().to_dict())
        proc.update(ch["FKL30"].dropna().astype(str).value_counts().to_dict())
        grp.update(ch["FKL20"].dropna().astype(str).value_counts().to_dict())
        inacbg.update(ch["FKL19"].dropna().astype(str).value_counts().to_dict())
        los = (smart_date(ch["FKL04"]) - smart_date(ch["FKL03"])).dt.days
        los_parts.append(los[(los >= 0) & (los <= 365)].dropna().astype(np.int32))
        t47 = pd.to_numeric(ch["FKL47"], errors="coerce")
        t48 = pd.to_numeric(ch["FKL48"], errors="coerce")
        same += int((t47 == t48).sum())
        has48 += int((t48.notna() & (t48 > 0)).sum())
        tagih_pos += int((t47.notna() & (t47 > 0)).sum())
        tagih_sum += float(t47.fillna(0).sum())
        verif_sum += float(t48.fillna(0).sum())
        sa += int(((ch["FKL33"].notna()) & (ch["FKL33"].astype(str).str.strip().str.upper() != "NONE")).sum())
        sp += int(((ch["FKL35"].notna()) & (ch["FKL35"].astype(str).str.strip().str.upper() != "NONE")).sum())
        si += int(((ch["FKL41"].notna()) & (ch["FKL41"].astype(str).str.strip().str.upper() != "NONE")).sum())
        sd += int(((ch["FKL44"].notna()) & (ch["FKL44"].astype(str).str.strip().str.upper() != "NONE")).sum())

los_all = pd.concat(los_parts) if los_parts else pd.Series(dtype="int32")
result["fkrtl"] = {
    "rows": n, "n_provinsi": len(prov), "provinsi_teratas": prov.most_common(8),
    "tipe_faskes": tipe.most_common(6), "kelas_rawat": kelas.most_common(4),
    "severitas_cbg_digit4": sev.most_common(5), "jenis_prosedur": proc.most_common(5),
    "grup_inacbg_teratas": grp.most_common(6), "distinct_grup_inacbg": len(grp),
    "distinct_kode_inacbg_full": len(inacbg), "kode_inacbg_teratas": inacbg.most_common(6),
    "los_p50_p90_p99": qs(los_all, (0.5, 0.9, 0.99)),
    "tagih_positif": tagih_pos, "verifikasi_terisi_positif": has48,
    "tagih_sama_verifikasi": same, "share_tagih_sama_verif_pct": pct(same / tagih_pos) if tagih_pos else None,
    "total_tagih_miliar": round(tagih_sum / 1e9, 2), "total_verif_miliar": round(verif_sum / 1e9, 2),
    "selisih_miliar": round((tagih_sum - verif_sum) / 1e9, 2),
    "share_baris_komponen_pct": {"SA_subacute": pct(sa / n), "SP_prosedur": pct(sp / n),
                                  "SI_investigasi": pct(si / n), "SD_obat": pct(sd / n)},
}

# --- FKTP kapitasi ---
f = ROOT / "202402_fktpkapitasi.dta"
cols = ["FKP03", "FKP05_NEW", "FKP08", "FKP09", "FKP14A"]
n = 0
prov, jenis, tipe, dx3 = Counter(), Counter(), Counter(), Counter()
with pd.read_stata(str(f), columns=cols, chunksize=CHUNK, convert_categoricals=False) as it:
    for ch in it:
        n += len(ch)
        prov.update(ch["FKP05_NEW"].dropna().astype(str).value_counts().to_dict())
        jenis.update(ch["FKP08"].dropna().astype(str).value_counts().to_dict())
        tipe.update(ch["FKP09"].dropna().astype(str).value_counts().to_dict())
        dx3.update(ch["FKP14A"].dropna().astype(str).value_counts().to_dict())
result["fktp"] = {"rows": n, "n_provinsi": len(prov), "provinsi_teratas": prov.most_common(6),
                  "jenis_faskes": jenis.most_common(6), "tipe_faskes": tipe.most_common(6),
                  "dx3_distinct": len(dx3), "dx3_teratas": dx3.most_common(6)}

# --- Non-kapitasi ---
f = ROOT / "202404_nonkapitasi.dta"
n = 0
tipe, prov, samev, tagih_pos = Counter(), Counter(), 0, 0
with pd.read_stata(str(f), columns=["PNK06_NEW", "PNK10", "PNK17", "PNK18"],
                   chunksize=CHUNK, convert_categoricals=False) as it:
    for ch in it:
        n += len(ch)
        tipe.update(ch["PNK10"].dropna().astype(str).value_counts().to_dict())
        prov.update(ch["PNK06_NEW"].dropna().astype(str).value_counts().to_dict())
        t17 = pd.to_numeric(ch["PNK17"], errors="coerce")
        t18 = pd.to_numeric(ch["PNK18"], errors="coerce")
        tagih_pos += int((t17.notna() & (t17 > 0)).sum())
        samev += int((t17 == t18).sum())
result["nonkapitasi"] = {"rows": n, "n_provinsi": len(prov), "tipe_faskes": tipe.most_common(6),
                         "tagih_positif": tagih_pos, "tagih_sama_verif": samev,
                         "share_sama_pct": pct(samev / tagih_pos) if tagih_pos else None}

# --- Kepesertaan ---
f = ROOT / "2015202401_kepesertaan.dta"
cols = ["PSTV03", "PSTV05", "PSTV07", "PSTV08", "PSTV09_NEW"]
n = 0
thn_lahir, kelas, seg, prov, jk = Counter(), Counter(), Counter(), Counter(), Counter()
with pd.read_stata(str(f), columns=cols, chunksize=CHUNK, convert_categoricals=False) as it:
    for ch in it:
        n += len(ch)
        if pd.api.types.is_numeric_dtype(ch["PSTV03"]) and ch["PSTV03"].median() < 50000:
            y = smart_date(ch["PSTV03"]).dt.year
        else:
            y = pd.to_numeric(ch["PSTV03"].astype(str).str[:4], errors="coerce")
        thn_lahir.update(y.dropna().astype(int).astype(str).value_counts().to_dict())
        kelas.update(ch["PSTV07"].dropna().astype(str).value_counts().to_dict())
        seg.update(ch["PSTV08"].dropna().astype(str).value_counts().to_dict())
        prov.update(ch["PSTV09_NEW"].dropna().astype(str).value_counts().to_dict())
        jk.update(ch["PSTV05"].dropna().astype(str).value_counts().to_dict())

age_counts = Counter()
for k, v in thn_lahir.items():
    if isinstance(k, str) and k.isdigit() and 1900 <= int(k) <= 2024:
        age_counts[2024 - int(k)] += v
age_ser = pd.Series(dict(age_counts), dtype=float).sort_index() if age_counts else pd.Series(dtype=float)
if len(age_ser):
    cum = age_ser.cumsum()
    umur_p50 = int(age_ser.index[int(np.searchsorted(cum.values, age_ser.sum() * 0.5, side="left"))])
    umur_p90 = int(age_ser.index[int(np.searchsorted(cum.values, age_ser.sum() * 0.9, side="left"))])
else:
    umur_p50 = umur_p90 = None
result["kepesertaan"] = {
    "rows": n, "n_provinsi": len(prov), "provinsi_teratas": prov.most_common(6),
    "kelas_rawat_peserta": kelas.most_common(4), "segmen": seg.most_common(6),
    "jenis_kelamin": jk.most_common(3), "umur_p50_p90": [umur_p50, umur_p90],
    "tahun_lahir_teratas": thn_lahir.most_common(5),
}

out = OUT_DIR / "profile_reguler.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
print(f"\nsaved -> {out}")
