"""
Explanation Agent — merangkai skor + evidence menjadi narasi Bahasa Indonesia.

Prinsip (AGENTS.md Section 7):
- LLM TIDAK menentukan angka. Prompt menyediakan angka final; narasi wajib mengutipnya persis.
- VALIDASI WAJIB: semua angka di narasi di-parse dan dicocokkan dengan nilai sumber.
  Mismatch → retry (maks 2x) → fallback template.
- recommended_action diturunkan dari priority_tier (bukan dari LLM).
- QA Panel dihitung dari field yang SUDAH ada — nol LLM call tambahan.
"""
import re

from backend.app.models.schemas import (
    ClaimInput, ClinicalAssessment, FinancialAssessment, FraudAssessment,
    ReviewSynthesis, RiskScore, ClaimExplanation, QAPanel,
)
from backend.app.core.llm_client import (
    structured_completion, LLMError,
    EXPLANATION_MODEL, EXPLANATION_MODEL_FALLBACK, get_available_model,
    resolve_model_name,
)
from backend.app.core.human_language import (
    RULE_LABELS,
    SIGNAL_LABELS,
    format_rule_finding,
    humanize_rule,
    humanize_signal,
)

FRAUD_ANSWER = (
    "Sistem ini tidak menetapkan status fraud secara definitif. Skor dan temuan yang ditampilkan "
    "merupakan rekomendasi prioritas untuk membantu verifikasi — keputusan akhir sepenuhnya "
    "berada di tangan petugas verifier BPJS."
)

TIER_TO_ACTION = {
    "high": "verify_immediately",
    "medium": "review_when_available",
    "low": "low_priority",
}

# Sanitizer deterministik: nama key breakdown yang bocor ke narasi diganti label awam.
# Ini jaring pengaman terakhir di belakang instruksi prompt (model 7B kadang lolos).
_JARGON_MAP = {
    "similarity_fraud": "kemiripan riwayat klaim",
    "clinical_rule_flags": "kewajaran medis",
    "clinical_plausibility": "kewajaran medis",
    "isolation_forest_anomaly": "pola klaim yang menyimpang",
    "isolation_forest": "pola klaim yang menyimpang",
    "financial_anomaly": "perbedaan biaya",
    "evidence_support": "kekuatan dasar penilaian",
    "SHAP": "analisis faktor biaya",
    "XGBoost": "perkiraan biaya",
    "Jaccard": "kemiripan kode medis",
}


def _sanitize_jargon(text: str) -> str:
    for key, label in _JARGON_MAP.items():
        text = text.replace(key, label)
    for key in (*RULE_LABELS, *SIGNAL_LABELS):
        text = text.replace(key, humanize_rule(key) if key in RULE_LABELS else humanize_signal(key))
    text = re.sub(r"\[[^\]]*(?:mistral|deepseek|qwen|llama)[^\]]*\]\s*", "Catatan tambahan: ", text, flags=re.I)
    text = text.replace("Flag", "Temuan").replace("flag", "temuan")
    text = text.replace("rule engine", "aturan pemeriksaan")
    text = text.replace("deterministik", "berdasarkan aturan pemeriksaan")
    text = text.replace("anomaly score", "nilai perbedaan")
    text = text.replace("repeat billing", "pengulangan klaim")
    text = text.replace("cloning", "kemiripan tidak wajar antar klaim")
    text = text.replace("unbundling", "pemisahan tindakan")
    return text


def _fmt_rp(x: float) -> str:
    return f"Rp {x:,.0f}".replace(",", ".")


def build_priority_reason(risk: RiskScore) -> str:
    """Deterministic QA wording so a clean claim is not described as a change."""
    if risk.priority_tier == "low":
        return (
            f"Prioritas rendah (nilai risiko {risk.total_score:.0f}/100) karena sistem tidak menemukan "
            "ketidakwajaran atau temuan risiko penting yang perlu ditindaklanjuti."
        )
    tier = "tinggi" if risk.priority_tier == "high" else "sedang"
    return f"Prioritas {tier} (nilai risiko {risk.total_score:.0f}/100) ditentukan dari beberapa temuan risiko yang saling mendukung."


def _normalize_tokens(text: str) -> list[float]:
    """Token angka → float. Titik diikuti tepat 3 digit = ribuan; selain itu desimal."""
    out = []
    for m in re.finditer(r"\d+(?:[.,]\d+)*", text):
        token = m.group()
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", token):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", ".")
        try:
            out.append(float(token))
        except ValueError:
            pass
    return out


