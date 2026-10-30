# -*- coding: utf-8 -*-
"""Unit test checker anti-halusinasi generik (F2, spec 2026-10-28-flow-maximization-design.md).

Pustaka murni — tanpa DB, tanpa Ollama. Kasus dunia-nyata dipatok dari benchmark
llm_bench (konversi persen/juta yang diamati pada deepseek-r1:7b, dan sapaan fiktif "Enyi").
"""
import pytest

from backend.app.core.llm_guard import (
    GuardError,
    GuardResult,
    check_names,
    check_numbers,
    extract_numbers,
    guard_report,
    harvest_numbers,
    _parse_number_token,
)

ENV = {
    "env_version": 1,
    "divisi": "model_biaya_kandidat_C",
    "catatan_domain": "data riil BPJS sampel 2025; parity penuh",
    "views": {"test_semua": {"n": 340518, "mape_pct": 8.59, "medape_pct": 3.42}},
    "konteks": {"r2": 0.8184, "prevalensi": 0.2142},
}


# ------------------------------------------------------- parsing token Indonesia
@pytest.mark.parametrize("tok,expected", [
    ("8.59", "8.59"),
    ("0,2142", "0.2142"),
    ("21,4", "21.4"),
    ("1.340.872", "1340872"),
    ("1,340,872", "1340872"),
    ("1.340", "1340"),           # konvensi ribuan (bukan bagian-0, tepat 3 digit)
    ("0.347", "0.347"),          # bagian-utama "0" → desimal
    ("1.340,87", "1340.87"),     # pemisah terakhir = desimal
    ("1,340.87", "1340.87"),
    ("2025", "2025"),
])
def test_parse_number_token(tok, expected):
    assert _parse_number_token(tok) is not None
    assert str(_parse_number_token(tok)) == expected


def test_extract_numbers_sequence():
    vals = [v for _, v in extract_numbers("MAPE 8.59 (n=340.518), atau 8,59 retak.") ]
    assert [str(v) for v in vals] == ["8.59", "340518", "8.59"]


# ------------------------------------------------------- harvest envelope
def test_harvest_numbers_includes_strings_and_values():
    targets = harvest_numbers(ENV)
    vals = {str(t) for t in targets}
    assert {"8.59", "340518", "3.42", "0.8184", "0.2142", "2025"} <= vals


def test_harvest_skips_bools():
    assert harvest_numbers({"flag": True}) == set()


# ------------------------------------------------------- check_numbers
def test_traceable_raw_number():
    assert check_numbers("MAPE test 8.59 persen terhadap 340.518 klaim.", ENV) == []


def test_traceable_percent_conversion():
    # 0.2142 (envelope) → "21,4%" di report (×100, pembulatan 2 desimal)
    assert check_numbers("Prevalensi anomali 21,4% dari populasi.", ENV) == []


def test_traceable_juta_conversion():
    # 340518 (envelope? tidak ada!) — pakai 1.340.872 di envelope tambahan
    env = {**ENV, "views": {**ENV["views"], "rupiah_total": 1340872}}
    assert check_numbers("Total nilai klaim 1,34 juta rupiah.", env) == []


def test_invented_number_is_flagged():
    viol = check_numbers("Angka wow 42 persen muncul tak sumber.", ENV)
    assert len(viol) == 1 and viol[0]["token"] == "42"


def test_rounding_within_tolerance_passes():
    # 21,42% vs envelope 21.4? toleransi rel 0.5% dari 21.4 ≈ 0.107 > 0.02
    env = {**ENV, "views": {"s": {"prevalensi_persen": 21.4}}}
    assert check_numbers("Rasio ini 21,42%.", env) == []


def test_outside_tolerance_flagged():
    env = {**ENV, "views": {"s": {"mape_pct": 8.59}}}
    viol = check_numbers("MAPE-nya 9.90%.", env)
    assert len(viol) == 1


def test_year_in_envelope_text_is_traceable():
    assert check_numbers("Data Sampel 2025 dipakai sebagai dasar.", ENV) == []


# ------------------------------------------------------- check_names / sapaan
def test_salutation_penipu_flagged_enyi():
    assert "Enyi" in check_names("Enyi, berikut ringkasan model biaya.", ENV)


def test_normal_opener_not_flagged():
    assert check_names("Berdasarkan envelope, temuan utama: MAPE 8.59.", ENV) == []


def test_strict_flags_unknown_token_passes_known():
    viol = check_names("Kandidat model ini milik Divisi Modeling Seni.",
                       ENV, strict=True)
    # "Kandidat"/"Divisi" ada di whitelist builtin (lolos); "Modeling"/"Seni" tidak ada
    # di manifold sumber envelope maupun whitelist → adil, ter-flag.
    assert "Seni" in viol
    assert "Modeling" in viol


def test_strict_passes_names_from_envelope():
    env = {"divisi": "d", "catatan_domain": "laporan Menurut Dr Ani", "views": {}}
    assert check_names("Menurut Ani terlihat jelas.", env, strict=True) == []


# ------------------------------------------------------- guard_report
def test_guard_report_ok_and_notok():
    env = {**ENV}
    r_ok = guard_report("MAPE 8.59 persen pada 340.518 klaim.", env, mode="strict")
    assert isinstance(r_ok, GuardResult) and r_ok.ok and r_ok.n_angka_checked >= 2

    r_bad = guard_report("Enyi, angka 42 persen muncul.", env, mode="strict")
    assert not r_bad.ok and r_bad.angka_violasi and r_bad.nama_violasi == ["Enyi"]


def test_guard_report_numbers_mode_ignores_salutation():
    r = guard_report("Enyi, MAPE 8.59 persen.", ENV, mode="numbers")
    assert r.ok and r.mode == "numbers"


def test_guard_report_invalid_mode_raises():
    with pytest.raises(GuardError):
        guard_report("teks", ENV, mode="salah")
