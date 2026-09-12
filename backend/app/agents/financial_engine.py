"""
Financial Risk Engine — murni ML, tanpa LLM (AGENTS.md Section 3).

Jalur utama : XGBoost regressor (prediksi biaya) + SHAP (atribusi fitur).
Fallback    : z-score terhadap peer group baseline — tetap deterministik,
              tetap ada angka, TIDAK PERNAH fallback ke "no score"
              dan TIDAK PERNAH memberi anomaly_score maksimum semu.
"""
import os
import math
import numpy as np
import xgboost as xgb
import shap
from backend.app.models.schemas import ClaimInput, FinancialAssessment, SHAPFeature
from backend.app.ml.feature_engineering import (
    extract_cost_features,
    COST_FEATURE_NAMES,
    PEER_BASELINE,
)

# Label ramah pengguna untuk tiap fitur (ditampilkan di UI)
FEATURE_LABELS = {
    "primary_diag_encoded": "jenis diagnosis",
    "num_secondary_diags": "jumlah diagnosis sekunder",
    "num_procedures": "jumlah prosedur",
    "num_medications": "jumlah jenis obat",
    "severity_level": "tingkat keparahan",
    "length_of_stay": "lama rawat",
    "has_high_cost_proc": "ada prosedur berbiaya tinggi",
    "has_phantom_risk_proc": "ada prosedur berisiko phantom billing",
    "has_upcoding_risk_diag": "ada diagnosis berisiko upcoding",
    "severity_proc_mismatch": "severity vs prosedur tidak cocok",
    "severity_med_mismatch": "severity vs obat tidak cocok",
    "los_outlier": "lama rawat outlier",
    "num_total_codes": "jumlah total kode medis",
    "proc_count_ratio": "rasio prosedur vs severity",
    "medication_count": "jumlah obat",
}

_MODELS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models_trained"))

_xgb_model = None
_shap_explainer = None
_load_error: str | None = None


def get_financial_model():
    global _xgb_model, _shap_explainer, _load_error
    if _xgb_model is None:
        model_path = os.path.join(_MODELS_DIR, "xgboost_regressor.json")
        if not os.path.exists(model_path):
            _load_error = "Model XGBoost tidak ditemukan. Jalankan scripts/train_all.py."
            raise RuntimeError(_load_error)
        try:
            model = xgb.XGBRegressor()
            model.load_model(model_path)
            # XGBoost 3.x + SHAP 0.49: pakai predict callable
            model_features = model.get_booster().num_features()
            if model_features != len(COST_FEATURE_NAMES):
                raise RuntimeError(
                    "Model biaya lama tidak kompatibel dengan fitur tanpa target leakage. "
                    "Jalankan scripts/train_all.py."
                )
            _shap_explainer = shap.Explainer(
                model.predict,
                shap.maskers.Independent(np.zeros((1, len(COST_FEATURE_NAMES))), max_samples=50),
            )
            _xgb_model = model
            _load_error = None
        except Exception as e:
            _load_error = f"Gagal load model XGBoost: {e}"
            raise
    return _xgb_model, _shap_explainer


def _zscore_fallback(claim: ClaimInput, reason: str) -> FinancialAssessment:
    """Fallback deterministik: z-score terhadap peer baseline diagnosis yang sama."""
    base = claim.diagnosis_primary.split(".")[0]
    peer_mean = float(PEER_BASELINE.get(base, 5_000_000))
    peer_std = peer_mean * 0.25  # asumsi CV 25% untuk klaim sejenis

    predicted = peer_mean
    deviation_pct = ((claim.cost_claimed - predicted) / predicted) * 100 if predicted > 0 else 0.0
    z = (claim.cost_claimed - peer_mean) / peer_std if peer_std > 0 else 0.0
    anomaly_score = float(min(max(z / 4.0, 0.0), 1.0))  # z>=4 → skor maksimum

    return FinancialAssessment(
        claim_id=claim.claim_id,
        predicted_cost_range=(peer_mean * 0.85, peer_mean * 1.15),
        actual_cost=claim.cost_claimed,
        deviation_pct=float(deviation_pct),
        shap_top_features=[],
        anomaly_score=anomaly_score,
        evidence_text=(
            f"[Fallback z-score peer — model ML tidak tersedia: {reason}] "
            f"Claimed amount Rp {claim.cost_claimed:,.0f} dibanding reimbursement benchmark "
            f"diagnosis {base}: Rp {peer_mean:,.0f} (deviasi "
            f"{'+' if deviation_pct >= 0 else ''}{deviation_pct:.1f}%, z-score {z:.2f})."
        ),
        method="zscore_peer_fallback",
    )


async def analyze_financial(claim: ClaimInput) -> FinancialAssessment:
    try:
        model, explainer = get_financial_model()
    except Exception as e:
        return _zscore_fallback(claim, str(e))

    features = np.array([extract_cost_features(claim.model_dump())])
    try:
        predicted_cost = float(model.predict(features)[0])
    except Exception as e:
        return _zscore_fallback(claim, f"prediksi model gagal: {e}")

    # SHAP attribution
    try:
        shap_explanation = explainer(features)
        raw_shap = shap_explanation.values[0]
    except Exception as e:
        print(f"[SHAP] Warning: {e}. Menggunakan kontribusi nol.")
        raw_shap = np.zeros(features.shape[1])

    actual_cost = claim.cost_claimed
    deviation_pct = ((actual_cost - predicted_cost) / predicted_cost) * 100 if predicted_cost > 0 else 0.0

    # >50% deviasi dari reimbursement benchmark = makin anomali, capped di 1.0
    anomaly_score = float(min(abs(deviation_pct) / 50.0, 1.0))

    # Top SHAP features dengan label terjemahan
    contributions = sorted(
        zip(COST_FEATURE_NAMES, raw_shap), key=lambda x: abs(x[1]), reverse=True
    )
    top_features: list[SHAPFeature] = []
    for fname, fval in contributions[:5]:
        if not math.isnan(float(fval)) and abs(float(fval)) > 1e-6:
            top_features.append(SHAPFeature(
                feature_name=fname,
                feature_label=FEATURE_LABELS.get(fname, fname.replace("_", " ")),
                contribution=abs(float(fval)),
                direction="positive" if fval > 0 else "negative",
            ))

    lower_bound = max(0.0, predicted_cost * 0.85)
    upper_bound = predicted_cost * 1.15

    top_driver = (
        top_features[0].feature_label if top_features else "N/A"
    )
    evidence_text = (
        f"Claimed amount Rp {actual_cost:,.0f} berbanding reimbursement benchmark model Rp {predicted_cost:,.0f} "
        f"(deviasi {'+' if deviation_pct >= 0 else ''}{deviation_pct:.1f}%). "
        f"Faktor utama deviasi terhadap benchmark: {top_driver}."
    )

    return FinancialAssessment(
        claim_id=claim.claim_id,
        predicted_cost_range=(float(lower_bound), float(upper_bound)),
        actual_cost=float(actual_cost),
        deviation_pct=float(deviation_pct),
        shap_top_features=top_features,
        anomaly_score=anomaly_score,
        evidence_text=evidence_text,
        method="xgboost_model",
    )
