# -*- coding: utf-8 -*-
"""Benchmark per-slot peran LLM (F3, spec 2026-10-28-flow-maximization-design.md) — OFFLINE ONLY.

Perluasan pola llm_bench.py: diukur BUKAN cuma peran Pelapor, tapi slot per peran dari .env
(REVIEW_MODEL/EXPLANATION_MODEL + fallback) VS kandidat deepseek-r1:7b. Keputusan formal slot
tetap pasca-gate A3; run ini = baseline pengukuran saja (gitignored, tak mengubah runtime).

Peran v1 (kejujuran anti-fabrikasi):
- review_sintesis — envelope 3 divisi (aturan/biaya_C/klasifier_v3) -> tingkat bukti + narasi.
- explanation     — envelope biaya_C -> narasi penjelasan + rekomendasi tindakan.
- (lapis2_klinis ditunda: fixture klinis belum ada sampai payload A1 — tidak diinventasi.)

Pemanggilan: POST /api/chat, stream:false, format json, temp 0.2/top_p 0.8/num_ctx 8192/seed 42.
Checker angka via backend.app.core.llm_guard (pustaka murni; script offline, bukan runtime).
Output: backend/app/data/analysis/role_bench_results.json (inkremental).

Pemakaian: venv/Scripts/python.exe scripts/agent/role_bench.py   (Ollama di localhost:11434)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backend.app.core.llm_guard import check_numbers  # noqa: E402

AN = REPO / "backend" / "app" / "data" / "analysis"
OUT = AN / "role_bench_results.json"
OLLAMA = "http://localhost:11434"
CANDIDATE = "deepseek-r1:7b"
ENV_FILE = REPO / ".env"

ROLE_SYSTEM = {
    "review_sintesis": (
        "Kamu adalah Review Agent sistem AEGIS-Health: menyintesis bukti lintas divisi "
        "dari JSON envelope. ATURAN MUTLAK: (1) angka HANYA dari JSON — dilarang menghitung/"
        "mengubah/menambah angka; (2) tentukan tingkat_bukti persis salah satu: "
        "CRITICAL|STRONG|MODERATE|WEAK; (3) sebut divisi rujukan; (4) Bahasa Indonesia."
    ),
    "explanation": (
        "Kamu adalah Explanation Agent sistem AEGIS-Health: menyusun narasi penjelasan "
        "Bahasa Indonesia dari JSON envelope. ATURAN MUTLAK: (1) angka HANYA dari JSON — "
        "dilarang menghitung/mengubah/menambah angka; (2) sarankan satu rekomendasi tindakan "
        "verifikasi; (3) sebut divisi sumber; (4) maksimal 120 kata."
    ),
}

REVIEW_SCHEMA = ('{"tingkat_bukti": str, "narasi": str, "rujukan_divisi": [str], '
                 '"sinyal_utama": [{"divisi": str, "fakta": str}]}')
EXPL_SCHEMA = '{"narasi": str, "rekomendasi_tindakan": str, "divisi_sumber": [str]}'


def env_models() -> list[str]:
    """Parse slot .env live (REVIEW/EXPLANATION/FALLBACK); tam bahan kandidat r1."""
    slots: list[str] = []
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            for key in ("REVIEW_MODEL=", "EXPLANATION_MODEL=",
                        "REVIEW_MODEL_FALLBACK=", "EXPLANATION_MODEL_FALLBACK="):
                if line.startswith(key):
                    val = line.split("=", 1)[1].strip()
                    if val and val not in slots:
                        slots.append(val)
    if not slots:
        slots = ["mistral:7b"]  # default template .env.example
    if CANDIDATE not in slots:
        slots.append(CANDIDATE)
    return slots


def build_fixtures() -> dict[str, dict]:
    cad = json.loads((AN / "cadence_signal_scan.json").read_text(encoding="utf-8"))
    peer = json.loads((AN / "peer_signal_scan.json").read_text(encoding="utf-8"))
    cost = json.loads((AN / "eval_cost_c_parity.json").read_text(encoding="utf-8"))
    rep = json.loads((REPO / "backend" / "models_trained" / "synthetic_v2_v3"
                      / "synthetic_v2_training_report.json").read_text(encoding="utf-8"))
    cc = rep["classifier_candidate_not_runtime"]
    m = cc["test_metrics"]
    op = m["operating_point"]
    tp = int(op.get("true_positive", op.get("tp", 0)))
    fp = int(op.get("false_positive", op.get("fp", 0)))
    fn = int(op.get("false_negative", op.get("fn", 0)))
    tn = int(op.get("true_negative", op.get("tn", 0)))

    rule = {"divisi": "pillar_aturan",
            "catatan_domain": "scan kalibrasi pilar relasional — BUKAN indikasi fraud",
            "cadence_scan": cad, "peer_scan": peer}
    cost_env = {"divisi": "model_biaya_kandidat_C",
                "catatan_domain": "data riil BPJS sampel 2025; parity penuh vs retrain_results.json",
                "views": cost["views"]}
    clf = {"divisi": "model_anomali_kandidat_v3",
           "catatan_domain": "seluruh klaim & label SINTETIS — bukan validasi BPJS",
           "ambang_operasi": {"threshold": round(float(op["threshold"]), 4),
                              "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                              "alert_rate_persen": round(float(op.get("alert_rate", 0)) * 100, 3)},
           "headline": {"average_precision": round(m["average_precision"], 4),
                        "n_test": 50000}}
    return {"review_sintesis": {"bahan": [rule, cost_env, clf], "schema": REVIEW_SCHEMA},
            "explanation": {"bahan": [cost_env], "schema": EXPL_SCHEMA}}


def call(model: str, messages: list, timeout: int = 900) -> tuple[str, dict]:
    payload = {"model": model, "messages": messages, "stream": False, "format": "json",
               "options": {"temperature": 0.2, "top_p": 0.8, "num_ctx": 8192, "seed": 42}}
    req = urllib.request.Request(OLLAMA + "/api/chat",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    dt = time.perf_counter() - t0
    content = data.get("message", {}).get("content", "")
    meta = {"latency_s": round(dt, 1),
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "eval_tokens": data.get("eval_count", 0)}
    return content.strip(), meta


def ollama_alive() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5) as r:
            json.loads(r.read().decode("utf-8"))
        return True
    except Exception:
        return False


def main() -> None:
    if not ollama_alive():
        print("Ollama tidak terjangkau — baseline dilewati (script tetap tersaji).")
        return
    fixtures = build_fixtures()
    models = env_models()
    results: dict = {"catatan": "baseline F3 — keputusan slot formal pasca-gate A3",
                     "models": {}, "fixtures_meta":
                         {k: len(json.dumps(v)) for k, v in fixtures.items()}}
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    for model in models:
        content, meta = call(model, [{"role": "user", "content": "Balas persis: siap."}])
        print(f"[warmup] {model}: {content[:20]!r} {meta['latency_s']}s")
        for role, fx in fixtures.items():
            bahan = json.dumps(fx["bahan"], ensure_ascii=False)
            user = (f"Envelope JSON:\n{bahan}\n\nBalas HANYA JSON skema: {fx['schema']} — "
                    f"mengikuti aturan system.")
            try:
                content, meta = call(model, [{"role": "system", "content": ROLE_SYSTEM[role]},
                                             {"role": "user", "content": user}])
                try:
                    parsed = json.loads(content)
                    json_valid = isinstance(parsed, dict)
                    src = json.dumps(fx["bahan"])
                    viol = check_numbers(json.dumps(parsed, ensure_ascii=False), src)
                except Exception:
                    parsed, json_valid, viol = None, False, []
                    viol = check_numbers(content, json.dumps(fx["bahan"]))
                rec = {"meta": meta, "json_valid": json_valid,
                       "angka_violasi": viol, "n_violasi": len(viol), "chars": len(content)}
                print(f"[ok] {model} / {role}: json={json_valid} viol={len(viol)} "
                      f"{meta['latency_s']}s {meta['eval_tokens']}tok")
            except Exception as e:  # noqa: BLE001
                rec = {"error": repr(e)}
                print(f"[err] {model} / {role}: {e!r}")
            results["models"].setdefault(model, {})[role] = rec
            OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"selesai -> {OUT}")


if __name__ == "__main__":
    main()
