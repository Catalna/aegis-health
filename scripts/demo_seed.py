"""Seed curated demo DB via the live REST API (Fase 6, video-bound).

- 212 klaim sintetis kurasi (90 normal + 122 skenario anomali) di-POST ke
  server lokal sehingga SETIAP klaim melewati alur produksi nyata:
  POST /api/claims -> FIFO worker -> orchestrator -> risk_analyses -> LanceDB.
- Kalibrasi terhadap mesin skor runtime (bukan terhadap label):
  * prediksi biaya runtime (XGBoost; biaya TIDAK termasuk fitur) dipanggil
    in-process; claimed = pred x multiplier -> financial_anomaly =
    30*min(|dev|/50,1) dipilih per skenario.
  * flag relasional pembentuk tier (clone/repeat/unbundling/exact-dup) dipicu
    lewat desain konten: pasien/faskes/kode/biaya/jendela <=45 hari sesuai
    kondisi fraud_agent (J>0.9 + prox>0.95 + faskes sama + pasien beda untuk
    clone; overlap prosedur untuk repeat; fragmen <0.8 peer + sum 0.75-1.5
    untuk unbundling; tanggal masuk sama + kode + biaya identik untuk exact).
  * nomor tier disimulasikan OFFLINE oleh --dry-run memakai fungsi runtime
    yang sama (rule clinical + risk_engine bands 55.0/48.7 + floor relasional)
    sebelum satu pun klaim di-POST.
- DB demo bersifat presentasional; angka evaluasi ML (AP/recall) tetap dari
  docs/ evaluasi. Klaim sintetis demonstrator - bukan validasi BPJS.

Usage:
    python scripts/demo_seed.py --dry-run   # verifikasi silang offline tanpa POST
    python scripts/demo_seed.py             # seed + tunggu antrean kosong + verifikasi
    python scripts/demo_seed.py --skip-wait # submit saja; polling nanti
    python scripts/demo_seed.py --base-url http://localhost:8000

Server harus sudah jalan (start.bat) dan DB demo kosong
(scripts/demo_reset.py + restart server); claim_id yang sudah ada -> 409 skip.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = date(2026, 9, 1)
DOCTORS = ["DR-ANDI", "DR-BUDI", "DR-CITA", "DR-DANI"]

# (mulut keluarga: kode utama, frekuensi prosedur keluarga, batas LOS kasar)
FAMILIES = {
    "J18": {"code": "J18.9", "procy": "47.0", "los_hi": 5},
    "J44": {"code": "J44.9", "procy": "47.0", "los_hi": 7},
    "I10": {"code": "I10.9", "procy": "47.0", "los_hi": 5},
    "E11": {"code": "E11.9", "procy": "47.0", "los_hi": 3},
    "K35": {"code": "K35.8", "procy": "47.0", "los_hi": 6},
    "O80": {"code": "O80.0", "procy": "", "los_hi": 3},
    "N18": {"code": "N18.9", "procy": "39.95", "los_hi": 4},
    "C50": {"code": "C50.9", "procy": "85.41", "los_hi": 8},
    "S72": {"code": "S72.0", "procy": "81.51", "los_hi": 12},
}
FAM_ORDER = list(FAMILIES)
# Satu faskes per keluarga: kode set antar skenario berbeda (Jaccard <= 0.75),
# sehingga tidak ada cloning palsu lintas kelompok pada faskes yang sama.
FAMILY_PROVIDER = {fam: f"FASKES-R{i + 1:02d}" for i, fam in enumerate(FAM_ORDER)}
# Faskes cadangan untuk UPC (baris 2 & 4 per keluarga, jarak tanggal > 45 hari
# di antara baris same-fam tanpa harus melebar rentang tanggal demo).
UPC_ALT_PROVIDER = {"J18": "FASKES-R91", "J44": "FASKES-R92",
                    "N18": "FASKES-R93", "K35": "FASKES-R94"}

# Pool diagnosis sekunder per keluarga (6 kode); baris normal pakai pasangan
# (a,b) unik agar Jaccard intra-keluarga maksimum 0.5 (jauh dari ambang 0.9).
SECONDARY_POOLS = {
    "J18": ["J96.9", "R06.8", "J96.0", "R50.9", "E87.6", "R05.9"],
    "J44": ["J44.1", "R06.0", "E87.6", "J96.9", "R50.9", "K21.9"],
    "I10": ["E78.5", "E11.9", "K76.9", "R73.9", "N18.9", "D64.9"],
    "E11": ["E11.5", "I10.9", "N17.9", "E87.6", "D64.9", "K21.9"],
    "K35": ["K35.2", "R10.4", "K91.8", "D64.9", "E87.6", "K21.9"],
    "O80": ["O42.9", "Z37.0", "O99.8", "D64.9", "R50.9", "K21.9"],
    "N18": ["N17.9", "I10.9", "D64.9", "E87.6", "K76.9", "R50.9"],
    "C50": ["C50.4", "N18.9", "D64.9", "Z51.1", "K76.9", "R50.9"],
    "S72": ["S72.4", "D64.9", "K76.9", "Z89.4", "I10.9", "R50.9"],
}
# 10 kombinasi 2-kode pairwise unik (tidak identik, maksimum berbagi 1 kode).
_SEC_COMBOS = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0),
               (0, 2), (1, 3), (2, 4), (3, 5)]
# Normal deviasi ±14% (fin <= 9) + jarak pairwise >= 7% (prox <= 0.93 < 0.95).
NORMAL_MULTS = (0.86, 0.93, 1.00, 1.07, 1.14)

# Prosedur keluarga yang masuk set high-cost model (36.10/81.51/85.41/39.95/72.0)
# memberi lonjakan pred biaya yang tidak mengikuti tarif — klaim "normal" tidak
# memakainya; keluarga di luar _PROC_SAFE_FAMS lanjut tanpa prosedur.
_PROC_SAFE_FAMS = {"J18", "J44", "I10", "E11", "K35"}

MEDS_1 = [{"name": "Paracetamol", "quantity": 10}]
MEDS_2 = [{"name": "Ceftriaxone", "quantity": 5}, {"name": "Paracetamol", "quantity": 15}]
MEDS_3 = [{"name": "Ceftriaxone", "quantity": 5}, {"name": "Paracetamol", "quantity": 15},
          {"name": "Omeprazole", "quantity": 7}]


def _day(i: int) -> str:
    return str(BASE + timedelta(days=i))


def _claim(cid, patient, provider, primary, secondary, procs, meds, severity,
           mult, los, adm_i, dis_i, tags, mult_locked_to=None):
    """Buat klaim dengan claimed cost terkalibrasi runtime.

    cost_claimed = prediksi biaya XGBoost (fitur tanpa biaya) x multiplier.
    deviasi ~ (mult-1)*100 secara deterministik."""
    provisional = {
        "claim_id": cid, "patient_id": patient, "provider_id": provider,
        "doctor_id": DOCTORS[len(cid) % len(DOCTORS)],
        "diagnosis_primary": primary, "diagnosis_secondary": secondary,
        "procedure_codes": procs, "medication": meds, "severity_level": severity,
        "cost_claimed": 0, "length_of_stay": los,
        "admission_date": _day(adm_i), "discharge_date": _day(dis_i),
        "tags": tags,
    }
    if mult_locked_to is not None:
        cost = round(mult_locked_to)
    else:
        pred = predict_cost(provisional)
        cost = round(pred * mult)
    claimed = dict(provisional, cost_claimed=cost)
    _CALIBRATION_LOG.append((cid, mult, *_dev_breakdown(claimed)))
    return claimed


_CALIBRATION_LOG: list[tuple] = []


def _dev_breakdown(claim: dict):
    """(dev_pct, predicted) untuk log verifikasi; memakai cache pred runtime."""
    cid = claim["claim_id"]
    pred = _PRED_CACHE.get(cid)
    if pred is None:
        pred = predict_cost(claim)
        _PRED_CACHE[cid] = pred
    c = claim["cost_claimed"]
    dev = ((c - pred) / pred) * 100.0 if pred > 0 else 0.0
    return dev, pred

_PRED_CACHE: dict[str, float] = {}

_FIN_MODEL = None


def predict_cost(claim: dict) -> float:
    """Prediksi biaya runtime (jalur finansi produksi, tanpa SHAP).

    Biaya klaim TIDAK termasuk fitur model (train_xgboost: target-leak guard),
    jadi nilai cost_claimed pada dict probe tidak memengaruhi prediksi."""
    global _FIN_MODEL
    if _FIN_MODEL is None:
        from backend.app.agents.financial_engine import get_financial_model
        model, _shap = get_financial_model()
        _FIN_MODEL = model
    from backend.app.ml.feature_engineering import extract_cost_features
    feats = np.asarray([extract_cost_features(claim)], dtype=float)
    return float(_FIN_MODEL.predict(feats)[0])


# ---------------------------------------------------------------------------
# Skenario kurasi (semua tier disimulasikan dulu oleh --dry-run)
# ---------------------------------------------------------------------------

def _normals(body: list) -> None:
    """90 normal, 10/keluarga: sev 1-2, LOS <= batas keluarga, dua sekunder
    unik per baris (Jaccard intra-keluarga <= 0.5), deviasi biaya +-14%
    -> fin <= 9, tanpa flag: skor < 10 => LOW."""
    for fam, meta in FAMILIES.items():
        pool = SECONDARY_POOLS[fam]
        for k in range(10):
            sev = 1 if k % 3 == 0 else 2
            los = (k % meta["los_hi"]) + 1
            procs = [meta["procy"]] if meta["procy"] and fam in _PROC_SAFE_FAMS and k % 4 == 0 else []
            a, b = _SEC_COMBOS[k]
            body.append(_claim(
                f"DEMO-NORM-{fam}-{k:02d}", f"PAT-DEMO-N{fam}{k:02d}",
                FAMILY_PROVIDER[fam], meta["code"], [pool[a], pool[b]], procs,
                MEDS_2, sev, NORMAL_MULTS[k % 5], los, 10 + k * 8, 10 + k * 8 + los,
                ["normal", "expect_low"]))


def _unbundling(body: list) -> None:
    """6 grup x 3 fragmen. Fragment: pasien+faskes+primary sama, prosedur
    bersama non-high-cost, <45 hari; setiap fragmen < 0.8 peer dan sum
    0.75-1.5 peer -> unbundling flag. Fams dipilih dari probe pred biaya
    (K35/J44/I10/U80 ratio <=0.5 pada fitur kecil; S72/C50 hanya dengan
    prosedur non-high-cost karena 81.51/85.41 mem-flip pred sampai 1.0 peer)."""
    groups = [
        # (grupo, fam, proc, (frac per fragmen), secs per fragmen)
        (0, "K35", "47.09", (0.24, 0.28, 0.31), ["K40.9", "K35.2", "R10.4"]),
        (1, "J44", "47.0", (0.41, 0.44, 0.47), ["R06.0", "E87.6", "R50.9"]),
        (2, "I10", "47.0", (0.40, 0.44, 0.48), ["E78.5", "R73.9", "D64.9"]),
        (3, "S72", "93.49", (0.28, 0.31, 0.34), ["S72.4", "I10.9", "D64.9"]),
        (4, "C50", "85.11", (0.24, 0.27, 0.30), ["C50.4", "D64.9", "Z51.1"]),
        (5, "K35", "47.09", (0.26, 0.29, 0.32), ["K63.5", "K91.8", "B36.1"]),
    ]
    peer_by_fam = {"K35": 7_500_000, "J44": 4_200_000, "I10": 5_000_000,
                   "S72": 28_000_000, "C50": 35_000_000}
    for g, fam, proc, fracs, secs in groups:
        meta = FAMILIES[fam]
        peer = peer_by_fam[fam]
        patient = f"PAT-DEMO-UB{g}"
        provider = FAMILY_PROVIDER[fam]
        start = 40 + g * 5
        for j, (frac, sec) in enumerate(zip(fracs, secs)):
            target = peer * frac
            los = 2 + j
            meds, sev, chosen = _fit_features(
                fam, meta["code"], [sec], proc, los, target, peer,
                allow_dev=0.35, sum_context=(g, j, peer, fracs))
            tags = ["unbundling", "expect>=medium", "frags-split"]
            body.append(_claim(
                f"DEMO-UB{g}-F{j}", patient, provider, meta["code"], [sec],
                [proc], meds, sev, None, los, start + j, start + j + 2 + j,
                tags, mult_locked_to=chosen))


def _fit_features(fam, primary, secs, procs, los, target_cost, peer,
                  allow_dev: float, sum_context=None) -> tuple[list, int, float]:
    """Cari (meds, sev) dengan pred paling dekat target biaya.
    Cost tetap = target (fraksi peer yang menjamin jendela unbundling);
    hanya digeser ke pred jika |dev| > allow_dev (maks fin 27 -> tak menyentuh
    band high karena 20 sim + fin + ev <= 48)."""
    med_options = [MEDS_2, MEDS_1, MEDS_3][:3]
    best = None
    for meds in med_options:
        for sev in (1, 2):
            probe = {
                "claim_id": "probe", "patient_id": "pp", "provider_id": "pvx",
                "doctor_id": "DR-ANDI", "diagnosis_primary": primary,
                "diagnosis_secondary": secs, "procedure_codes": [procs],
                "medication": meds, "severity_level": sev, "cost_claimed": 0,
                "length_of_stay": los,
                "admission_date": _day(10), "discharge_date": _day(10 + los),
            }
            pred = predict_cost(probe)
            if pred <= 0:
                continue
            err = abs(pred - target_cost) / target_cost
            if best is None or err < best[0]:
                best = (err, meds, sev, pred)
    if best is None:
        raise SystemExit(f"fit gagal: {fam} target={target_cost:,.0f}")
    err, meds, sev, pred = best
    cost = round(target_cost)
    dev = abs(cost - pred) / pred
    if dev > allow_dev:
        cost = round(min(pred * (1 + allow_dev), max(pred * (1 - allow_dev), cost)))
    if sum_context:
        _UB_SUM_GUARD.append((sum_context, cost, peer))
    return meds, sev, cost


_UB_SUM_GUARD: list[tuple] = []


def _check_ub_sums() -> None:
    """Validasi sum fragmen 0.75-1.5 peer setelah fit; fragmen < 0.8 peer."""
    groups = {}
    for (g, j, peer, fracs), cost, _peer in _UB_SUM_GUARD:
        groups.setdefault(g, []).append((j, cost, peer))
    for g, frags in sorted(groups.items()):
        total = sum(c for _, c, _ in frags)
        peer = frags[0][2]
        for j, c, _ in frags:
            if c >= peer * 0.8:
                raise SystemExit(f"UB{g}-F{j} cost {c:,.0f} >= 0.8*peer")
        if not (0.75 * peer <= total <= 1.5 * peer):
            raise SystemExit(f"UB{g} sum {total:,.0f} di luar 0.75-1.5 * {peer:,.0f}")


def _repeat_pairs(body: list) -> None:
    """7 pasien-pasangan, 25-45 hari, prosedur bersama -> repeat flag dua sisi.
    deviasi <= 30% (fin <= 18): sim 20 + fin + ev <= 48 -> floor MEDIUM."""
    fams = ["J44", "I10", "N18", "J18", "E11", "J44", "K35"]
    mults = [1.25, 1.00, 0.85, 1.18, 1.15, 0.80, 1.30]
    pair_secs = {
        0: ["J44.1", "E78.0"], 5: ["J44.1", "D64.9"],  # J44 ganda: beda sekunder
    }
    for g, fam in enumerate(fams):
        meta = FAMILIES[fam]
        patient = f"PAT-DEMO-RT{g}"
        provider = FAMILY_PROVIDER[fam]
        # Prosedur bersama: keluarga aman pakai procy; N18 pakai 39.27
        # (39.95 high-cost mem-flip pred biaya 28M semua kombo).
        if meta["procy"] and fam in _PROC_SAFE_FAMS:
            proc_pair = [meta["procy"]]
        elif fam == "N18":
            proc_pair = ["39.27"]
        else:
            proc_pair = [meta["procy"]] if meta["procy"] else []
        # Satu sekunder dari pool keluarga (J vs baris normal <= 0.67 - pool
        # aman); J44 dipakai dua pasang -> beda sekunder antar pasang.
        sec = pair_secs.get(g) or [SECONDARY_POOLS[fam][g % 6]]
        base = dict(
            primary=meta["code"], secondary=sec, procs=proc_pair,
            meds=MEDS_3, sev=2, los=3)
        body.append(_claim(
            f"DEMO-RT{g}-A", patient, provider, base["primary"], base["secondary"],
            base["procs"], base["meds"], base["sev"], mults[g], base["los"],
            10 + g * 8, 13 + g * 8, ["repeat", "expect>=medium"]))
        body.append(_claim(
            f"DEMO-RT{g}-B", patient, provider, base["primary"], base["secondary"],
            base["procs"], base["meds"], base["sev"], mults[g] * 1.04, base["los"],
            35 + g * 8, 38 + g * 8, ["repeat", "expect>=medium"]))


def _near_window_pairs(body: list) -> None:
    """5 pasien-pasangan 50 hari (>45): repeat TIDAK boleh terpicu (prosedur
    POLOS -> SQL repeat skip). Target LOW: fin <= 9 tanpa flag."""
    fams = ["J44", "J18", "N18", "I10", "E11"]
    mults = [1.00, 0.93, 1.07, 0.86, 1.14]
    for g, fam in enumerate(fams):
        meta = FAMILIES[fam]
        pool = SECONDARY_POOLS[fam]
        patient = f"PAT-DEMO-NW{g}"
        provider = FAMILY_PROVIDER[fam]
        # Sekunder tunggal dari pool keluarga -> J vs baris normal <= 0.67
        # (baris normal memakai pasangan 2 sekunder + gap biaya >= 14%).
        sec = [pool[(g * 2) % 6]]
        body.append(_claim(
            f"DEMO-NW{g}-A", patient, provider, meta["code"], sec, [], MEDS_2, 2,
            mults[g], 3, 8 + g * 8, 11 + g * 8, ["near_window", "expect_low"]))
        body.append(_claim(
            f"DEMO-NW{g}-B", patient, provider, meta["code"], sec, [], MEDS_2, 2,
            mults[g] * 1.03, 3, 58 + g * 8, 61 + g * 8,
            ["near_window", "expect_low", "gap50d"]))


def _cloning_pairs(body: list) -> None:
    """6 pasangan clone: faskes sama, pasien beda, kode identik (J=1), biaya
    pasangan persis (prox >= 0.98), <=42 hari -> clone flag dua sisi.
    mult antar-pasangan dipisah >= 20% (prox cross < 0.9)."""
    groups = [
        (0, "K35", ["K57.3"], "47.09", 1.30),
        (1, "K35", ["K29.9"], "47.09", 1.00),
        (2, "C50", ["N95.1"], "85.41", 1.25),
        (3, "C50", ["D25.9"], "85.41", 1.05),
        (4, "K35", ["K63.5"], "47.09", 0.80),
        (5, "C50", ["L30.9"], "85.41", 0.85),
    ]
    for g, fam, sec, proc, mult in groups:
        meta = FAMILIES[fam]
        provider = FAMILY_PROVIDER[fam]
        start = 30 + g * 9
        body.append(_claim(
            f"DEMO-CLN{g}-A", f"PAT-DEMO-CHA{g}", provider, meta["code"], sec,
            [proc], MEDS_3, 2, mult, 4, start, start + 4, ["cloning", "expect>=medium"]))
        body.append(_claim(
            f"DEMO-CLN{g}-B", f"PAT-DEMO-CHB{g}", provider, meta["code"], sec,
            [proc], MEDS_3, 2, mult * 1.01, 4, start + 3, start + 7,
            ["cloning", "expect>=medium"]))


def _exact_dups(body: list) -> None:
    """2 ejaan gandeng persis (pasien/primary/kode/biaya/tanggal masuk sama)
    -> exact dup dua sisi -> floor HIGH."""
    for g, fam in enumerate(["N18", "E11"]):
        meta = FAMILIES[fam]
        pool = SECONDARY_POOLS[fam]
        sec = [pool[0], pool[2]]
        procs = [meta["procy"]] if meta["procy"] else []
        common = dict(
            patient=f"PAT-DEMO-DU{g}", provider=FAMILY_PROVIDER[fam],
            primary=meta["code"], secondary=sec, procs=procs,
            meds=MEDS_3, sev=2, los=4, adm=90 + g, dis=94 + g)
        # mult sama untuk kedua baris (persis) - dev jadi kontinuitas kecil
        for suffix in ("1", "2"):
            body.append(_claim(
                f"DEMO-DU{g}-{suffix}", common["patient"], common["provider"],
                common["primary"], common["secondary"], common["procs"],
                common["meds"], common["sev"], 1.20, common["los"],
                common["adm"], common["dis"], ["exact_dup", "expect>=high"]))


def _upcoding(body: list) -> None:
    """16 upcoding (sev 4, sekunder upcoding-risk, tanpa prosedur, 2-3 obat).
    clin 9 (proc-mismatch 5 + upcoding-diag 4) + fin 30 + ev 10 = 49 MEDIUM.
    8 variasi repeat-overlay (pasien sama, prosedur 47.0, +30 hari) tetap LOW
    karena UPC tak memuat prosedur (SQL repeat skip)."""
    fams = ["J18", "J44", "N18", "K35"]
    row_mults = [1.6, 2.2, 2.4, 1.6]
    for g in range(16):
        fam = fams[g % 4]
        row = g // 4
        meta = FAMILIES[fam]
        provider = UPC_ALT_PROVIDER[fam] if row % 2 else FAMILY_PROVIDER[fam]
        patient = f"PAT-DEMO-UP{g}"
        mult = row_mults[row]
        adm = 15 + row * 55
        los = 4 + (row % 3)
        base = dict(
            primary=meta["code"], secondary=["A41.9", "Z87.39"], procs=[],
            meds=MEDS_3, sev=4, los=los)
        body.append(_claim(
            f"DEMO-UPC-{g:02d}", patient, provider, base["primary"],
            base["secondary"], base["procs"], base["meds"], base["sev"],
            mult, base["los"], adm, adm + base["los"],
            ["upcoding", "expect>=medium"]))
        # overlay repeat-dengan-prosedur; pasien sama dengan UPC-{g} (30 hari
        # kemudian, UPC tak memuat prosedur -> repeat SQL tidak terpicu).
        body.append(_claim(
            f"DEMO-UPC-RT-{g:02d}", patient, provider, base["primary"],
            base["secondary"], ["47.0"], base["meds"], base["sev"],
            mult * 1.05, base["los"], adm + 30, adm + 30 + base["los"],
            ["upcoding", "repeat-overlay", "expect_low"]))


def _phantom(body: list) -> None:
    """12 phantom: prosedur high-risk tak didukung primary + sev 4 + 1 obat
    (clin 3+8=11) + dev >= 50% (fin 30) + ev 10 = 51 MEDIUM."""
    fams = ["J18", "J44", "I10", "E11", "O80", "J18",
            "J44", "I10", "E11", "O80", "J18", "J44"]
    fam_rows: dict[str, list[str]] = {}
    for g, fam in enumerate(fams):
        fam_rows.setdefault(fam, []).append(f"DEMO-FLT-{g:02d}")
    mult_by_fam_rows = {fam: (1.5, 2.5, 1.9) for fam in fam_rows}
    row_seen: dict[str, int] = {}
    for g, fam in enumerate(fams):
        meta = FAMILIES[fam]
        proc = "81.51" if fam in {"S72"} else (["36.10", "85.41"][g % 2])
        rows = fam_rows[fam]
        idx = row_seen.get(fam, 0)
        row_seen[fam] = idx + 1
        mult = mult_by_fam_rows[fam][idx % 3]
        pool = SECONDARY_POOLS[fam]
        body.append(_claim(
            f"DEMO-FLT-{g:02d}", f"PAT-DEMO-FL{g}", FAMILY_PROVIDER[fam],
            meta["code"], [pool[(g + 1) % 6]], [proc], MEDS_2[:1], 4, mult, 5,
            20 + g * 6, 25 + g * 6, ["phantom", "expect>=medium", "proc-unsupported"]))


def _inflated(body: list) -> None:
    """16 inflated: 8 tampil bersih (1.7-2.4x -> fin 30 cap, tanpa flag -> LOW
    karena fin-only 35 < band 48.7) + 8 X (sev 3, no-proc, 1 obat, LOS outlier
    -> clin 10) -> 50 MEDIUM."""
    for h in range(8):
        fam = FAM_ORDER[h]
        meta = FAMILIES[fam]
        pool = SECONDARY_POOLS[fam]
        sec = [pool[0], pool[2]]
        # N18 tanpa prosedur: 39.95 high-cost mem-flip pred biaya (28M semua combo).
        procs = ([meta["procy"]] if meta["procy"] and h % 2 == 0
                 and fam in _PROC_SAFE_FAMS else [])
        mult = (1.7, 1.9, 2.1, 1.8, 2.2, 2.4, 2.0, 1.9)[h]
        body.append(_claim(
            f"DEMO-INF-{h:02d}", f"PAT-DEMO-IN{h}", FAMILY_PROVIDER[fam],
            meta["code"], sec, procs, MEDS_3, 2, mult, 3,
            25 + h * 6, 28 + h * 6, ["inflated", "expect_low", "finance-only"]))
    for h in range(8):
        fam = FAM_ORDER[(h + 8) % 9]
        meta = FAMILIES[fam]
        pool = SECONDARY_POOLS[fam]
        sec = [pool[1], pool[3]]
        los = 2 * (_expected_los_max(fam)) + 3
        mult = (1.7, 2.6, 1.9, 2.2, 2.0, 2.4, 1.8, 2.1)[h]
        body.append(_claim(
            f"DEMO-INF-X{h:02d}", f"PAT-DEMO-INX{h}", FAMILY_PROVIDER[fam],
            meta["code"], sec, [], MEDS_3[:1], 3, mult, los,
            25 + h * 6, 31 + h * 6 + los,
            ["inflated", "expect>=medium", "multi-mismatch"]))


def _prolonged(body: list) -> None:
    """12 prolonged-LOS: LOS > 2 batas keluarga. 6 low-cost (dev +-14% ->
    fin <= 9 + flag LOS 2 + ev 5 => LOW) + 6 X (sev 3, 1 obat, dev >= 50% ->
    clin 10 + fin 30 + ev 10 = 50 MEDIUM)."""
    fams = ["J18", "J44", "K35", "N18", "J18", "K35",
            "J18", "J44", "K35", "N18", "J18", "J44"]
    mults = {0: 1.07, 1: 0.93, 2: 1.00, 3: 0.97, 4: 0.93, 5: 1.14,
             6: 1.9, 7: 2.3, 8: 2.1, 9: 2.0, 10: 2.4, 11: 2.2}
    row_idx: dict[str, int] = {}
    for g, fam in enumerate(fams):
        meta = FAMILIES[fam]
        pool = SECONDARY_POOLS[fam]
        idx = row_idx.get(fam, 0)
        row_idx[fam] = idx + 1
        a, b = (idx * 2) % 6, (idx * 2 + 1) % 6
        los = 2 * _expected_los_max(fam) + 3
        mult = mults[g]
        if g < 6:
            tags = ["prolonged", "expect_low", "long-stay-clean-cost"]
        else:
            tags = ["prolonged", "expect>=medium", "long-stay-inflated"]
        sev = 2 if g < 6 else 3
        meds = MEDS_2 if g < 6 else MEDS_2[:1]
        procs = []  # sev>=3 tanpa prosedur hanya utk X (proc-mismatch)
        body.append(_claim(
            f"DEMO-LOS-{g:02d}", f"PAT-DEMO-PL{g}", FAMILY_PROVIDER[fam],
            meta["code"], [pool[a], pool[b]], procs, meds, sev, mult, los,
            30 + g * 6, 30 + g * 6 + los, tags))


def _expected_los_max(fam: str) -> int:
    from backend.app.ml.feature_engineering import EXPECTED_LOS
    return EXPECTED_LOS[fam][1]


def build_scenarios() -> list[dict]:
    body: list[dict] = []
    _normals(body)
    _unbundling(body)
    _repeat_pairs(body)
    _near_window_pairs(body)
    _cloning_pairs(body)
    _exact_dups(body)
    _upcoding(body)
    _phantom(body)
    _inflated(body)
    _prolonged(body)
    ids = [c["claim_id"] for c in body]
    dupes = [k for k, v in Counter(ids).items() if v > 1]
    if dupes:
        raise SystemExit(f"duplicate claim ids in scenario plan: {dupes[:6]}")
    return body


# ---------------------------------------------------------------------------
# Simulator offline: mirror mesin runtime (rule + band + floor)
# ---------------------------------------------------------------------------

_REL_G = None


def _rel_modules():
    global _REL_G
    if _REL_G is None:
        from backend.app.ml.similarity_scoring import (
            compute_jaccard_similarity, cost_proximity, composite_similarity,
            temporal_proximity)
        from backend.app.agents.fraud_agent import is_unbundling_candidate
        from backend.app.agents.risk_engine import CLINICAL_FLAG_WEIGHTS
        from backend.app.agents.clinical_agent import _rule_flags
        from backend.app.data.ina_cbg_rules import (
            calculate_expected_tariff, DIAGNOSIS_TO_CBG_MAPPING)
        from backend.app.models.schemas import ClaimInput
        _REL_G = dict(
            jaccard=compute_jaccard_similarity, prox=cost_proximity,
            composite=composite_similarity, temporal=temporal_proximity,
            unb=is_unbundling_candidate, weights=CLINICAL_FLAG_WEIGHTS,
            rule_flags=_rule_flags, grouped=calculate_expected_tariff,
            cbg_map=DIAGNOSIS_TO_CBG_MAPPING, claim_cls=ClaimInput)
    return _REL_G


def _code_set(claim: dict) -> set:
    vals = {claim.get("diagnosis_primary", "")}
    vals |= {s.strip() for s in claim.get("diagnosis_secondary", []) if s.strip()}
    vals |= {p.strip() for p in claim.get("procedure_codes", []) if p.strip()}
    vals.discard("")
    return vals


def _pair_days(a: dict, b: dict) -> int | None:
    try:
        left = date.fromisoformat(str(a["admission_date"])[:10])
        right = date.fromisoformat(str(b["admission_date"])[:10])
        return abs((left - right).days)
    except (ValueError, TypeError, KeyError):
        return None


def simulate_tiers(claims: list[dict]) -> dict[str, dict]:
    """Mirror deterministik dari pipeline runtime untuk klaim terencana."""
    R = _rel_modules()
    from backend.app.ml.feature_engineering import PEER_BASELINE
    by_id = {c["claim_id"]: c for c in claims}

    out: dict[str, dict] = {}
    for c in claims:
        cid = c["claim_id"]
        pred = _PRED_CACHE.get(cid)
        if pred is None:
            pred = predict_cost(c)
            _PRED_CACHE[cid] = pred
        dev = ((c["cost_claimed"] - pred) / pred) * 100.0 if pred else 0.0
        anomaly = min(abs(dev) / 50.0, 1.0)
        fin = 30.0 * anomaly

        # clinical rule flags (jalur produksi, tanpa LLM)
        try:
            claim_obj = R["claim_cls"].model_validate(
                {k: v for k, v in c.items() if k != "tags"})
        except Exception as e:  # pragma: no cover - guard
            raise SystemExit(f"ClaimInput gagal: {c['claim_id']}: {e}")
        base = c["diagnosis_primary"].split(".")[0]
        grp = R["grouped"](c["diagnosis_primary"], c["procedure_codes"], c["severity_level"])
        tariff_dev = None
        if grp:
            _code, _name, expected = grp
            if expected > 0:
                tariff_dev = ((c["cost_claimed"] - expected) / expected) * 100.0
        flags = R["rule_flags"](claim_obj, tariff_dev, base in R["cbg_map"])
        clin = 0.0
        for flag, weight in R["weights"].items():
            if flag in {"tariff_deviation_high", "tariff_deviation_extreme"}:
                continue
            if flag in flags:
                clin += weight
        clin = min(20.0, clin)

        # relasional
        repeat_flag = False
        unbundle_ids: list[str] = []
        clone_ids: list[str] = []
        exact_flag = False
        sim_max = 0.0
        for d in claims:
            if d["claim_id"] == c["claim_id"]:
                continue
            days = _pair_days(c, d)
            j = R["jaccard"](c, d)
            prox = R["prox"](float(c["cost_claimed"]), float(d["cost_claimed"]))
            same_prov = d["provider_id"] == c["provider_id"]
            comp = R["composite"](j, prox, same_prov, d["patient_id"] == c["patient_id"], days)
            sim_max = max(sim_max, comp)
            # exact dup: pasien+primary+cost+admit + sekunder/prosedur identik
            if (d["patient_id"] == c["patient_id"]
                    and d["diagnosis_primary"] == c["diagnosis_primary"]
                    and d["cost_claimed"] == c["cost_claimed"]
                    and str(d["admission_date"])[:10] == str(c["admission_date"])[:10]
                    and _code_set(d) == _code_set(c)):
                exact_flag = True
            # repeat: pasien sama, overlap prosedur, <=45 hari
            if (not repeat_flag and days is not None and days <= 45
                    and d["patient_id"] == c["patient_id"]):
                mine = set(c["procedure_codes"]) or set()
                theirs = set(d["procedure_codes"]) or set()
                if mine and (mine & theirs):
                    repeat_flag = True
            # unbundling: pasien+faskes+primary sama, overlap prosedur, <=45 hari
            if (days is not None and days <= 45
                    and d["patient_id"] == c["patient_id"]
                    and d["provider_id"] == c["provider_id"]
                    and d["diagnosis_primary"] == c["diagnosis_primary"]):
                mine = set(c["procedure_codes"])
                theirs = set(d["procedure_codes"])
                if mine and (mine & theirs):
                    unbundle_ids.append(d["claim_id"])
                    sim_max = max(sim_max, comp)  # prosedure overlap: top mungkin
            # clone: faskes sama + pasien beda + J>0.9 + prox>0.95 + <=45 hari
            if (days is not None and days <= 45 and same_prov
                    and d["patient_id"] != c["patient_id"] and j > 0.9 and prox > 0.95):
                clone_ids.append(d["claim_id"])
        unb_flag = bool(unbundle_ids) and R["unb"](
            float(c["cost_claimed"]),
            [float(by_id[i]["cost_claimed"]) for i in unbundle_ids],
            PEER_BASELINE.get(c["diagnosis_primary"].split(".")[0], 5_000_000))
        sim_score = 20.0 if (exact_flag or unb_flag or repeat_flag) else (
            min(20.0, sim_max * 20.0) if clone_ids else 0.0)
        fraud_signal = exact_flag or repeat_flag or bool(clone_ids) or unb_flag
        sources = sum((
            any(f not in {"tariff_deviation_high", "tariff_deviation_extreme"} for f in flags),
            anomaly > 0.4 or dev > 30,
            fraud_signal,
        ))
        ev = 15.0 if sources >= 3 else 10.0 if sources == 2 else 5.0 if sources == 1 else 0.0

        total = min(85.0, clin + fin + sim_score + ev)
        tier = "low"
        if total >= 55.0:
            tier = "high"
        elif total >= 48.7:
            tier = "medium"
        if exact_flag:
            tier = "high"
        elif repeat_flag or bool(clone_ids) or unb_flag:
            if tier == "low":
                tier = "medium"
        out[c["claim_id"]] = {
            "claim_id": c["claim_id"], "sim": round(total, 1), "tier": tier,
            "clin": round(clin, 1), "fin": round(fin, 1), "simc": round(sim_score, 1),
            "ev": round(ev, 1), "dev": round(dev, 1), "flags": list(flags),
            "exact": exact_flag, "repeat": repeat_flag, "clone": bool(clone_ids),
            "unbund": bool(unb_flag), "clone_ids": clone_ids[:3],
            "unbund_ids": unbundle_ids[:3],
        }
    return out


def _want_tier(tags: list[str]) -> str | None:
    for t in tags:
        if t.startswith("expect>=high"):
            return "high"
        if t.startswith("expect>=medium"):
            return "medium"
        if t.startswith("expect_low"):
            return "low"
    return None


def print_dry_run(claims: list[dict]) -> int:
    """Simulasi verifikasi; return 0 bila semua target tercapai."""
    sim = simulate_tiers(claims)
    groups: dict[str, list[tuple[str, str | None, dict]]] = {}
    for c in claims:
        groups.setdefault(c["tags"][0], []).append((c["claim_id"], _want_tier(c["tags"]), sim[c["claim_id"]]))
    failures: list[str] = []
    print("=== dry-run simulasi tier (mirror runtime) ===")
    for src, rows in sorted(groups.items()):
        ok = sum(1 for _, w, s in rows if w in (None, s["tier"]))
        print(f"\n[{src}] {ok}/{len(rows)} target")
        for cid, w, s in rows:
            mark = "" if w in (None, s["tier"]) else "  << GAGAL"
            if mark:
                failures.append(cid)
            note = ""
            if w is None:
                note = " (tanpa target)"
            print(f"  {cid:20s} want={w or '-':6s} got={s['tier']:6s} "
                  f"score={s['sim']:5.1f} [clin={s['clin']:g};fin={s['fin']:g};"
                  f"sim={s['simc']:g};ev={s['ev']:g}] dev={s['dev']:+6.1f}% "
                  f"f={s['flags'] if s['flags'] else '-'}{mark}{note}")
    warn = []
    for cid, s in sim.items():
        tagsby = next(c["tags"] for c in claims if c["claim_id"] == cid)
        src = tagsby[0]
        for kind in ("clone", "repeat", "unbund", "exact"):
            if s[kind] and src not in {"cloning", "repeat", "unbundling", "exact_dup",
                                       "upcoding"}:  # upcoding overlay repeat dimatikan sendiri
                warn.append(f"{cid}: flag {kind} di grup {src}")
    print("\n=== peringatan flag di luar desain ===")
    if warn:
        for w in warn:
            print(f"  {w}")
    else:
        print("  bersih")
    print(f"\nhasil: {len(sim) - len(failures)}/{len(sim)} sesuai target; "
          f"gagal {len(failures)}")
    if failures:
        print("-> revisi skenario sebelum seeding.")
        return 1
    return 0


# ---------------------------------------------------------------------------
# Eksekusi seeding via REST
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="simulasi offline saja")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--skip-wait", action="store_true")
    parser.add_argument("--poll-timeout-min", type=int, default=120)
    parser.add_argument("--tag-filter", default=None)
    args = parser.parse_args()

    scenarios = build_scenarios()
    _check_ub_sums()
    if args.tag_filter:
        scenarios = [c for c in scenarios if any(args.tag_filter in t for t in c["tags"])]

    # pred cache perklaim untuk simulasi/laporan deviasi
    for c in scenarios:
        _PRED_CACHE[c["claim_id"]] = predict_cost(c)

    if args.dry_run:
        return print_dry_run(scenarios)

    import httpx  # noqa: E402 - import lokal agar --dry-run --help tetap cepat

    client = httpx.Client(timeout=60.0)
    print(f"submitting {len(scenarios)} kalibrasi-demo klaim ke {args.base_url} ...")
    ok, skipped, errors = 0, 0, 0
    t0 = time.time()
    for c in scenarios:
        payload = {k: v for k, v in c.items() if k != "tags"}
        try:
            r = client.post(f"{args.base_url}/api/claims", json=payload)
        except (httpx.HTTPError, OSError) as exc:
            print(f"  network error on {c['claim_id']}: {exc}")
            errors += 1
            continue
        if r.status_code == 200:
            ok += 1
        elif r.status_code == 409:
            skipped += 1
        else:
            errors += 1
            print(f"  POST failed {c['claim_id']}: HTTP {r.status_code} {r.text[:200]}")
    print(f"submitted: ok={ok} skip={skipped} err={errors} in {time.time() - t0:.1f}s")
    if errors:
        print("batal: masih ada error submit")
        return 1
    if args.skip_wait:
        print("--skip-wait: polling nanti")
        return 0

    deadline = time.time() + args.poll_timeout_min * 60
    pending = -1
    drained = False
    while time.time() < deadline:
        r = client.get(f"{args.base_url}/api/claims", params={"limit": 1000})
        if r.status_code != 200:
            print("gagal baca daftar klaim; coba lagi")
            time.sleep(5)
            continue
        items = r.json()["items"]
        counts: dict[str, int] = Counter(i["status"] for i in items)
        terminal = sum(counts.get(s, 0) for s in ("processed", "review_required", "verified", "failed"))
        if terminal != pending and pending >= 0:
            print(f"  terminal {terminal}/{len(items)}: {dict(sorted(counts.items()))}")
        pending = terminal
        if items and terminal == len(items):
            drained = True
            break
        time.sleep(15)
    if not drained:
        print("timeout menunggu antrean")
        return 2

    dash = client.get(f"{args.base_url}/api/analytics/dashboard").json()
    print("\n=== dashboard ===")
    print(json.dumps(dash, sort_keys=True, indent=1))
    print("\nselesai; cek tier via GET /api/claims?tier=high | medium | low")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
