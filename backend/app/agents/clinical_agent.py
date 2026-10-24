"""
Clinical Reasoning Agent — 2 lapis sesuai AGENTS.md Section 2.

Lapis 1 (SELALU, deterministik): INA-CBG grouper lookup + rule compatibility check.
  - Skor klinis BERASAL DARI SINI (rule_flags), bukan dari LLM.
Lapis 2 (HANYA kasus ambigu): LLM lokal menilai plausibility untuk kombinasi
  diagnosis-prosedur yang tidak ada di tabel referensi. Output LLM HANYA
  menambah evidence_text + confidence_level — TIDAK mengubah skor numerik.
"""
import logging

from backend.app.models.schemas import ClaimInput, ClinicalAssessment, CBGLookupResult
from backend.app.core.llm_client import structured_completion, LLMError, CLINICAL_MODEL, resolve_model_name
from backend.app.core.errors import failure_for_exception
from backend.app.core.human_language import format_rule_finding
from backend.app.data.ina_cbg_rules import (
    DIAGNOSIS_LABELS, DIAGNOSIS_TO_CBG_MAPPING, PROCEDURE_LABELS,
    calculate_expected_tariff,
)
from backend.app.ml.feature_engineering import EXPECTED_LOS
from backend.app.ml.feature_engineering import PHANTOM_RISK_PROCS


SUPPORTED_HIGH_RISK_PROCS = {
    "I21": {"36.10"},
    "N18": {"39.95"},
    "C50": {"85.41"},
    "S72": {"81.51"},
}

logger = logging.getLogger(__name__)


def _diag_name(code: str) -> str:
    if code in DIAGNOSIS_LABELS:
        return DIAGNOSIS_LABELS[code]
    base = code.split(".")[0] if "." in code else code
    info = DIAGNOSIS_TO_CBG_MAPPING.get(base)
    return info.name if info else code


def _procedure_name(code: str) -> str:
    return PROCEDURE_LABELS.get(code, code)


def _rule_flags(claim: ClaimInput, tariff_deviation: float | None, known_diag: bool) -> list[str]:
    """Sinyal deterministik — satu-satunya sumber skor klinis (prinsip non-negotiable #1)."""
    flags: list[str] = []

    if known_diag and tariff_deviation is not None:
        if tariff_deviation > 100:
            flags.append("tariff_deviation_extreme")
        elif tariff_deviation > 50:
            flags.append("tariff_deviation_high")

    # Severity tinggi tanpa prosedur → indikasi upcoding severity
    if claim.severity_level >= 3 and len(claim.procedure_codes) == 0:
        flags.append("severity_proc_mismatch")

    # Severity tinggi tapi obat < 2 jenis → indikasi upcoding severity
    if claim.severity_level >= 3 and len(claim.medication) < 2:
        flags.append("severity_med_mismatch")

    # LOS jauh di atas rentang klinis wajar
    base = claim.diagnosis_primary.split(".")[0]
    los_range = EXPECTED_LOS.get(base)
    if los_range and claim.length_of_stay > los_range[1] * 2:
        flags.append("los_outlier")

    # Diagnosis sekunder komplikasi yang umum dipakai upcoding tanpa prosedur pendukung
    upcoding_risk = {"A41.9", "Z87.39", "E46"}
    if claim.severity_level >= 3 and any(d in upcoding_risk for d in claim.diagnosis_secondary):
        flags.append("upcoding_risk_diag")

    # A high-cost procedure must have a diagnosis context that supports it.
    # This is a review signal, not a claim that the procedure was definitely absent.
    supported_procs = SUPPORTED_HIGH_RISK_PROCS.get(base, set())
    if any(p in PHANTOM_RISK_PROCS and p not in supported_procs for p in claim.procedure_codes):
        flags.append("unsupported_high_risk_proc")

    return flags


def _plausibility_from_flags(flags: list[str]) -> tuple[str, str]:
    """Petakan rule flags → plausibility deterministik."""
    if "tariff_deviation_extreme" in flags:
        return "implausible", "high"
    hard = [f for f in flags if f in ("severity_proc_mismatch", "severity_med_mismatch", "los_outlier", "upcoding_risk_diag", "tariff_deviation_high")]
    if len(hard) >= 2:
        return "implausible", "high"
    if len(hard) == 1:
        return "questionable", "medium"
    return "plausible", "high"


