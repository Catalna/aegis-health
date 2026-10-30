"""Delapan figur evaluasi model biaya kandidat C (v2+context) — satu model, tanpa pembanding.

Sumber: `backend/app/data/analysis/eval_cost_c_test.parquet` (test 340.518 klaim,
tanpa PII, dihasilkan `scripts/bpjs/eval_cost_candidate_c.py` dengan parity check
terhadap `retrain_results.json`) + `retrain_results.json` (metrik view & gain top10).

Output `docs/figures/` (prefix cost_c_):
  1) cost_c_pred_vs_actual.png   — heksbin prediksi vs aktual (skala log)
  2) cost_c_ape_distribution.png — distribusi APE + kuantil p50/p90/p99
  3) cost_c_coverage_curve.png   — % klaim dalam ±x% (x = 1..50%)
  4) cost_c_stratum_metrics.png  — MAPE per view (semua/terbaru/dialisis/non)
  5) cost_c_ape_by_stratum.png   — kuantil APE per view (p25–p95)
  6) cost_c_ape_by_inacbg.png    — medAPE 8 grup INACBG terbesar
  7) cost_c_feature_importance.png — gain top 10
  8) cost_c_bias_by_decile.png   — medAPE per desil biaya aktual

Pemakaian: venv\\Scripts\\python.exe scripts\\plot_cost_c_report.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
PARQUET = REPO / "backend" / "app" / "data" / "analysis" / "eval_cost_c_test.parquet"
RESULTS = REPO / "backend" / "app" / "data" / "analysis" / "retrain_results.json"
OUT_DIR = REPO / "docs" / "figures"

INK, MUTED, GRID, PAPER = "#18252F", "#62717A", "#DEE5E7", "#F7F8F5"
TEAL, GOLD, GRAY, RED = "#087E83", "#D18A35", "#9AA7AA", "#B85B4B"
FIG_KW = dict(figsize=(9.6, 6.8), dpi=160)
MODEL_TAG = "Model 1 · Biaya (kandidat C) — "

VIEW_LABELS = {"test_semua": "Test semua", "test_terbaru": "Test terbaru",
               "test_dialisis": "Hemodialisis", "test_non_dialisis": "Non-dialisis"}


def _ax(title: str, ylabel: str = ""):
    fig, ax = plt.subplots(**FIG_KW)
    ax.set_facecolor(PAPER)
    fig.suptitle(f"{MODEL_TAG}{title}", x=0.02, ha="left", color=INK,
                 fontsize=13.5, fontweight="bold")
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED, fontsize=10)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    return fig, ax


def _img(fig, name: str, note: str = "") -> None:
    if note:
        fig.text(0.08, 0.02, note, color=MUTED, fontsize=8, va="bottom")
    fig.tight_layout(rect=(0.04, 0.055 if note else 0.03, 0.98, 0.97))
    fig.savefig(OUT_DIR / name, facecolor=PAPER)
    plt.close(fig)
    print(f"[ok] {name}")


def main() -> None:
    df = pd.read_parquet(PARQUET)
    results = json.loads(RESULTS.read_text(encoding="utf-8"))["C_v2_real"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    a = df["actual"].to_numpy("float64")
    p = df["pred"].to_numpy("float64")
    ape = np.abs(p - a) / a
    n_total = len(df)
    print(f"test n={n_total:,}; medAPE {np.median(ape) * 100:.2f}%")

    # 1) Prediksi vs aktual (scatter sub-sampel, log-log)
    fig, ax = _ax("Prediksi vs Aktual (test riil BPJS)",
                  "aktual Rp (log)")
    lim = (1e5, max(a.max(), p.max()) * 1.5)
    rng = np.random.default_rng(42)
    sample = rng.choice(n_total, size=min(80_000, n_total), replace=False)
    ax.scatter(a[sample], p[sample], s=3, color=TEAL, alpha=0.15, linewidths=0)
    ax.plot(lim, lim, "--", color=RED, lw=1.4, label="identitas")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("Aktual Rp (FKL48)", color=MUTED, fontsize=10)
    ax.grid(color=GRID, linewidth=0.8)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _img(fig, "cost_c_pred_vs_actual.png",
         "80,000 dari 340,518 test claims (seed 42) · subject split · band dialysis rapat di garis identitas")

    # 2) Distribusi APE
    fig, ax = _ax("Distribusi APE (test)", "klaim")
    clip = np.clip(ape, 0, 1.5)
    ax.hist(clip, bins=60, color=TEAL, edgecolor=PAPER, linewidth=0.3)
    for q, c in ((0.5, INK), (0.9, GOLD), (0.99, RED)):
        val = float(np.quantile(ape, q))
        ax.axvline(min(val, 1.5), color=c, lw=1.5, ls=(0, (4, 2)))
        ax.text(min(val, 1.5) + 0.015, ax.get_ylim()[1] * 0.90, f"p{int(q * 100)} {val:.1%}",
                color=c, fontsize=8.5, fontweight="bold")
    ax.set_xlabel("APE = |pred − aktual| / aktual", color=MUTED, fontsize=10)
    _img(fig, "cost_c_ape_distribution.png",
         "APE > 150% diklip untuk kejelasan · MAPE 8.59% ditarik oleh ekor kanan")

    # 3) Coverage curve
    xs = np.arange(1, 51)
    cov = np.asarray([(ape <= x / 100).mean() * 100 for x in xs])
    fig, ax = _ax("Klaim dalam banding error ±x% (coverage)", "klaim (%)")
    ax.plot(xs, cov, color=TEAL, lw=2.2)
    for x_validate, c in ((5, GOLD), (10, RED)):
        v = float(cov[x_validate - 1])
        ax.scatter([x_validate], [v], color=c, zorder=4, s=34)
        ax.annotate(f"±{x_validate}%: {v:.1f}%", (x_validate, v), xytext=(8, -2),
                    textcoords="offset points", fontsize=8.5, color=INK, fontweight="bold")
    ax.set_xlabel("banding error diperbolehkan x (%)", color=MUTED, fontsize=10)
    ax.set_xlim(1, 50)
    ax.set_ylim(0, 100)
    _img(fig, "cost_c_coverage_curve.png",
         "within ±5% 63.6% · within ±10% 80.1% · subject-split test")

    # 4) MAPE per view (metrik satu model, view bukan pembanding model)
    views = ("test_semua", "test_terbaru", "test_dialisis", "test_non_dialisis")
    vals = [results[v]["mape_pct"] for v in views]
    fig, ax = _ax("Performa per stratum & periode", "MAPE (%)")
    colors = [TEAL, GOLD, GRAY, GRAY]
    bars = ax.bar(range(4), vals, color=colors, width=0.6)
    for i, (bar, v, key) in enumerate(zip(bars, vals, views)):
        m = results[key]
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.12,
                f"{v:.2f}%\nmedAPE {m['medape_pct']:.2f}% · R² {m['r2']:.3f}\nn {m['n']:,}",
                ha="center", color=INK, fontsize=8, fontweight="bold")
    ax.set_xticks(range(4), [VIEW_LABELS[v] for v in views], fontsize=9)
    ax.set_ylim(0, max(vals) * 1.45)
    _img(fig, "cost_c_stratum_metrics.png",
         "R² dialysis rendah karena tarif terkunci-hampir-konstan (varians aktual kecil) — MAPE tetap 8.17%")

    # 5) Kuantil APE per view
    fig, ax = _ax("Sebaran APE per stratum", "APE (%)")
    stats_p, positions = [], []
    for i, key in enumerate(("test_dialisis", "test_non_dialisis", "test_terbaru")):
        if key == "test_dialisis":
            m = df["dialysis"].to_numpy()
        elif key == "test_non_dialisis":
            m = ~df["dialysis"].to_numpy()
        else:
            m = df["terbaru"].to_numpy()
        sub = ape[m.to_numpy() if hasattr(m, "to_numpy") else m]
        q25, q50, q75, q95 = np.quantile(sub, (0.25, 0.5, 0.75, 0.95)) * 100
        stats_p.append((q25, q50, q75, q95))
        positions.append(i)
    for pos, (q25, q50, q75, q95) in zip(positions, stats_p):
        ax.vlines(pos, q25, q95, color=TEAL, lw=6, alpha=0.35)
        ax.vlines(pos, q25, q75, color=TEAL, lw=6, alpha=0.65)
        ax.scatter([pos], [q50], color=INK, s=42, zorder=5)
        ax.text(pos + 0.06, q50, f"p50 {q50:.2f}%", va="center", fontsize=8.5, color=INK, fontweight="bold")
        ax.text(pos + 0.06, q95, f"p95 {q95:.2f}%", va="center", fontsize=8, color=MUTED)
    ax.set_xticks(positions, ["Hemodialisis", "Non-dialisis", "Test terbaru"], fontsize=9)
    ax.set_ylim(0, max(s[3] for s in stats_p) * 1.2)
    _img(fig, "cost_c_ape_by_stratum.png", "bar: p25–p95 · titik: median · APE dalam persen")

    # 6) medAPE per grup INACBG terbesar
    grp = (df.assign(ape_pct=ape * 100).groupby("inacbg")
             .agg(n=("ape_pct", "size"), med=("ape_pct", "median"))
             .sort_values("n", ascending=False).head(8))
    fig, ax = _ax("medAPE 8 grup INACBG terbesar", "medAPE (%)")
    bars = ax.barh(range(len(grp)), grp["med"], color=TEAL, height=0.62)
    ax.set_yticks(range(len(grp)), list(grp.index), fontsize=8.5)
    ax.invert_yaxis()
    for bar, (code, row) in zip(bars, grp.iterrows()):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                f"{row['med']:.2f}% · n {int(row['n']):,}", va="center", fontsize=8, color=INK, fontweight="bold")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, grp["med"].max() * 1.35)
    _img(fig, "cost_c_ape_by_inacbg.png",
         "subset wajar (tarif verifikasi = tagih) · Q-5-44-0 = hemodialisis kronik")

    # 7) Feature importance — gain top 10 dari report retrain (share dari top-10)
    gains = results["feature_gain_top10"]
    names_x = list(gains)
    raw = np.asarray([gains[k] for k in names_x], dtype=float)
    share = raw / raw.sum()
    fig, ax = _ax("Feature importance (gain share, top 10)")
    bars = ax.barh(names_x, share, color=GOLD, height=0.62)
    ax.set_xlabel("porsi total gain 10 teratas", color=MUTED, fontsize=10)
    for bar, v in zip(bars, share):
        ax.text(bar.get_width() + share.max() * 0.015, bar.get_y() + bar.get_height() / 2,
                f"{v:.1%}", va="center", fontsize=8.5, color=INK, fontweight="bold")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.invert_yaxis()
    ax.set_xlim(0, share.max() * 1.18)
    _img(fig, "cost_c_feature_importance.png",
         "15 fitur kontrak v2 · base_rate (median train-only per INACBG×sev) & severity/LOS dominan")

    # 8) Bias per desil biaya aktual
    dec = pd.qcut(a, 10, labels=False, duplicates="drop")
    dec_med = pd.Series(ape * 100).groupby(dec).median()
    x_line = pd.Series(a).groupby(dec).median()
    fig, ax = _ax("Bias per desil biaya aktual", "medAPE (%)")
    ax.bar(range(len(dec_med)), dec_med.values, color=TEAL, width=0.7)
    ax.set_xticks(range(len(dec_med)),
                  [f"{v / 1e6:.1f} jt" for v in x_line], fontsize=8)
    ax.set_xlabel("median biaya aktual per desil", color=MUTED, fontsize=10)
    for i, v in enumerate(dec_med.values):
        ax.text(i, v + 0.15, f"{v:.1f}%", ha="center", fontsize=8, color=INK, fontweight="bold")
    ax.set_ylim(0, dec_med.max() * 1.25)
    _img(fig, "cost_c_bias_by_decile.png",
         "klaim mahal: APE acap % kecil tapi Rupiah besar; klaim murah sebaliknya — baca MAPE + MAE bersama")

    print("selesai: 8 PNG cost_c_* di docs/figures")


if __name__ == "__main__":
    main()
