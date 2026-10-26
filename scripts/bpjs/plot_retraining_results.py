"""Visual final hasil retraining benchmark biaya pada data riil BPJS.

Membaca backend/app/data/analysis/retrain_results.json (ter-ignasi) dan menulis
satu angka sesuai kebijakan single-visual: docs/figures/bpjs_real_benchmark_eval.png.

Panel:
 1. MAPE per varian (skala log)          3. R^2 per varian (garis nol)
 2. MAE per varian (skala log, Rp)       4. medAPE per stratum (B vs C)
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RES = Path(r"C:\Users\Radith\E-Jak\backend\app\data\analysis\retrain_results.json")
OUT = Path(r"C:\Users\Radith\E-Jak\docs\figures\bpjs_real_benchmark_eval.png")

VARIANTS = [
    ("A_runtime_legacy", "A: runtime legacy\n(pelatihan sintetis)", "#d62728"),
    ("B_legacy_real", "B: kontrak legacy\n(retrain riil)", "#ff7f0e"),
    ("C_v2_real", "C: kontrak v2 + konteks\n(retrain riil)", "#2ca02c"),
]

res = json.loads(RES.read_text(encoding="utf-8"))
m = {key: res[key] for key, _, _ in VARIANTS}


def idn(x: float, digits: int = 2) -> str:
    return f"{x:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.6), dpi=200)
fig.suptitle("Benchmark biaya pada data riil BPJS — FKRTL Reguler, subset diterima penuh (FKL47 = FKL48)",
             fontsize=13, fontweight="bold")

# --- P1: MAPE (log) ---
ax = axes[0][0]
vals = [m[k]["test_semua"]["mape_pct"] for k, _, _ in VARIANTS]
ax.bar([label for _, label, _ in VARIANTS], vals, color=[c for _, _, c in VARIANTS])
ax.set_yscale("log")
ax.set_ylabel("MAPE (%) — skala log")
ax.set_title("1) MAPE test 340.518 klaim (split subjek)", fontsize=10)
for i, v in enumerate(vals):
    ax.text(i, v * 1.15, f"{idn(v)}%", ha="center", fontsize=9, fontweight="bold")
ax.set_ylim(1, max(vals) * 6)

# --- P2: MAE (log) ---
ax = axes[0][1]
vals = [m[k]["test_semua"]["mae_rp"] for k, _, _ in VARIANTS]
ax.bar([label for _, label, _ in VARIANTS], vals, color=[c for _, _, c in VARIANTS])
ax.set_yscale("log")
ax.set_ylabel("MAE (Rp) — skala log")
ax.set_title("2) MAE nilai absolut", fontsize=10)
for i, v in enumerate(vals):
    label = f"Rp {v / 1e6:.2f} jt".replace(".", ",") if v >= 1e6 else f"Rp {v / 1e3:,.0f} rb"
    ax.text(i, v * 1.15, label, ha="center", fontsize=9, fontweight="bold")
ax.set_ylim(5e4, max(vals) * 6)

# --- P3: R2 ---
ax = axes[1][0]
vals = [m[k]["test_semua"]["r2"] for k, _, _ in VARIANTS]
ax.bar([label for _, label, _ in VARIANTS], vals, color=[c for _, _, c in VARIANTS])
ax.axhline(0, color="black", linewidth=1)
ax.set_ylabel("R²")
ax.set_title("3) R² (negatif = lebih buruk daripada rata-rata)", fontsize=10)
for i, v in enumerate(vals):
    ax.text(i, v + (0.03 if v >= 0 else -0.06), idn(v, 3), ha="center", fontsize=9, fontweight="bold")
ax.set_ylim(-1.0, 1.0)

# --- P4: medAPE per stratum (B vs C) ---
ax = axes[1][1]
strata = ["Hemodialisis\n(Q-5-44-0)", "Non-dialisis"]
b_vals = [m["B_legacy_real"]["test_dialisis"]["medape_pct"],
          m["B_legacy_real"]["test_non_dialisis"]["medape_pct"]]
c_vals = [m["C_v2_real"]["test_dialisis"]["medape_pct"],
          m["C_v2_real"]["test_non_dialisis"]["medape_pct"]]
xpos = [0, 1]
width = 0.36
ax.bar([p - width / 2 for p in xpos], b_vals, width, label="B: kontrak legacy", color="#ff7f0e")
ax.bar([p + width / 2 for p in xpos], c_vals, width, label="C: kontrak v2 + konteks", color="#2ca02c")
ax.set_xticks(xpos, strata)
ax.set_ylabel("medAPE (%)")
ax.set_title("4) medAPE per stratum — presisi tinggi di sel terkunci tarif", fontsize=10)
for i, v in enumerate(b_vals):
    ax.text(i - width / 2, v + 1.2, f"{idn(v)}%", ha="center", fontsize=9)
for i, v in enumerate(c_vals):
    ax.text(i + width / 2, v + 1.2, f"{idn(v)}%", ha="center", fontsize=9)
ax.set_ylim(0, max(b_vals) * 1.25)
ax.legend(fontsize=9)

foot = ("Split subjek: crc32(PSTV01) % 10 — pasien tak lintas train→test • ground truth = FKL48 verifikasi BPJS • "
        "ICU/ventilator/obat = konstanta 0 (gap terdeklarasi)\n"
        f"Stabilitas waktu: test terbaru (≥ 2024-11-06) C MAPE {idn(m['C_v2_real']['test_terbaru']['mape_pct'])}% — "
        "tanpa drift • promosi runtime hanya via gate A3 pasca-1-Nov")
fig.text(0.5, 0.005, foot, ha="center", fontsize=8, color="#555555", wrap=True)
fig.tight_layout(rect=(0, 0.055, 1, 0.96))
OUT.parent.mkdir(exist_ok=True)
fig.savefig(OUT, bbox_inches="tight")
print(f"[ok] saved -> {OUT}")