async def analyze_clinical(claim: ClaimInput) -> ClinicalAssessment:
    base = claim.diagnosis_primary.split(".")[0]
    known_diag = base in DIAGNOSIS_TO_CBG_MAPPING

    # ---------- Lapis 1: Rule engine (selalu jalan) ----------
    grouper_result = calculate_expected_tariff(
        claim.diagnosis_primary, claim.procedure_codes, claim.severity_level
    )
    cbg_info = None
    tariff_deviation = None
    if grouper_result:
        code, name, expected_tariff = grouper_result
        cbg_info = CBGLookupResult(cbg_code=code, cbg_name=name, base_tariff=expected_tariff)
        if expected_tariff > 0:
            tariff_deviation = ((claim.cost_claimed - expected_tariff) / expected_tariff) * 100

    flags = _rule_flags(claim, tariff_deviation, known_diag)
    rule_plausibility, rule_confidence = _plausibility_from_flags(flags)

    # Bangun evidence text deterministik dari rule
    parts = []
    if cbg_info:
        parts.append(
            f"Klaim sesuai dengan kelompok layanan {cbg_info.cbg_code} ({cbg_info.cbg_name}); "
            f"tarif referensi Rp {cbg_info.base_tariff:,.0f}, deviasi klaim "
            f"{'+' if (tariff_deviation or 0) >= 0 else ''}{tariff_deviation:.1f}%."
        )
    else:
        parts.append(f"Diagnosis {claim.diagnosis_primary} belum tersedia dalam tabel acuan biaya layanan.")

    for f in flags:
        parts.append(format_rule_finding(f))

    # ---------- Keputusan apakah Lapis 2 (LLM) diperlukan ----------
    ambiguous = (not known_diag) or (len(flags) == 1 and rule_plausibility == "questionable")

    if not ambiguous:
        # Kasus jelas — tidak perlu LLM (hemat, konsisten, anti-halusinasi)
        evidence = " ".join(parts)
        if rule_plausibility == "plausible" and not flags:
            evidence = (
                f"Kombinasi diagnosis, tindakan, dan tingkat keparahan sesuai tabel acuan. " + evidence
            ).strip()
        return ClinicalAssessment(
            claim_id=claim.claim_id,
            grouper_result=cbg_info,
            tariff_deviation_pct=tariff_deviation,
            compatibility_status="match_table" if known_diag else "no_data",
            plausibility=rule_plausibility if known_diag else "n/a",
            evidence_text=evidence if flags or cbg_info else "Tidak ditemukan anomali klinis dari rule engine.",
            confidence_level=rule_confidence if known_diag else "low",
            evidence_source="rule_engine",
            rule_flags=flags,
            model_used=None,
        )

    # ---------- Lapis 2: LLM hanya untuk kasus ambigu ----------
    diag_secondary_names = [f"{c} ({_diag_name(c)})" for c in claim.diagnosis_secondary]
    prompt = f"""
Evaluasi kewajaran klinis klaim JKN berikut.

Diagnosis Primer: {claim.diagnosis_primary} ({_diag_name(claim.diagnosis_primary)})
Diagnosis Sekunder: {", ".join(diag_secondary_names) if diag_secondary_names else "Tidak ada"}
 Prosedur: {", ".join(f"{c} ({_procedure_name(c)})" for c in claim.procedure_codes) if claim.procedure_codes else "Tidak ada"}
Obat: {", ".join([f"{m.name} x{m.quantity}" for m in claim.medication]) if claim.medication else "Tidak ada"}
Severity Level: {claim.severity_level} (skala 1-4)
Lama Rawat: {claim.length_of_stay} hari
Biaya Diklaim: Rp {claim.cost_claimed:,.0f}

Pertanyaan: Apakah kombinasi diagnosis-prosedur-obat-severity ini masuk akal secara klinis?
Contoh anomali: diagnosis ringan dengan LOS/severity/obat berlebihan, atau diagnosis berat
tanpa prosedur/obat yang semestinya.

plausibility harus PERSIS salah satu dari: "plausible", "questionable", "implausible".
confidence_level harus PERSIS salah satu dari: "high", "medium", "low".
evidence_text: 1-2 kalimat Bahasa Indonesia yang menyebut fakta spesifik dari data di atas.
"""
    system_prompt = (
        "Kamu adalah auditor klinis ahli program JKN (BPJS Kesehatan). Deteksi upcoding, "
        "phantom billing, dan kombinasi medis tidak wajar. Jawab HANYA berdasarkan data yang "
        "diberikan — jangan mengarang fakta tambahan. Seluruh respons dalam Bahasa Indonesia."
    )

    from pydantic import BaseModel

    class LLMClinicalResponse(BaseModel):
        plausibility: str
        evidence_text: str
        confidence_level: str

    try:
        llm = await structured_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            output_schema=LLMClinicalResponse,
            model=CLINICAL_MODEL,
            temperature=0.1,
        )
        llm_plausibility = llm.plausibility if llm.plausibility in ("plausible", "questionable", "implausible") else "questionable"
        confidence = llm.confidence_level if llm.confidence_level in ("high", "medium", "low") else "medium"

        # LLM boleh MENGESKALASI temuan rule (questionable→implausible), tetapi
        # tidak boleh MENGHAPUS flag rule (implausible/questionable→plausible).
        severity_rank = {"plausible": 0, "questionable": 1, "implausible": 2}
        final_plausibility = max(
            llm_plausibility, rule_plausibility, key=lambda p: severity_rank[p]
        ) if flags else llm_plausibility

        # Label sumber jelas sesuai spek: evidence dari LLM diberi awalan sumber
        evidence = "Catatan tambahan dari penilaian medis: " + llm.evidence_text
        if flags:
            evidence += " Temuan berdasarkan aturan pemeriksaan: " + "; ".join(
                format_rule_finding(flag).rstrip(".") for flag in flags
            ) + "."

        return ClinicalAssessment(
            claim_id=claim.claim_id,
            grouper_result=cbg_info,
            tariff_deviation_pct=tariff_deviation,
            compatibility_status="llm_assessed",
            plausibility=final_plausibility,
            evidence_text=evidence,
            confidence_level=confidence,
            evidence_source="llm_local",
            rule_flags=flags,  # skor tetap dari rule, LLM hanya melengkapi narasi
            model_used=resolve_model_name(CLINICAL_MODEL),
        )
    except LLMError as e:
        # Fallback sesuai AGENTS.md: no_data + n/a, bukan menebak
        logger.exception("Clinical LLM fallback for claim_id=%s", claim.claim_id)
        failure = failure_for_exception(e)
        return ClinicalAssessment(
            claim_id=claim.claim_id,
            grouper_result=cbg_info,
            tariff_deviation_pct=tariff_deviation,
            compatibility_status="no_data",
            plausibility="n/a",
            evidence_text=(
                "Catatan tambahan dari penilaian medis belum tersedia. "
                + " ".join(parts)
            ).strip(),
            confidence_level="low",
            evidence_source="fallback_no_data",
            rule_flags=flags,
            model_used=None,
        )
