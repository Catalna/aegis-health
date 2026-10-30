"""Kontrak envelope divisi (F1 spec 2026-10-28-flow-maximization-design.md) — pustaka murni.

Status: BELUM di-import oleh runtime mana pun (freeze demo 1-Nov). Pemakaian
pasca-integrasi: proyeksi keluaran clinical/financial/fraud ke JSON divisi yang
dialidasi — sumber angka tunggal bagi Review/Explanation/QA/Pelapor dan checker
anti-halusinasi (`core.llm_guard`).

Aturan kontrak (diwarisi design induk §2):
- `"angka harus angka"`: nilai numerik tidak boleh menyamar sebagai string ("8.59" ditolak).
- Kunci berlabel satuan (`*_pct`, `*_rupiah`) — hanya dipetakan, tidak dipaksa di sini.
- `catatan_domain` wajib.
- Nol PII: kunci yang kerap membawa identitas peserta ditolak (PSTV01, FKL02/47/48, NIK, dst.).
- Idempoten: regenerasi dari data yang sama menghasilkan digest identik.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ENV_VERSION = 1

#: Token kunci yang dilarang muncul (substring, case-insensitive) di kunci manapun,
#: dalam tingkat kedalaman apapun. Ini kunci identitas peserta/klaim rawan PII.
PII_KEY_TOKENS: tuple[str, ...] = (
    "pstv01", "fk102", "fk147", "fk148", "fk103", "fkl02", "fkl47", "fkl48",
    "nik", "nama_", "dob", "tanggal_lahir", "tgl_lahir", "no_kartu",
    "no_peserta", "no_telepon", "alamat", "email", "segmen",
)


class EnvelopeError(ValueError):
    """Kontrak envelope dilanggar — gagal keras, jangan diam-diam didegradasi."""


_NUM_AS_STR_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _fail(msg: str) -> None:
    raise EnvelopeError(msg)


def _assert_no_pii_keys(obj: Any, path: str = "") -> None:
    """Larang kunci berbau PII di kedalaman manapun (substring, case-insensitive)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                _fail(f"kunci non-string pada '{path}': {k!r}")
            low = k.lower()
            for tok in PII_KEY_TOKENS:
                if tok in low:
                    _fail(f"kunci terdeteksi PII pada '{path}': '{k}' (pola '{tok}')")
            if k.startswith("_"):
                _fail(f"kunci privat '_' tidak boleh pada '{path}': '{k}'")
            nxt = f"{path}.{k}" if path else k
            _assert_no_pii_keys(v, nxt)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_no_pii_keys(v, f"{path}[{i}]")


def _assert_numbers_are_numbers(obj: Any, path: str = "") -> None:
    """Larang angka menyamar sebagai string murni (mis. "8.59", "1.340.872").

    String yang memuat angka tapi bukan angka penuh ("medAPE 1.58%") diizinkan —
    itulah catatan_domain/konteks naratif.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            nxt = f"{path}.{k}" if path else k
            if isinstance(v, str) and _NUM_AS_STR_RE.fullmatch(v.strip()):
                _fail(f"angka menyamar string pada '{nxt}': {v!r} — pakai tipe numerik")
            _assert_numbers_are_numbers(v, nxt)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str) and _NUM_AS_STR_RE.fullmatch(v.strip()):
                _fail(f"angka menyamar string pada '{path}[{i}]': {v!r}")
            _assert_numbers_are_numbers(v, f"{path}[{i}]")


def to_envelope(
    divisi: str,
    catatan_domain: str,
    data: dict[str, Any],
    unit_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Bungkus temuan divisi menjadi envelope JSON tervalidasi.

    - `divisi`/`catatan_domain` wajib string non-kosong.
    - `data` wajib dict; dibulldog-jlip JSON agar serialisasi & nilai deterministik.
    - `unit_labels` opsional: peta kunci→satuan, disimpan di `"satuan"`;
      setiap kunci yang dinisbatkan wajib ada di `data`.
    - Melanggar kontrak → `EnvelopeError` (fail-fast).
    """
    if not isinstance(divisi, str) or not divisi.strip():
        _fail("divisi wajib string non-kosong")
    if not isinstance(catatan_domain, str) or not catatan_domain.strip():
        _fail("catatan_domain wajib string non-kosong")
    if not isinstance(data, dict):
        _fail(f"data wajib dict, dapat {type(data).__name__}")
    if unit_labels is not None:
        if not isinstance(unit_labels, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in unit_labels.items()
        ):
            _fail("unit_labels wajib dict[str, str]")
        hilang = sorted(k for k in unit_labels if k not in data)
        if hilang:
            _fail(f"unit_labels untuk kunci yang tidak ada di data: {hilang}")

    # Round-trip JSON: menjamin serializable & menyalin ke struktur umum (fail-fast tanpa default=str).
    try:
        payload = json.loads(json.dumps(data, ensure_ascii=False))
    except (TypeError, ValueError) as e:  # noqa: PERF203
        _fail(f"data tidak serialisasi JSON: {e!r}")

    _assert_no_pii_keys({"divisi": divisi, "catatan_domain": catatan_domain, **payload})
    _assert_numbers_are_numbers(payload)

    env: dict[str, Any] = {"env_version": ENV_VERSION, "divisi": divisi.strip(),
                           "catatan_domain": catatan_domain.strip()}
    env.update(payload)
    if unit_labels:
        env["satuan"] = dict(unit_labels)
    return env


def is_envelope(obj: Any) -> bool:
    """Pemeriksaan lapisan ringan bentuk envelope (untuk guard pemanggil)."""
    return (isinstance(obj, dict) and obj.get("env_version") == ENV_VERSION
            and isinstance(obj.get("divisi"), str) and bool(obj.get("divisi"))
            and isinstance(obj.get("catatan_domain"), str))


def canonical_json(env: dict[str, Any]) -> str:
    """Bentuk kanonik (sort_keys, tanpa spasi) — dasar idempotensi."""
    return json.dumps(env, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def envelope_digest(env: dict[str, Any]) -> str:
    """Digest sha256 kanonik — identik bila regenerasi dari artefak yang sama."""
    if not isinstance(env, dict):
        _fail("envelope wajib dict")
    return hashlib.sha256(canonical_json(env).encode("utf-8")).hexdigest()
