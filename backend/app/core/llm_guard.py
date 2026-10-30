# -*- coding: utf-8 -*-
"""Checker anti-halusinasi generik (F2, spec 2026-10-28-flow-maximization-design.md) — pustaka murni.

Status: BELUM terpasang pada runtime mana pun (freeze demo 1-Nov). Pasca-integrasi
membungkus semua permukaan LLM — Pelapor `strict`; Review/Explanation mode `numbers`;
QA Panel (deterministik murni) dikecualikan. Resep gagal: TOLAK output, jalan
deterministik (template) menggantikan — dilarang LLM "memperbaiki" keluaran sendiri.

Aturan angka (design induk §4): tiap angka pada teks LLM wajib punya padanan di envelope —
nilai mentah ATAU konversi satuan sah (×100 persen, ÷100, ×10⁶/÷10⁶ juta), toleransi
pembulatan dua-desimal (0,5% rel; 0,06 absolut untuk nilai <10).

Parsing angka Indonesia (heuristik deterministik, dipakai di teks report DAN teks envelope):
- "1.340.872" / "1,340,872" → 1340872 (grouping ribuan)
- "0,2142" → 0.2142; "21,4" → 21.4 (koma desimal)
- "8.59" → 8.59 (titik desimal)
- "1.340,87" → 1340.87; "1,340.87" → 1340.87 (pemisah TERAKHIR = desimal)
- "1.340" (satu pemisah, tepat 3 digit, bagian-utama bukan "0") → 1340 (konvensi ribuan)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
# Kata majemuk kapital di awal baris diikuti koma = pola sapaan (kasus benchmark: "Enyi,").
SALUTATION_RE = re.compile(r"(?:\A|\n)\s*([A-Za-zÀ-ÿ]+)\s*,")
# Kandidat proper noun: token kapital panjang ≥3 (kata-kata Indonesia kapital awal kalimat
# masuk whitelist builtin — v1; kalibrasi lanjut pada gelombang integrasi).
PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-ZÀ-ÿ]{2,}\b")

#: Whitelist v1 — kata pembuka/konektor Indonesia umum + kosakata domain sistem.
BUILTIN_WHITELIST: frozenset[str] = frozenset({
    "berikut", "berdasarkan", "secara", "dengan", "dalam", "dari", "adalah", "bahwa",
    "tidak", "untuk", "atas", "pada", "setelah", "sebelum", "ini", "itu", "juga",
    "ringkasan", "temuan", "risiko", "rekomendasi", "kesimpulan", "simulasi", "skenario",
    "divisi", "model", "klaim", "biaya", "anomali", "data", "kandidat", "ambang",
    "threshold", "presisi", "rasio", "kelompok", "harga", "rupiah", "persen", "juta",
    "total", "rata", "deviasi", "klasifikasi", "regresi", "analisis", "strata",
    "inacbg", "bpjs", "jkn", "aegis", "mape", "medape", "shap", "xgboost",
    "faskes", "pasien",
})

KONVERSI_SKALA: tuple[float, ...] = (1.0, 100.0, 0.01, 1_000_000.0, 1e-6)


class GuardError(ValueError):
    """Pemanggil memakau checker dengan bentuk argumen salah — fail-fast."""


def _parse_number_token(tok: str) -> Decimal | None:
    """Satu token → Decimal menurut heuristik §detik docstring; tak terurai → None."""
    t = tok.strip()
    try:
        dot, comma = t.count("."), t.count(",")
        if dot and comma:  # dua jenis pemisah: yang TERAKHIR = desimal
            dec = "." if t.rfind(".") > t.rfind(",") else ","
            grp = "," if dec == "." else "."
            int_part, frac = t.rsplit(dec, 1)
            return Decimal(f"{int_part.replace(grp, '')}.{frac or '0'}")
        if dot == 0 and comma == 0:
            return Decimal(t)
        sep = "." if dot else ","        # satu jenis pemisah (mungkin berulang)
        parts = t.split(sep)
        if all(len(p) == 3 for p in parts[1:]) and len(parts) >= 2 and parts[0] != "0":
            if dot + comma == 1 and len(parts[1]) == 3 and parts[0] == "0":
                # "0.347"/"0,347" → desimal (bagian-utama nol)
                return Decimal(t.replace(sep, "."))
            return Decimal(t.replace(sep, ""))          # grouping ribuan
        if dot + comma == 1:
            return Decimal(f"{parts[0]}.{parts[-1] or '0'}")  # desimal titik/koma
        # pemisah berulang tapi bukan pola ribuan murni: bersihkan pemisah selain terakhir
        last = t.rfind(sep)
        cleaned = t[:last].replace(sep, "") + "." + t[last + 1:].replace(sep, "")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def extract_numbers(text: str) -> list[tuple[str, Decimal]]:
    """Semua token angka pada teks → [(raw, nilai)]. Token tak-terurai dilewatkan."""
    out: list[tuple[str, Decimal]] = []
    for m in NUM_RE.finditer(text):
        val = _parse_number_token(m.group(0))
        if val is not None:
            out.append((m.group(0), val))
    return out


def harvest_numbers(obj) -> set[Decimal]:
    """Kumpulan nilai target dari envelope: angka asli + token di dalam teks."""
    targets: set[Decimal] = set()

    def walk(o) -> None:
        if isinstance(o, bool):
            return
        if isinstance(o, (int, float)):
            targets.add(Decimal(str(o)))
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            for _, val in extract_numbers(o):
                targets.add(val)

    walk(obj)
    return targets


def check_numbers(report_text: str, envelope, *, tol_rel: float = 0.005,
                  tol_abs: float = 0.06) -> list[dict]:
    """Angka report yang tak berpadanan (mentah/konversi/toleransi) → daftar pelanggaran."""
    targets = harvest_numbers(envelope)
    violations: list[dict] = []
    for raw, n in extract_numbers(report_text):
        nf = float(n)
        ok = False
        for t in targets:
            tf = float(t)
            for k in KONVERSI_SKALA:
                c = tf * k
                thr = tol_abs if abs(c) < 10 else max(tol_rel * abs(c), tol_abs)
                if abs(nf - c) <= thr:
                    ok = True
                    break
            if ok:
                break
        if not ok:
            violations.append({"token": raw, "nilai": nf})
    return violations


def check_names(report_text: str, envelope, *, strict: bool = False,
                extra_whitelist: "set[str] | None" = None) -> list[str]:
    """Guard nama fiktif. Default: hanya pola sapaan awal-baris ("Enyi,").

    `strict=True`: semua proper-noun kapital wajib terkandung envelope/whitelist —
    v1(calibratable), aktifkan untuk peran Pelapor pada gelombang integrasi.
    """
    vocab: set[str] = set(BUILTIN_WHITELIST)
    if extra_whitelist:
        vocab.update(w.lower() for w in extra_whitelist)

    def collect_strings(o) -> None:
        if isinstance(o, dict):
            for v in o.values():
                collect_strings(v)
                if isinstance(v, str):
                    vocab.update(w.lower() for w in PROPER_NOUN_RE.findall(v))
        elif isinstance(o, list):
            for v in o:
                collect_strings(v)
        elif isinstance(o, str):
            vocab.update(w.lower() for w in PROPER_NOUN_RE.findall(o))

    collect_strings(envelope)

    bad: list[str] = []
    m = SALUTATION_RE.search(report_text)
    if m and m.group(1).lower() not in vocab:
        bad.append(m.group(1))
    if strict:
        for tok in PROPER_NOUN_RE.findall(report_text):
            if tok.lower() not in vocab and tok not in bad:
                bad.append(tok)
    return bad


@dataclass(frozen=True)
class GuardResult:
    """Hasil checker: `ok=False` berarti output LLM DITOLAK, jalan deterministik yang menjawab."""

    mode: str
    n_angka_checked: int
    angka_violasi: list[dict] = field(default_factory=list)
    nama_violasi: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.angka_violasi and not self.nama_violasi


def guard_report(report_text: str, envelope, *, mode: str = "strict",
                 tol_rel: float = 0.005, tol_abs: float = 0.06,
                 extra_whitelist: "set[str] | None" = None) -> GuardResult:
    """Simpul satuan checker: mode `strict` (angka+sapaan+nama) atau `numbers` (angka saja)."""
    if mode not in ("strict", "numbers"):
        raise GuardError(f"mode tak dikenal: {mode!r} (khusus 'strict'|'numbers')")
    if not isinstance(report_text, str):
        raise GuardError("report_text wajib string")
    toks = extract_numbers(report_text)
    angka = check_numbers(report_text, envelope, tol_rel=tol_rel, tol_abs=tol_abs)
    nama = ([] if mode == "numbers"
            else check_names(report_text, envelope, strict=(mode == "strict"),
                             extra_whitelist=extra_whitelist))
    return GuardResult(mode=mode, n_angka_checked=len(toks),
                       angka_violasi=angka, nama_violasi=nama)