def _validate_narrative(narrative: str, facts: dict) -> list[str]:
    """Cross-check angka narasi vs fakta sumber. Return daftar pelanggaran (kosong = valid)."""
    errors = []
    values = _normalize_tokens(narrative)

    # 1. Skor wajib disebut dengan benar (persis, atau pembulatannya)
    score = facts["score"]
    score_found = any(
        abs(v - score) < 0.05 or abs(v - round(score)) < 0.05 for v in values
    )
    if not score_found:
        errors.append(f"Skor risiko {score} tidak disebut dengan benar di narasi.")

    # 2. Deviasi wajib disebut jika signifikan
    dev = facts.get("deviation_pct")
    if dev is not None and abs(dev) >= 1:
        if not any(abs(abs(v) - abs(dev)) < 0.5 for v in values):
            errors.append(f"Angka deviasi biaya {dev:.1f}% tidak disebut dengan benar.")

    # 3. Kemiripan wajib disebut jika tinggi
    sim = facts.get("similarity_pct")
    if sim and sim >= 50:
        if not any(abs(v - sim) < 0.5 for v in values):
            errors.append(f"Angka kemiripan {sim:.0f}% tidak disebut dengan benar.")

    return errors


def _similar_claim_text(fraud: FraudAssessment, claim_cost: float = 0.0) -> str:
    """Teks klaim serupa DENGAN konteks faktor — bukan sekadar persen."""
    if not fraud.similar_claims:
        # Prioritaskan repeat billing dari SQL (lebih konkret dari vector similarity)
        if fraud.repeat_billing_matched_claim_id:
            return (
                f"Terdeteksi pengulangan klaim dengan {fraud.repeat_billing_matched_claim_id} "
                f"— pasien dan tindakan yang sama ditemukan dalam rentang 45 hari. "
                f"Periksa apakah dua episode perawatan ini terpisah secara klinis."
            )
        if fraud.similarity_matched_claim_id:
            return f"Klaim yang paling mirip: {fraud.similarity_matched_claim_id} (tingkat kemiripan {fraud.similarity_max_score*100:.0f}%)."
        return "Tidak ada riwayat klaim yang mirip."
    top = fraud.similar_claims[0]
    faktor = [f"kode medis {top.code_similarity*100:.0f}% sama"]
    if top.cost_claimed > 0 and claim_cost > 0:
        selisih = abs(claim_cost - top.cost_claimed) / max(claim_cost, top.cost_claimed) * 100
        faktor.append(f"selisih biaya {selisih:.0f}%")
    if top.same_provider:
        faktor.append("faskes sama")
    if top.same_patient:
        faktor.append("pasien sama")
    if top.days_apart is not None:
        faktor.append(f"jarak {top.days_apart} hari")
    return (
        f"Klaim {top.claim_id} paling mirip (tingkat kemiripan gabungan {top.similarity*100:.0f}%: "
        f"{', '.join(faktor)}; biaya klaim lain {_fmt_rp(top.cost_claimed)}, "
        f"diagnosis {top.diagnosis_primary or 'N/A'}, faskes {top.provider_id or 'N/A'})."
    )


def _template_explanation(
    claim: ClaimInput, clinical: ClinicalAssessment, financial: FinancialAssessment,
    fraud: FraudAssessment, review: ReviewSynthesis, risk: RiskScore, facts: dict,
) -> ClaimExplanation:
    """Fallback template — kaku tapi 100% akurat."""
    # Low tier must not repeat an unverified LLM synthesis as a finding.
    reasons = [] if risk.priority_tier == "low" else [
        item.explanation for item in risk.evidence
        if item.source_family != "behavioral_context"
    ][:4]
    if not reasons:
        if financial.deviation_pct > 20:
            reasons.append(f"Biaya lebih tinggi {financial.deviation_pct:+.1f}% dari perkiraan kasus sejenis")
        if fraud.repeat_billing_flag:
            reasons.append("Kemungkinan pengulangan klaim pada peserta yang sama")
        if clinical.rule_flags:
            reasons.extend(format_rule_finding(flag) for flag in clinical.rule_flags)
    if not reasons:
        reasons.append("Tidak ditemukan indikasi anomali signifikan.")

    tier_label = {"high": "tinggi", "medium": "sedang", "low": "rendah"}[risk.priority_tier]
    top_reason = reasons[0].rstrip(".")
    narrative = (
        f"Klaim {claim.claim_id} mendapat nilai risiko {facts['score']:.0f} dari 100 "
        f"(prioritas {tier_label}). "
        + (f"Temuan utama: {top_reason}. " if reasons else "")
        + f"Biaya diklaim {_fmt_rp(claim.cost_claimed)}"
        + (
            f" dibandingkan perkiraan biaya penggantian {_fmt_rp(financial.predicted_cost_range[1] / 1.15)} (perbedaan {financial.deviation_pct:+.1f}%)."
            if financial.method == "xgboost_model" else "."
        )
    )

    similar_text = _similar_claim_text(fraud, claim.cost_claimed)

    strongest = max(risk.breakdown, key=risk.breakdown.get) if risk.breakdown else "financial_anomaly"
    strongest_label = {
        "financial_anomaly": "Perbedaan biaya",
        "clinical_rule_flags": "Temuan medis",
        "similarity_fraud": "Kemiripan klaim historis",
        "isolation_forest_anomaly": "Pola klaim yang menyimpang",
        "evidence_support": "Kekuatan dasar penilaian",
    }.get(strongest, _sanitize_jargon(strongest))

    return ClaimExplanation(
        claim_id=claim.claim_id,
        narrative_id=narrative,
        ranked_reasons=reasons,
        recommended_action=TIER_TO_ACTION[risk.priority_tier],
        qa_panel=QAPanel(
            why_top_priority=build_priority_reason(risk),
            most_similar_claim=similar_text,
            strongest_evidence=f"{strongest_label}: {risk.breakdown.get(strongest, 0):.1f} poin dari total {facts['score']:.0f}. " +
                               (financial.evidence_text if strongest == "financial_anomaly" else ""),
            is_this_fraud=FRAUD_ANSWER,
        ),
        generated_by="template_fallback",
    )


