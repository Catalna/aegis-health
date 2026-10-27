# -*- coding: utf-8 -*-
"""Unit test kontrak envelope (F1, spec 2026-10-28-flow-maximization-design.md).

Pustaka murni — tanpa DB, tanpa Ollama, tanpa menyentuh konfigurasi runtime.
"""
import json

import pytest

from backend.app.core.envelope import (
    ENV_VERSION,
    EnvelopeError,
    canonical_json,
    envelope_digest,
    is_envelope,
    to_envelope,
)


def _noop_data():
    return {"views": {"test_semua": {"n": 340518, "mape_pct": 8.59}},
            "konteks": {"catatan": "medAPE 1.58% pada strata dialisis"}}


# ------------------------------------------------------- happy path
def test_to_envelope_basic_shape():
    env = to_envelope("model_biaya_kandidat_C", "data riil BPJS sampel 2025", _noop_data())
    assert env["env_version"] == ENV_VERSION == 1
    assert env["divisi"] == "model_biaya_kandidat_C"
    assert env["catatan_domain"].startswith("data riil")
    assert env["views"]["test_semua"]["mape_pct"] == 8.59
    assert "satuan" not in env
    assert is_envelope(env)


def test_to_envelope_strips_and_with_unit_labels():
    env = to_envelope("divisi X ", " catatan " , {"alert_rate_persen": 3.0},
                      {"alert_rate_persen": "persen"})
    assert env["divisi"] == "divisi X"
    assert env["satuan"] == {"alert_rate_persen": "persen"}


def test_to_envelope_is_json_roundtrip_deterministic():
    env = to_envelope("d", "c", _noop_data())
    again = to_envelope("d", "c", _noop_data())
    assert canonical_json(env) == canonical_json(again)
    assert envelope_digest(env) == envelope_digest(again)


def test_is_envelope_rejects_plain_dict():
    assert not is_envelope({"divisi": "x"})


# ------------------------------------------------------- kontrak: angka = angka
def test_rejects_numeric_string_value():
    with pytest.raises(EnvelopeError, match="angka menyamar string"):
        to_envelope("d", "c", {"mape_pct": "8.59"})


def test_rejects_numeric_string_nested():
    with pytest.raises(EnvelopeError, match="angka menyamar string"):
        to_envelope("d", "c", {"a": {"b": ["7", 1.5]}})


def test_rejects_thousands_string_value():
    with pytest.raises(EnvelopeError):
        to_envelope("d", "c", {"n": "1.340.872"})


def test_allows_narrative_string_containing_numbers():
    env = to_envelope("d", "c", {"konteks": "error rupiah kecil (medAPE 1.58%)"})
    assert "konteks" in env


# ------------------------------------------------------- kontrak: 0 PII
@pytest.mark.parametrize("key", ["pstv01", "PSTV01", "no_pstv01_lama", "fkl02",
                                 "fkl47", "NIK", "nama_pasien", "tanggal_lahir",
                                 "no_kartu"])
def test_rejects_pii_keys(key):
    with pytest.raises(EnvelopeError, match="deteksi PII"):
        to_envelope("d", "c", {key: "nilai"})


def test_rejects_pii_key_nested():
    with pytest.raises(EnvelopeError):
        to_envelope("d", "c", {"agregat": {"per_peserta": {"pstv01": 1}}})


def test_rejects_underscore_private_keys():
    with pytest.raises(EnvelopeError, match="privat"):
        to_envelope("d", "c", {"_internal": 1})


# ------------------------------------------------------- validasi argumen
def test_rejects_empty_divisi_and_catatan():
    with pytest.raises(EnvelopeError):
        to_envelope("", "c", {})
    with pytest.raises(EnvelopeError):
        to_envelope("   ", "c", {})
    with pytest.raises(EnvelopeError):
        to_envelope("d", "", {})
    with pytest.raises(EnvelopeError):
        to_envelope("d", "    ", {})


def test_rejects_non_dict_data():
    with pytest.raises(EnvelopeError, match="data wajib dict"):
        to_envelope("d", "c", [1, 2, 3])
    with pytest.raises(EnvelopeError):
        to_envelope("d", "c", None)


def test_rejects_unit_labels_for_missing_keys():
    with pytest.raises(EnvelopeError, match="unit_labels"):
        to_envelope("d", "c", {"a": 1}, {"tidak_ada_pct": "persen"})


def test_rejects_non_serializable_data():
    with pytest.raises(EnvelopeError, match="serialisasi"):
        to_envelope("d", "c", {"obj": object()})


# ------------------------------------------------------- digest
def test_digest_changes_when_content_changes():
    env = to_envelope("d", "c", {"n": 1})
    env2 = to_envelope("d", "c", {"n": 2})
    assert envelope_digest(env) != envelope_digest(env2)
    assert len(envelope_digest(env)) == 64


def test_bool_flags_allowed_not_treated_as_number():
    env = to_envelope("d", "c", {"exact_duplicate": False})
    assert env["exact_duplicate"] is False


def test_envelope_json_dumps_is_ascii_safe_indonesia():
    env = to_envelope("divisi üñí", "catatan — emdash", {"n": 1})
    assert json.loads(json.dumps(env, ensure_ascii=False))["divisi"] == "divisi üñí"
