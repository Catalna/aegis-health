"""Formal Indonesian wording for claim findings shown to officers."""

import re


RULE_LABELS = {
    "tariff_deviation_extreme": "biaya jauh di atas perkiraan biaya penggantian",
    "tariff_deviation_high": "biaya di atas perkiraan biaya penggantian",
    "severity_proc_mismatch": "ketidaksesuaian tingkat keparahan dengan tindakan",
    "severity_med_mismatch": "perbedaan tingkat keparahan dengan biaya pengobatan",
    "los_outlier": "lama rawat jauh di atas pola umum",
    "upcoding_risk_diag": "tingkat keparahan diagnosis perlu diverifikasi",
    "unsupported_high_risk_proc": "tindakan berbiaya tinggi perlu didukung dokumen",
}

SIGNAL_LABELS = {
    "repeat_billing": "pengulangan klaim pada peserta yang sama",
    "cloning": "kemiripan tidak wajar antar klaim",
    "unbundling": "pemisahan tindakan yang perlu diperiksa",
}


def humanize_rule(value: str) -> str:
    return RULE_LABELS.get(value, value.replace("_", " "))


def humanize_signal(value: str) -> str:
    return SIGNAL_LABELS.get(value, value.replace("_", " "))


def format_rule_finding(value: str) -> str:
    messages = {
        "severity_proc_mismatch": (
            "Tingkat keparahan yang tercatat tidak sebanding dengan tindakan yang diajukan."
        ),
        "severity_med_mismatch": (
            "Tingkat keparahan yang tercatat tidak sebanding dengan biaya pengobatan yang diajukan."
        ),
        "los_outlier": "Lama rawat jauh di atas pola umum untuk kasus sejenis.",
        "upcoding_risk_diag": "Diagnosis sekunder perlu diverifikasi karena tingkat keparahannya.",
        "unsupported_high_risk_proc": (
            "Tindakan berbiaya tinggi perlu didukung dokumen dan kesesuaian diagnosis."
        ),
        "tariff_deviation_high": "Biaya yang diajukan berada di atas perkiraan biaya penggantian.",
        "tariff_deviation_extreme": (
            "Biaya yang diajukan jauh di atas perkiraan biaya penggantian."
        ),
    }
    return messages.get(value, humanize_rule(value).capitalize() + ".")


def _format_rupiah(value: float) -> str:
    return f"Rp{value:,.0f}".replace(",", ".")


def format_benchmark_finding(
    actual_cost: float,
    benchmark_cost: float,
    deviation_pct: float,
    main_factor: str,
) -> str:
    direction = "lebih tinggi" if deviation_pct >= 0 else "lebih rendah"
    deviation = f"{abs(deviation_pct):.1f}".replace(".", ",")
    return (
        f"Biaya yang diajukan sebesar {_format_rupiah(actual_cost)} {direction} "
        f"{deviation}% dibandingkan perkiraan biaya penggantian "
        f"sebesar {_format_rupiah(benchmark_cost)}. Perbedaan ini terutama "
        f"dipengaruhi oleh {main_factor}."
    )


def humanize_finding(value: str) -> str:
    match = re.fullmatch(r"Sinyal deterministik:\s*([a-z0-9_]+)\.?", value.strip(), re.I)
    if match:
        finding = format_rule_finding(match.group(1))
        return f"Temuan berdasarkan aturan pemeriksaan: {finding[0].lower()}{finding[1:]}"
    return value


def humanize_public_text(value: str) -> str:
    """Remove implementation vocabulary from legacy text before it is exposed."""
    value = humanize_finding(value)
    for key in (*RULE_LABELS, *SIGNAL_LABELS):
        value = value.replace(key, humanize_rule(key) if key in RULE_LABELS else humanize_signal(key))
    value = re.sub(
        r"\[[^\]]*(?:mistral|deepseek|qwen|llama)[^\]]*\]\s*",
        "Catatan tambahan: ", value, flags=re.I
    )
    return value.replace("Sinyal deterministik", "Temuan berdasarkan aturan pemeriksaan")