async def generate_explanation(
    claim: ClaimInput,
    clinical: ClinicalAssessment,
    financial: FinancialAssessment,
    fraud: FraudAssessment,
    review: ReviewSynthesis,
    risk: RiskScore,
) -> ClaimExplanation:
    # ---------- Fakta final yang BOLEH dikutip narasi ----------
    # Kemiripan antar-faskes berbeda tanpa kontensi cloning/repeat = pola penyakit wajar,
    # TIDAK dikutip sebagai temuan agar narasi tidak menyesatkan verifier.
    relational_signal = bool(fraud.repeat_billing_flag or fraud.cloning_flag)
    facts = {
        "score": risk.total_score,
        "tier": risk.priority_tier,
        "deviation_pct": financial.deviation_pct if financial.method == "xgboost_model" else None,
        "similarity_pct": fraud.similarity_max_score * 100 if (relational_signal and fraud.similarity_max_score > 0.6) else None,
        "actual_cost": claim.cost_claimed,
    }

    # A low-priority result is a clean/weak-signal outcome. Keep its narrative
    # deterministic so an LLM cannot introduce an unsupported fraud finding.
    if risk.priority_tier == "low":
        return _template_explanation(claim, clinical, financial, fraud, review, risk, facts)

    model = await get_available_model(EXPLANATION_MODEL, EXPLANATION_MODEL_FALLBACK)

    breakdown_items = sorted(risk.breakdown.items(), key=lambda x: -x[1])
    nonzero = [(k, v) for k, v in breakdown_items if v > 0.05]
    if nonzero:
        breakdown_lines = "\n".join(f"- {k}: {v:.1f} poin" for k, v in nonzero)
    else:
        breakdown_lines = "- (tidak ada komponen yang menyumbang skor berarti — klaim bersih)"

    top_shap = financial.shap_top_features[0].feature_label if financial.shap_top_features else "N/A"

    context = f"""
Tulis laporan ringkas untuk petugas verifier BPJS berdasarkan FAKTA final berikut.

FAKTA FINAL (angka ini SUDAH FINAL — wajib dikutip PERSIS, dilarang membulatkan/mengubah):
- Claim ID: {claim.claim_id}
- Skor risiko: {risk.total_score:.1f} dari 100 (prioritas: {risk.priority_tier})
- Biaya diklaim: {_fmt_rp(claim.cost_claimed)}
- Deviasi biaya vs prediksi model: {f"{financial.deviation_pct:+.1f}%" if facts["deviation_pct"] is not None else "tidak tersedia (fallback statistik)"}
- Faktor biaya terbesar (SHAP): {top_shap}
- Kemiripan klaim historis tertinggi: {f"{fraud.similarity_max_score*100:.0f}%" if facts["similarity_pct"] else "tidak signifikan (pola penyakit wajar)"}
- Indikasi repeat billing: {"YA" if fraud.repeat_billing_flag else "TIDAK"}
- Indikasi cloning (faskes sama, pasien beda): {"YA" if fraud.cloning_flag else "TIDAK"}
- Flag klinis rule engine: {", ".join(clinical.rule_flags) if clinical.rule_flags else "tidak ada"}
- Evidence ID yang tersedia: {", ".join(item.evidence_id for item in risk.evidence) or "tidak ada"}

KONTRIBUSI SKOR:
{breakdown_lines}

SINTESIS REVIEW: {review.reasoning_narrative}
"""

    system_prompt = (
        "Kamu adalah asisten analis klaim BPJS Kesehatan yang menulis untuk staf verifier non-IT. "
        "ATURAN MUTLAK:\n"
        "1. Bahasa Indonesia baku, mengalir seperti laporan — BUKAN daftar/dump data.\n"
        "2. narrative_id: 2-4 kalimat utuh. WAJIB menyebut nomor klaim, skor risiko persis dari fakta, "
        "dan 1-2 alasan utama dengan angka persis. Contoh gaya (jangan salin angkanya): "
        "'Klaim CLM-567 mendapat skor 82 dari 100 sehingga masuk prioritas tinggi. "
        "Biaya klaim Rp 84.646.949 tercatat 129% lebih tinggi dari prediksi model untuk kasus sejenis, "
        "dan terdapat indikasi pengulangan klaim pada pasien yang sama. "
        "Disarankan verifikasi dokumen penunjang sebelum persetujuan.'\n"
        "3. DILARANG mengubah, membulatkan, atau menambah angka yang tidak ada di fakta.\n"
        "4. DILARANG memakai istilah teknis atau nama key (isolation forest, SHAP, Jaccard, XGBoost, "
        "embedding, similarity_fraud, clinical_rule_flags, evidence_support). "
        "Ganti dengan bahasa awam: 'pola anomali', 'kemiripan riwayat klaim', 'flag kewajaran medis'.\n"
        "5. DILARANG menyimpulkan klaim ini fraud — hanya tingkat kebutuhan verifikasi.\n"
        "6. why_top_priority: 1-2 kalimat mengalir dengan angka persis (bukan fragmen).\n"
        "7. strongest_evidence: 1 kalimat utuh temuan terkuat dengan angka persis.\n"
        "8. ranked_reasons: maksimal 4 alasan berupa frasa/kalimat singkat yang mengandung angka persis.\n"
        "9. evidence_ids wajib berisi hanya ID evidence yang tersedia pada fakta final.\n"
        "10. Semua output dalam Bahasa Indonesia."
        "\n11. Jika prioritas rendah, jelaskan sebagai 'tidak ditemukan ketidakwajaran atau sinyal risiko signifikan' "
        "dan JANGAN menulis 'tidak ada yang menunjukkan perubahan'."
    )

    from pydantic import BaseModel

    class LLMExplanationResponse(BaseModel):
        narrative_id: str
        ranked_reasons: list[str]
        why_top_priority: str
        strongest_evidence: str
        evidence_ids: list[str] = []

    try:
        response = await structured_completion(
            prompt=context,
            system_prompt=system_prompt,
            output_schema=LLMExplanationResponse,
            model=model,
            temperature=0.1,
        )

        # ---------- VALIDASI WAJIB: angka narasi vs fakta ----------
        narrative = _sanitize_jargon(response.narrative_id.strip())
        violations = _validate_narrative(narrative, facts)
        if violations:
            raise LLMError("Validasi angka narasi gagal: " + " | ".join(violations[:3]))

        allowed_evidence = {item.evidence_id: item for item in risk.evidence}
        requested_evidence = getattr(response, "evidence_ids", None)
        if requested_evidence is None:
            raise LLMError("Explanation Agent tidak mengembalikan evidence_ids.")
        if not requested_evidence or any(item_id not in allowed_evidence for item_id in requested_evidence):
            raise LLMError("Explanation Agent mengembalikan evidence_id yang tidak tersedia.")
        selected_evidence = [allowed_evidence[item_id] for item_id in requested_evidence]

        similar_claim_text = _similar_claim_text(fraud, claim.cost_claimed)

        strongest = max(risk.breakdown, key=risk.breakdown.get) if risk.breakdown else "financial_anomaly"
        strongest_label = {
            "financial_anomaly": "Anomali finansial",
            "clinical_rule_flags": "Flag klinis (rule engine)",
            "similarity_fraud": "Kemiripan klaim historis",
            "isolation_forest_anomaly": "Anomali pola perilaku",
            "evidence_support": "Kekuatan bukti deterministik",
        }.get(strongest, _sanitize_jargon(strongest))

        return ClaimExplanation(
            claim_id=claim.claim_id,
            narrative_id=narrative,
            ranked_reasons=[_sanitize_jargon(item.explanation) for item in selected_evidence[:4]],
            recommended_action=TIER_TO_ACTION[risk.priority_tier],  # dari tier, bukan LLM
            qa_panel=QAPanel(
                why_top_priority=build_priority_reason(risk),
                most_similar_claim=similar_claim_text,
            strongest_evidence=_sanitize_jargon(" ".join(item.explanation for item in selected_evidence[:2])),
                is_this_fraud=FRAUD_ANSWER,  # hardcoded, tidak pernah dari LLM
            ),
            generated_by=resolve_model_name(model),
        )

    except Exception as e:
        # print() harus aman cp1252 (console Windows): karakter Unicode seperti
        # '→' memicu UnicodeEncodeError pada fallback path dan mematikan analisis.
        print(f"[explanation] LLM gagal/divalidasi ulang -> template fallback: {e}")
        return _template_explanation(claim, clinical, financial, fraud, review, risk, facts)
