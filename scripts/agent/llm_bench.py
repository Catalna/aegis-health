"""Benchmark A/B LLM Pelapor lokal (Ollama): qwen3.5:9b vs deepseek-r1:7b — OFFLINE ONLY.

Peran diuji: "LLM Pelapor" membaca envelope JSON divisi (pivot aturan / model biaya C /
klasifier v3) lalu menyusun ringkasan. Dua mode per fixture:
  report_text — ringkasan Bahasa Indonesia (maks 120 kata); dicek passthrough angka:
                setiap angka di keluaran HARUS ada di envelope sumber (anti-halusinasi).
  report_json — balasan wajib JSON skema tetap; dicek validitas parse + kunci wajib + passthrough.
Latensi & token dicatat dari metrik Ollama; pemanggilan pertama = warmup (tidak dinilai).
Hasil: backend/app/data/analysis/llm_bench_results.json (ter-ignasi), ditulis inkremental.

Pemakaian: venv\\Scripts\\python.exe scripts\\agent\\llm_bench.py   (Ollama di localhost:11434)
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AN = REPO / "backend" / "app" / "data" / "analysis"
OUT = AN / "llm_bench_results.json"
MODELS = ["qwen3.5:9b", "deepseek-r1:7b"]
OLLAMA = "http://localhost:11434"

SYSTEM = ("Kamu adalah 'LLM Pelapor' sistem J-ARI: menyusun laporan dari JSON divisi. "
          "ATURAN MUTLAK: (1) gunakan HANYA angka yang ada di JSON — dilarang menambah, "
          "mengubah, atau menghitung angka; (2) Bahasa Indonesia; (3) maksimal 120 kata; "
          "(4) sebut divisi sumber untuk tiap poin.")

NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


def harvest(obj, acc: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        acc.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            harvest(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            harvest(v, acc)
    elif isinstance(obj, str):
        for t in NUM_RE.findall(obj):
            harvest_candidates_str(t, acc)


def harvest_candidates_str(t: str, acc: list[float]) -> None:
    for c in candidates(t):
        acc.append(c)


def candidates(t: str) -> set[float]:
    out = set()
    for s in (t, t.replace(",", ""), t.replace(".", "").replace(",", "."), t.replace(",", ".")):
        try:
            out.add(float(s))
        except ValueError:
            pass
    return out


def violations(text: str, src: list[float]) -> list[str]:
    """Angka pada teks yang tak punya padanan (toleran) di envelope sumber."""
    bad = []
    for t in NUM_RE.findall(text):
        ok = any(
            any(abs(c - s) <= (0.06 if abs(s) < 10 else abs(s) * 0.005) for s in src)
            for c in candidates(t)
        )
        if not ok:
            bad.append(t)
    return bad


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
    clf = {
        "divisi": "model_anomali_kandidat_v3",
        "catatan_domain": "seluruh klaim & label SINTETIS — bukan validasi BPJS",
        "headline": {"average_precision": round(m["average_precision"], 4),
                     "roc_auc": round(m["roc_auc"], 4),
                     "ci95_ap": [0.635, 0.683], "ci95_ap_persen": [63.5, 68.3],
                     "n_test": 50000, "prevalensi": 0.03, "prevalensi_persen": 3.0,
                     "jumlah_tipe_anomali": 7},
        "ambang_operasi": {"threshold": round(float(op["threshold"]), 4),
                           "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                           "alerts": int(op.get("predicted_positive_n", tp + fp)),
                           "alert_rate_persen": round(float(op.get("alert_rate", 0)) * 100, 3),
                           "precision_persen": round(float(op.get("precision", 0)) * 100, 2),
                           "recall_persen": round(float(op.get("recall", 0)) * 100, 2)},
        "per_tipe": {t: {"ap": round(d["average_precision"], 4), "n_positif": d["positive_n"]}
                     for t, d in sorted(m["by_anomaly_type"].items())},
    }
    cost_env = {
        "divisi": "model_biaya_kandidat_C",
        "catatan_domain": "data riil BPJS sampel 2025; parity penuh vs retrain_results.json",
        "views": cost["views"],
        "konteks": {"r2_dialisis_rendah_karena": "tarif terkunci hampir-konstan; error rupiah justru kecil (medAPE 1.58%)"},
    }
    rule = {"divisi": "pillar_aturan",
            "catatan_domain": "scan kalibrasi pilar relasional — BUKAN indikasi fraud",
            "cadence_scan": cad, "peer_scan": peer}
    return {"aturan_cadence_peer": rule, "biaya_C": cost_env, "klasifier_v3": clf}


def call(model: str, messages: list, as_json: bool, timeout: int = 900) -> tuple[str, dict]:
    payload = {"model": model, "messages": messages, "stream": False,
               "options": {"temperature": 0.2, "top_p": 0.8, "num_ctx": 8192, "seed": 42}}
    if as_json:
        payload["format"] = "json"
    req = urllib.request.Request(OLLAMA + "/api/chat",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    dt = time.perf_counter() - t0
    msg = data.get("message", {})
    content = msg.get("content", "")
    if "<think>" in content:  # r1 versi lama menanam pikiran di content
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    meta = {"latency_s": round(dt, 1),
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "eval_tokens": data.get("eval_count", 0),
            "eval_s": round(data.get("eval_duration", 0) / 1e9, 1)}
    return content.strip(), meta


def main() -> None:
    fixtures = build_fixtures()
    results: dict = {"models": {}, "fixtures_meta": {k: len(json.dumps(v)) for k, v in fixtures.items()}}
    for model in MODELS:
        content, meta = call(model, [{"role": "user", "content": "Balas persis: siap."}], False)
        print(f"[warmup] {model}: {content[:20]!r} {meta['latency_s']}s")
        mres: dict[str, dict] = {}
        for fname, env in fixtures.items():
            src: list[float] = []
            harvest(env, src)
            envelope = json.dumps(env, ensure_ascii=False)
            user_text = f"Envelope JSON divisi:\n{envelope}\n\nTulis ringkasan manajerial Bahasa Indonesia (maks 120 kata) berdasar envelope ini."
            user_json = (f"Envelope JSON divisi:\n{envelope}\n\nBalas HANYA JSON skema: "
                         "{\"ringkasan\": str, \"temuan\": [{\"fakta\": str, \"angka\": number}], "
                         "\"risiko\": str, \"rekomendasi\": str} — Bahasa Indonesia.")
            entry: dict[str, dict] = {}
            for mode, (txt, u) in (("report_text", (False, user_text)), ("report_json", (True, user_json))):
                try:
                    content, meta = call(model, [{"role": "system", "content": SYSTEM},
                                                 {"role": "user", "content": u}], txt)
                    v = violations(content, src)
                    rec = {"meta": meta, "angka_violasi": v, "n_violasi": len(v), "chars": len(content)}
                    if txt:
                        try:
                            parsed = json.loads(content)
                            rec["json_valid"] = True
                            rec["kunci_lengkap"] = all(k in parsed for k in
                                                       ("ringkasan", "temuan", "risiko", "rekomendasi"))
                        except Exception:
                            rec["json_valid"] = False
                            rec["kunci_lengkap"] = False
                    entry[mode] = rec
                    print(f"[ok] {model} / {fname} / {mode}: viol {len(v)} "
                          f"json={rec.get('json_valid')} {meta['latency_s']}s {meta['eval_tokens']}tok")
                except Exception as e:  # noqa: BLE001
                    entry[mode] = {"error": repr(e)}
                    print(f"[err] {model} / {fname} / {mode}: {e!r}")
                results["models"].setdefault(model, {})[fname] = entry
                OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    # sampel untuk eyeball kualitas bahasa
    for model in MODELS:
        env = fixtures["biaya_C"]
        u = f"Envelope JSON divisi:\n{json.dumps(env, ensure_ascii=False)}\n\nTulis ringkasan manajerial Bahasa Indonesia (maks 120 kata) berdasar envelope ini."
        content, meta = call(model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": u}], False)
        results["models"].setdefault(model, {})["sampel_biaya_C_text"] = {
            "meta": meta, "isi": content}
        print(f"--- sampel {model} ---\n{content[:600]}\n")
        OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"selesai -> {OUT}")


if __name__ == "__main__":
    main()
