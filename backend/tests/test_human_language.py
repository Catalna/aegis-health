from backend.app.core.human_language import (
    format_benchmark_finding,
    humanize_finding,
    humanize_rule,
    humanize_signal,
)
from backend.app.core.public_analysis import public_analysis_projection


def test_rule_names_become_formal_human_language():
    assert humanize_rule("severity_med_mismatch") == (
        "perbedaan tingkat keparahan dengan biaya pengobatan"
    )
    assert humanize_rule("severity_proc_mismatch") == (
        "ketidaksesuaian tingkat keparahan dengan tindakan"
    )
    assert humanize_rule("los_outlier") == "lama rawat jauh di atas pola umum"
    assert humanize_rule("upcoding_risk_diag") == (
        "tingkat keparahan diagnosis perlu diverifikasi"
    )
    assert "_" not in humanize_rule("severity_med_mismatch")


def test_signal_names_explain_claim_relationships_without_technical_labels():
    assert humanize_signal("repeat_billing") == "pengulangan klaim pada peserta yang sama"
    assert humanize_signal("cloning") == "kemiripan tidak wajar antar klaim"
    assert humanize_signal("unbundling") == "pemisahan tindakan yang perlu diperiksa"


def test_benchmark_finding_uses_indonesian_report_wording():
    assert format_benchmark_finding(4_000_000, 1_902_113, 110.3, "jenis diagnosis") == (
        "Biaya yang diajukan sebesar Rp4.000.000 lebih tinggi 110,3% "
        "dibandingkan perkiraan biaya penggantian sebesar Rp1.902.113. "
        "Perbedaan ini terutama dipengaruhi oleh jenis diagnosis."
    )


def test_technical_finding_sentence_is_rewritten():
    assert humanize_finding("Sinyal deterministik: severity_med_mismatch.") == (
        "Temuan berdasarkan aturan pemeriksaan: tingkat keparahan yang tercatat "
        "tidak sebanding dengan biaya pengobatan yang diajukan."
    )


def test_public_analysis_does_not_expose_model_names_or_internal_rule_codes():
    result = public_analysis_projection({
        "model_used": "mistral:7b",
        "generated_by": "mistral:7b",
        "clinical": {
            "model_used": "mistral:7b",
            "rule_flags": ["severity_med_mismatch"],
            "evidence_text": "Sinyal deterministik: severity_med_mismatch.",
        },
    })
    assert "model_used" not in result
    assert "generated_by" not in result
    assert "severity_med_mismatch" not in str(result)
    assert "mistral:7b" not in str(result)
