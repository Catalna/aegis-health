"""
Financial Risk Engine — murni ML, tanpa LLM (AGENTS.md Section 3).

Jalur utama : XGBoost regressor (prediksi biaya) + SHAP (atribusi fitur).
Fallback    : z-score terhadap peer group baseline — tetap deterministik,
              tetap ada angka, TIDAK PERNAH fallback ke "no score"
              dan TIDAK PERNAH memberi anomaly_score maksimum semu.
"""
import os
import logging
import math
import numpy as np
import xgboost as xgb
try:
    import shap
except Exception:
    shap = None
from backend.app.models.schemas import ClaimInput, FinancialAssessment, SHAPFeature
from backend.app.ml.feature_engineering import (
    extract_cost_features,
    COST_FEATURE_NAMES,
    PEER_BASELINE,
)
from backend.app.core.errors import ANALYSIS_RETRYABLE_MESSAGE, failure_for_exception
from backend.app.core.human_language import format_benchmark_finding

# Label ramah pengguna untuk tiap fitur (ditampilkan di UI)
FEATURE_LABELS = {
    "primary_diag_encoded": "jenis diagnosis",
    "num_secondary_diags": "jumlah diagnosis sekunder",
    "num_procedures": "jumlah prosedur",
    "num_medications": "jumlah jenis obat",
    "severity_level": "tingkat keparahan",
    "length_of_stay": "lama rawat",
    "has_high_cost_proc": "ada prosedur berbiaya tinggi",
    "has_phantom_risk_proc": "ada tindakan yang perlu dibuktikan pelaksanaannya",
    "has_upcoding_risk_diag": "ada diagnosis yang perlu diverifikasi",
    "severity_proc_mismatch": "tingkat keparahan tidak sebanding dengan tindakan",
    "severity_med_mismatch": "tingkat keparahan tidak sebanding dengan obat",
    "los_outlier": "lama rawat jauh di atas pola umum",
    "num_total_codes": "jumlah total kode medis",
    "proc_count_ratio": "rasio prosedur vs severity",
    "medication_count": "jumlah obat",
}

_MODELS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models_trained"))

_xgb_model = None
_shap_explainer = None
_load_error: str | None = None
logger = logging.getLogger(__name__)


class XGBoostRegressorAdapter:
    """Small sklearn-free adapter for the XGBoost Booster JSON model format."""

    def __init__(self, model_path: str):
        self._booster = xgb.Booster()
        self._booster.load_model(model_path)

    def predict(self, features):
        matrix = xgb.DMatrix(np.asarray(features, dtype=float))
        return self._booster.predict(matrix)

    def get_booster(self):
        return self._booster


def get_financial_model():
    global _xgb_model, _shap_explainer, _load_error
    if _xgb_model is None:
        model_path = os.path.join(_MODELS_DIR, "xgboost_regressor.json")
        if not os.path.exists(model_path):
            _load_error = "Model XGBoost tidak ditemukan. Jalankan scripts/train_all.py."
            raise RuntimeError(_load_error)
        try:
            model = XGBoostRegressorAdapter(model_path)
            # XGBoost 3.x + SHAP 0.49: pakai predict callable
            model_features = model.get_booster().num_features()
            if model_features != len(COST_FEATURE_NAMES):
                raise RuntimeError(
                    "Model biaya lama tidak kompatibel dengan fitur tanpa target leakage. "
                    "Jalankan scripts/train_all.py."
                )
            if shap is not None:
                _shap_explainer = shap.Explainer(
                    model.predict,
                    shap.maskers.Independent(np.zeros((1, len(COST_FEATURE_NAMES))), max_samples=10),
                )
            else:
                _shap_explainer = None
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
    predicted = peer_mean
    deviation_pct = ((claim.cost_claimed - predicted) / predicted) * 100 if predicted > 0 else 0.0
    anomaly_score = float(min(abs(deviation_pct) / 50.0, 1.0))

    return FinancialAssessment(
        claim_id=claim.claim_id,
        predicted_cost_range=(peer_mean * 0.85, peer_mean * 1.15),
        actual_cost=claim.cost_claimed,
        deviation_pct=float(deviation_pct),
        upward_exposure=float(max(0.0, claim.cost_claimed - predicted)),
        shap_top_features=[],
        anomaly_score=anomaly_score,
        evidence_text=(
            "Perkiraan biaya menggunakan data pembanding untuk diagnosis serupa. "
            + format_benchmark_finding(
                claim.cost_claimed, peer_mean, deviation_pct, "jenis diagnosis"
            )
        ),
        method="zscore_peer_fallback",
    )


async def analyze_financial(claim: ClaimInput) -> FinancialAssessment:
    try:
        model, explainer = get_financial_model()
    except Exception as e:
        logger.exception("Financial model fallback for claim_id=%s", claim.claim_id)
        return _zscore_fallback(claim, ANALYSIS_RETRYABLE_MESSAGE)

    features = np.array([extract_cost_features(claim.model_dump())])
    try:
        predicted_cost = float(model.predict(features)[0])
    except Exception as e:
        logger.exception("Financial prediction fallback for claim_id=%s", claim.claim_id)
        return _zscore_fallback(claim, ANALYSIS_RETRYABLE_MESSAGE)

    # SHAP attribution
    if explainer is not None:
        try:
            shap_explanation = explainer(features)
            raw_shap = shap_explanation.values[0]
        except Exception:
            logger.exception("SHAP attribution unavailable for claim_id=%s", claim.claim_id)
            raw_shap = np.zeros(features.shape[1])
    else:
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

    top_driver = top_features[0].feature_label if top_features else "data yang tersedia"
    evidence_text = format_benchmark_finding(
        actual_cost, predicted_cost, deviation_pct, top_driver
    )

    return FinancialAssessment(
        claim_id=claim.claim_id,
        predicted_cost_range=(float(lower_bound), float(upper_bound)),
        actual_cost=float(actual_cost),
        deviation_pct=float(deviation_pct),
        upward_exposure=float(max(0.0, actual_cost - predicted_cost)),
        shap_top_features=top_features,
        anomaly_score=anomaly_score,
        evidence_text=evidence_text,
        method="xgboost_model",
    )
