from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal, Tuple, Dict
from datetime import date

class MedicationLine(BaseModel):
    name: str
    quantity: int

class ReferralInfo(BaseModel):
    source_facility: str
    reason: str

class ClaimInput(BaseModel):
    claim_id: str
    patient_id: str
    provider_id: str
    doctor_id: str
    diagnosis_primary: str
    diagnosis_secondary: List[str]
    procedure_codes: List[str]
    medication: List[MedicationLine] = Field(default_factory=list)
    severity_level: int = Field(ge=1, le=4)
    cost_claimed: float = Field(ge=0)
    length_of_stay: int = Field(ge=0)
    admission_date: Optional[date] = None
    discharge_date: Optional[date] = None
    referral_info: Optional[ReferralInfo] = None

    @field_validator("claim_id", "patient_id", "provider_id", "diagnosis_primary")
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field wajib tidak boleh kosong")
        return v.strip()

    @field_validator("diagnosis_secondary", "procedure_codes", mode="before")
    @classmethod
    def split_string(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

class ValidationResult(BaseModel):
    """Hasil validasi deterministik (AGENTS.md Section 1) — sebelum agent apa pun jalan."""
    claim_id: str
    hard_reject: bool = False
    reject_reason: Optional[str] = None
    exact_duplicate_of: Optional[str] = None  # claim_id klaim kembar jika terdeteksi
    warnings: List[str] = Field(default_factory=list)

class CBGLookupResult(BaseModel):
    cbg_code: str
    cbg_name: str
    base_tariff: float

class ClinicalAssessment(BaseModel):
    claim_id: str
    grouper_result: Optional[CBGLookupResult] = None
    tariff_deviation_pct: Optional[float] = None
    compatibility_status: Literal["match_table", "llm_assessed", "no_data"]
    plausibility: Literal["plausible", "questionable", "implausible", "n/a"]
    evidence_text: str
    confidence_level: Literal["high", "medium", "low"]
    # Provenance (AGENTS.md prinsip #3): dari mana kesimpulan ini berasal
    evidence_source: Literal["rule_engine", "llm_local", "fallback_no_data"] = "rule_engine"
    # Sinyal rule-based yang menentukan skor klinis (bukan dari LLM)
    rule_flags: List[str] = Field(default_factory=list)
    model_used: Optional[str] = None  # nama model LLM jika Lapis 2 dipakai

class SHAPFeature(BaseModel):
    feature_name: str
    feature_label: str = ""  # terjemahan ramah pengguna
    contribution: float
    direction: Literal["positive", "negative"]

class FinancialAssessment(BaseModel):
    claim_id: str
    predicted_cost_range: Tuple[float, float]
    actual_cost: float
    deviation_pct: float
    shap_top_features: List[SHAPFeature]
    anomaly_score: float
    evidence_text: str = ""
    # Provenance: "xgboost_model" atau "zscore_peer_fallback"
    method: Literal["xgboost_model", "zscore_peer_fallback"] = "xgboost_model"

class SimilarClaim(BaseModel):
    """
    Klaim historis serupa — skor KOMPOSIT multi-faktor (bukan cosine pola medis saja):
    kode medis 40% + kedekatan biaya 30% + faskes sama 15% + jarak waktu 10% + pasien sama 5%.
    Rincian per-faktor ikut dikirim agar verifier melihat MENGAPA dianggap mirip.
    """
    claim_id: str
    similarity: float              # komposit 0-1 (dipakai ranking & tampilan utama)
    code_similarity: float = 0.0   # Jaccard kode medis 0-1
    cost_proximity: float = 0.0    # kedekatan biaya 0-1
    same_provider: bool = False
    same_patient: bool = False
    days_apart: Optional[int] = None
    profile_cosine: float = 0.0    # cosine profil medis (info tambahan)
    jaccard: float = 0.0
    provider_id: str = ""
    patient_id: str = ""
    diagnosis_primary: str = ""
    cost_claimed: float = 0.0

class FraudAssessment(BaseModel):
    claim_id: str
    similarity_max_score: float
    similarity_matched_claim_id: Optional[str] = None
    repeat_billing_flag: bool
    repeat_billing_matched_claim_id: Optional[str] = None
    # Cloning sungguhan: sangat mirip + pasien BERBEDA + faskes SAMA.
    # Kemiripan tinggi antar-faskes berbeda = pola penyakit wajar, BUKAN cloning.
    cloning_flag: bool = False
    unbundling_flag: bool = False
    unbundling_matched_claim_ids: List[str] = Field(default_factory=list)
    graph_cluster_anomaly_score: float  # dari provider network metrics precomputed
    isolation_forest_score: float = 0.0
    is_isolation_forest_outlier: bool = False
    evidence_text: str
    similar_claims: List[SimilarClaim] = Field(default_factory=list)

class ReviewSynthesis(BaseModel):
    claim_id: str
    evidence_level: Literal["strong_multi_signal", "single_signal", "weak"]
    corroborating_signals: List[str]
    reasoning_narrative: str
    reasoning_source: Literal["llm_direct", "llm_reasoning_trace", "rule_fallback"]
    model_used: Optional[str] = None

class RiskScore(BaseModel):
    total_score: float # 0-100
    breakdown: Dict[str, float]
    priority_tier: Literal["high", "medium", "low"]

class QAPanel(BaseModel):
    why_top_priority: str
    most_similar_claim: str
    strongest_evidence: str
    is_this_fraud: str = "Sistem ini tidak menentukan status fraud. Skor dan evidence yang ditampilkan adalah rekomendasi prioritas untuk verifikasi manusia — keputusan akhir selalu berada di tangan verifier BPJS."

class ClaimExplanation(BaseModel):
    claim_id: str
    narrative_id: str
    ranked_reasons: List[str]
    recommended_action: Literal["verify_immediately", "review_when_available", "low_priority"]
    qa_panel: QAPanel
    # Provenance narasi (FRONTEND.md 5e): model apa yang menulis narasi ini
    generated_by: str = "template_fallback"

class AgentError(BaseModel):
    agent_name: str
    error_type: Literal["schema_invalid", "timeout", "tool_failure", "exception"]
    raw_output: Optional[str] = None
    fallback_applied: bool

class RiskAssessment(BaseModel):
    claim_id: str
    score: Optional[RiskScore] = None
    evidence: Optional[ReviewSynthesis] = None
    narrative: Optional[ClaimExplanation] = None
    partial: bool = False
    agent_errors: List[AgentError] = Field(default_factory=list)
    rejected: bool = False
    reject_reason: Optional[str] = None
    exact_duplicate: bool = False

    @classmethod
    def create_rejected(cls, claim_id: str, reason: str):
        return cls(claim_id=claim_id, rejected=True, reject_reason=reason)

class HumanDecision(BaseModel):
    claim_id: str
    decision: Literal["Verified Valid", "Needs Further Review", "Escalate", "Request Clarification"]
    reviewer: str
    timestamp: Optional[str] = None
