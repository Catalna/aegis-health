"""Four offline diagnostic figures for the temporal BPJS cost candidate."""
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PLOT_FILENAMES = {
    'actual_vs_predicted': 'cost_temporal_actual_vs_predicted.png',
    'learning_curve': 'cost_temporal_learning_curve.png',
    'residual_plot': 'cost_temporal_residual_plot.png',
    'shap_summary': 'cost_temporal_shap_summary.png',
}

NAVY = '#17324D'
TEAL = '#168C8C'
CORAL = '#D76A5B'
MUTED = '#627487'


def _style(ax, title, xlabel, ylabel):
    ax.set_title(title, loc='left', color=NAVY, fontsize=15, fontweight='bold', pad=14)
    ax.set_xlabel(xlabel, color=MUTED)
    ax.set_ylabel(ylabel, color=MUTED)
    ax.grid(True, color='#DCE5EA', linewidth=.7, alpha=.8)
    ax.spines[['top', 'right']].set_visible(False)
    ax.spines[['left', 'bottom']].set_color('#C9D4DC')


def write_plots(output_dir, actual, predicted, history, features, shap_values):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    y = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    residual = p - y
    ape = np.abs(residual) / np.maximum(np.abs(y), 1e-9)
    plt.rcParams.update({'figure.facecolor': 'white', 'axes.facecolor': 'white', 'font.family': 'DejaVu Sans'})

    fig, ax = plt.subplots(figsize=(9, 7), constrained_layout=True)
    positive = (y > 0) & (p > 0)
    log_actual, log_pred = np.log10(y[positive]), np.log10(p[positive])
    hb = ax.hexbin(log_actual, log_pred, gridsize=70, bins='log', mincnt=1, cmap='GnBu', linewidths=0)
    low = float(min(log_actual.min(), log_pred.min()))
    high = float(max(log_actual.max(), log_pred.max()))
    ax.plot([low, high], [low, high], color=CORAL, linewidth=1.8, linestyle='--', label='Prediksi = aktual')
    powers = np.arange(np.floor(low), np.ceil(high) + 1)
    ax.set_xticks(powers, [f'10^{int(k)}' for k in powers]); ax.set_yticks(powers, [f'10^{int(k)}' for k in powers])
    ax.set_xlim(low, high); ax.set_ylim(low, high)
    _style(ax, 'Actual vs Predicted', 'Biaya verifikasi aktual · FKL48 (Rp, log)', 'Prediksi biaya (Rp, log)')
    fig.colorbar(hb, ax=ax, label='Kepadatan klaim (log count)')
    ax.legend(frameon=False, loc='upper left')
    ax.text(.98, .04, f'n = {len(y):,}\nMAPE = {ape.mean()*100:.2f}%\nMAE = Rp {np.abs(residual).mean():,.0f}',
            transform=ax.transAxes, ha='right', va='bottom', color=NAVY,
            bbox={'boxstyle': 'round,pad=.5', 'facecolor': '#F1F6F7', 'edgecolor': 'none'})
    fig.savefig(output_dir / PLOT_FILENAMES['actual_vs_predicted'], dpi=180); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
    rounds = np.arange(1, len(history['train']['mae']) + 1)
    ax.plot(rounds, history['train']['mae'], color=TEAL, linewidth=2.1, label='Train MAE')
    ax.plot(rounds, history['validation']['mae'], color=CORAL, linewidth=2.1, label='Validation MAE')
    best = int(np.argmin(history['validation']['mae'])) + 1
    ax.axvline(best, color=MUTED, linewidth=1, linestyle=':', label=f'Iterasi terbaik: {best}')
    ax.scatter([best], [history['validation']['mae'][best-1]], color=CORAL, zorder=4)
    _style(ax, 'Learning Curve', 'Boosting iteration', 'MAE validasi (Rp)')
    ax.legend(frameon=False)
    fig.savefig(output_dir / PLOT_FILENAMES['learning_curve'], dpi=180); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
    ax.scatter(p, residual, s=9, alpha=.24, color=TEAL, edgecolors='none', rasterized=True)
    ax.axhline(0, color=CORAL, linewidth=1.8, linestyle='--', label='Residual = 0')
    ax.set_xscale('log')
    display_limit = float(np.quantile(np.abs(residual), .99))
    ax.set_ylim(-display_limit, display_limit)
    _style(ax, 'Residual Plot', 'Prediksi biaya (Rp, log)', 'Residual: prediksi − aktual (Rp)')
    ax.legend(frameon=False)
    ax.text(.98, .04, f'Tampilan 99% residual tengah\n|residual| p99 = Rp {display_limit:,.0f}\nBias rata-rata = Rp {residual.mean():,.0f}',
            transform=ax.transAxes, ha='right', va='bottom', color=NAVY,
            bbox={'boxstyle': 'round,pad=.5', 'facecolor': '#F1F6F7', 'edgecolor': 'none'})
    fig.savefig(output_dir / PLOT_FILENAMES['residual_plot'], dpi=180); plt.close(fig)

    values = np.asarray(shap_values)
    importance = np.mean(np.abs(values), axis=0)
    order = np.argsort(importance)[::-1][:min(15, features.shape[1])]
    fig, ax = plt.subplots(figsize=(10, 7))
    rng = np.random.default_rng(42)
    norm = plt.Normalize(0, 1)
    for row, column in enumerate(order):
        vals = features.iloc[:, column].to_numpy(dtype=float)
        lo, hi = np.nanmin(vals), np.nanmax(vals)
        scaled = (vals - lo) / (hi - lo) if hi > lo else np.full(len(vals), .5)
        jitter = rng.uniform(-.28, .28, len(vals))
        ax.scatter(values[:, column], row + jitter, c=plt.cm.coolwarm(norm(scaled)),
                   s=10, alpha=.55, edgecolors='none', rasterized=True)
    ax.set_yticks(np.arange(len(order)), [features.columns[i] for i in order])
    ax.invert_yaxis()
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_title('SHAP Summary · Temporal audit model', loc='left', color=NAVY, fontsize=15, fontweight='bold', pad=14)
    ax.set_xlabel('Dampak fitur terhadap prediksi biaya (Rp)')
    ax.set_ylabel('Fitur · diurutkan menurut rata-rata |SHAP|')
    ax.grid(axis='x', color='#DCE5EA', linewidth=.7, alpha=.8)
    ax.spines[['top', 'right', 'left']].set_visible(False)
    shap_limit = float(np.quantile(np.abs(values[:, order]), .99))
    ax.set_xlim(-shap_limit, shap_limit)
    ax.text(.99, .02, 'Rentang sumbu menampilkan 99% kontribusi; ekor tidak dipotong dari perhitungan.',
            transform=ax.transAxes, ha='right', va='bottom', color=MUTED, fontsize=8)
    sm = plt.cm.ScalarMappable(norm=norm, cmap='coolwarm')
    fig.colorbar(sm, ax=ax, pad=.02, label='Nilai fitur relatif: rendah → tinggi')
    fig.tight_layout(rect=(0, .055, 1, 1))
    fig.text(.01, .01, 'TreeSHAP menjelaskan prediksi biaya model, bukan bukti fraud atau kebutuhan medis.', fontsize=8, color=MUTED)
    fig.savefig(output_dir / PLOT_FILENAMES['shap_summary'], dpi=180); plt.close(fig)
    return list(PLOT_FILENAMES.values())


def main():
    from scripts.bpjs.cost_temporal_audit import CUTOFF, OUT, fit_context, load_data, make_features
    from scripts.bpjs.cost_audit_utils import split_masks
    import json
    import xgboost as xgb

    df = load_data()
    fit_mask, _, test_mask = split_masks(df, CUTOFF)
    fit, test = df.loc[fit_mask].reset_index(drop=True), df.loc[test_mask].reset_index(drop=True)
    ctx = fit_context(fit)
    # Five-fold subject cross-fit for training rows is not used by test-time SHAP; test uses the complete fit table.
    xtest, _ = make_features(test, ctx)
    model = xgb.Booster(); model.load_model(OUT / 'xgb_with_base.json')
    predictions = model.predict(xgb.DMatrix(xtest))
    results = json.loads((OUT / 'results.json').read_text(encoding='utf-8'))
    history = results['learning_curve']
    sample = xtest.sample(n=min(1200, len(xtest)), random_state=42)
    sample_matrix = xgb.DMatrix(sample, feature_names=list(sample.columns))
    contribution_values = model.predict(sample_matrix, pred_contribs=True)
    values = contribution_values[:, :-1]
    prediction_from_contributions = contribution_values.sum(axis=1)
    prediction = model.predict(sample_matrix)
    if not np.allclose(prediction_from_contributions, prediction, rtol=1e-5, atol=.1):
        raise RuntimeError('TreeSHAP contributions do not add up to model prediction')
    figure_dir = ROOT / 'docs' / 'figures' / 'cost_temporal'
    filenames = write_plots(figure_dir, test.cost.to_numpy(), predictions, history, sample, values)
    print('generated', ', '.join(filenames))


if __name__ == '__main__':
    main()
