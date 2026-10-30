"""Post-grouper, pre-verification offline tariff and XGBoost comparison."""
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import xgboost as xgb

from scripts.bpjs.cost_audit_utils import fit_context, make_features, metrics, split_masks
from scripts.bpjs.cost_improvement_utils import GROUP_KEYS, eligible_history, tariff_tables, lookup_tariff, crossfit_tariffs

SOURCE_ROOT = Path(r'C:\Users\Radith\E-Jak')
OUT = ROOT / 'backend/app/data/analysis/cost_improvement'
CUTOFF = '2024-11-01'


def model_matrix(fit: pd.DataFrame, other: pd.DataFrame, fit_tariff, other_tariff):
    ctx = fit_context(fit)
    xf, _ = make_features(fit, ctx, include_base=False)
    xo, _ = make_features(other, ctx, include_base=False)
    xf['empirical_tariff'] = np.asarray(fit_tariff, dtype='float32')
    xo['empirical_tariff'] = np.asarray(other_tariff, dtype='float32')
    categories = pd.CategoricalDtype(categories=sorted(fit.inacbg.unique()))
    xf['inacbg'] = fit.inacbg.reset_index(drop=True).astype(categories)
    xo['inacbg'] = other.inacbg.reset_index(drop=True).astype(categories)
    return xf, xo


def inverse_target(values):
    return np.maximum(0, np.expm1(np.asarray(values, dtype=float)))


def raw_mae_metric(predictions, dmatrix):
    actual = inverse_target(dmatrix.get_label())
    return 'mae_rupiah', float(np.mean(np.abs(inverse_target(predictions) - actual)))


def learning_curve_from_eval(evals, *, use_log):
    metric = 'mae_rupiah' if use_log else 'mae'
    return {dataset: {'mae': list(values[metric])} for dataset, values in evals.items()}


def select_on_validation(scores):
    return min(scores, key=lambda name: (scores[name]['mae_rp'], name))


def load_cohorts():
    from scripts.bpjs import cost_temporal_audit
    cost_temporal_audit.DATA = SOURCE_ROOT / 'backend/app/data/2025/Data Sampel Reguler Edisi 2025/data'
    df = cost_temporal_audit.load_data()
    fit, val, test = split_masks(df, CUTOFF)
    # Date of BPJS verification is unknown; discharge cutoff is a necessary, not sufficient, guard.
    history = eligible_history(df, CUTOFF)
    fit = history.loc[fit[history.index]].reset_index(drop=True)
    val = history.loc[val[history.index]].reset_index(drop=True)
    test = df.loc[test].reset_index(drop=True)
    return fit, val, test


def choose_device():
    try:
        a = xgb.DMatrix(np.arange(120, dtype='float32').reshape(40, 3), label=np.arange(40, dtype='float32'))
        xgb.train({'tree_method': 'hist', 'device': 'cuda', 'objective': 'reg:squarederror',
                   'nthread': 4, 'verbosity': 0}, a, num_boost_round=2).predict(a)
        return 'cuda'
    except (xgb.core.XGBoostError, RuntimeError) as exc:
        print('CUDA unavailable for XGBoost, using CPU:', exc, flush=True)
        return 'cpu'


def train_variant(name, fit_x, val_x, fit_y, val_y, *, device):
    use_log = name.startswith('log')
    train_y = np.log1p(fit_y) if use_log else fit_y
    valid_y = np.log1p(val_y) if use_log else val_y
    train = xgb.DMatrix(fit_x, label=train_y, enable_categorical=True)
    valid = xgb.DMatrix(val_x, label=valid_y, enable_categorical=True)
    params = {'objective': 'reg:squarederror', 'eval_metric': 'mae', 'tree_method': 'hist',
              'device': device, 'eta': .05, 'max_depth': 7, 'min_child_weight': 5,
              'subsample': .85, 'colsample_bytree': .9, 'max_cat_to_onehot': 8,
              'max_cat_threshold': 64, 'seed': 42, 'nthread': 8}
    history = {}
    start = time.monotonic()
    model = xgb.train(params, train, num_boost_round=3000, evals=[(train, 'train'), (valid, 'validation')],
                      custom_metric=raw_mae_metric if use_log else None,
                      evals_result=history, early_stopping_rounds=55, verbose_eval=False)
    best = model[:model.best_iteration + 1]
    raw = best.predict(xgb.DMatrix(val_x, enable_categorical=True))
    pred = inverse_target(raw) if use_log else np.maximum(raw, 0)
    return best, pred, {'rounds': best.num_boosted_rounds(), 'elapsed_sec': round(time.monotonic() - start, 2),
                        'negative_unclipped': int((raw < 0).sum()), 'history': history}


def bootstrap_mae_gap(frame, winner, baseline, *, seed=42, iterations=2000):
    """Paired participant bootstrap; positive difference means winner is worse."""
    d = pd.DataFrame({'participant': frame.PSTV01.to_numpy(), 'a': abs(winner-frame.cost.to_numpy()),
                      'b': abs(baseline-frame.cost.to_numpy())})
    group = d.groupby('participant').agg(n=('a', 'size'), a=('a', 'sum'), b=('b', 'sum')).to_numpy()
    rng = np.random.default_rng(seed)
    diffs = np.empty(iterations)
    for i in range(iterations):
        sample = group[rng.integers(len(group), size=len(group))].sum(axis=0)
        diffs[i] = (sample[1]-sample[2])/sample[0]
    return {'subjects': len(group), 'n': len(frame), 'difference_rp': float((d.a-d.b).mean()),
            'ci95_rp': np.quantile(diffs, [.025, .975]).tolist(), 'bootstrap_iterations': iterations}


def save_inference_context(output, fit, tables, *, min_count):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    context = fit_context(fit)
    payload = {'inacbg_categories': sorted(fit.inacbg.unique()), 'diagnoses': context['diagnoses'],
               'global_median_rp': tables['global'], 'min_count': min_count,
               'keys': [list(k) for k in GROUP_KEYS],
               'model_target': 'verified FKRTL cost after grouper, before verification'}
    (output / 'feature_context.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    for i, (keys, table) in enumerate(zip(GROUP_KEYS, tables['levels'])):
        table.dropna().rename('median_rp').reset_index().to_csv(output / f'tariff_level_{i}.csv', index=False)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fit, val, test = load_cohorts()
    assert max(fit.FKL04.max(), val.FKL04.max()) < pd.Timestamp(CUTOFF)
    assert test.FKL03.min() >= pd.Timestamp(CUTOFF)
    assert not (set(fit.PSTV01) & set(val.PSTV01) or set(fit.PSTV01) & set(test.PSTV01)
                or set(val.PSTV01) & set(test.PSTV01))
    print('cohorts', len(fit), len(val), len(test), flush=True)
    fine = tariff_tables(fit, min_count=20)
    save_inference_context(OUT, fit, fine, min_count=20)
    fit_fine, folds = crossfit_tariffs(fit, min_count=20, folds=5)
    val_fine, test_fine = lookup_tariff(val, fine), lookup_tariff(test, fine)
    global_ctx = fit_context(fit)
    _, val_simple = make_features(val, global_ctx)
    _, test_simple = make_features(test, global_ctx)
    train_x, val_x = model_matrix(fit, val, fit_fine, val_fine)
    _, test_x = model_matrix(fit, test, fit_fine, test_fine)
    assert list(train_x.columns) == list(val_x.columns) == list(test_x.columns)
    baseline_val = {'simple_median': val_simple, 'hierarchical_median': val_fine}
    candidates = {k: metrics(val.cost, p) for k, p in baseline_val.items()}
    models, meta = {}, {}
    learning_curve = None
    device = choose_device()
    for name in ('raw_xgb', 'log_xgb'):
        model, val_pred, details = train_variant(name, train_x, val_x, fit.cost, val.cost, device=device)
        models[name] = model
        meta[name] = {k: v for k, v in details.items() if k != 'history'}
        if name == 'log_xgb':
            learning_curve = learning_curve_from_eval(details['history'], use_log=True)
        model.save_model(OUT / f'{name}.json')
        candidates[name] = metrics(val.cost, val_pred)
        print(name, 'validation', candidates[name], 'rounds', details['rounds'], flush=True)
    winner = select_on_validation(candidates)
    # The test set is reused from the previous audit. Never select/retune based on this evaluation.
    test_preds = {'simple_median': test_simple, 'hierarchical_median': test_fine}
    for name, model in models.items():
        raw = model.predict(xgb.DMatrix(test_x, enable_categorical=True))
        test_preds[name] = inverse_target(raw) if name.startswith('log') else np.maximum(raw, 0)
    views = {'all': np.ones(len(test), dtype=bool), 'dialysis': test.inacbg.eq('Q-5-44-0').to_numpy(),
             'non_dialysis': test.inacbg.ne('Q-5-44-0').to_numpy(),
             'over_20m_actual': test.cost.gt(20_000_000).to_numpy()}
    scores = {name: {key: metrics(test.cost.to_numpy()[mask], np.asarray(pred)[mask])
                     for key, mask in views.items() if mask.any()} for name, pred in test_preds.items()}
    print('selected on validation', winner, flush=True)
    for key in ['all','over_20m_actual']:
        print(key, {name: scores[name][key] for name in scores}, flush=True)
    rare = test.diag.map(fit.diag.value_counts()).fillna(0) < 100
    diag_audit = {label: {'n': int(mask.sum()), 'codes': int(test.loc[mask, 'diag'].nunique()),
                          'winner': metrics(test.loc[mask, 'cost'], np.asarray(test_preds[winner])[mask])}
                  for label, mask in [('unseen', ~test.diag.isin(fit.diag)), ('rare_lt100_fit', rare),
                                      ('common_ge100_fit', ~rare)] if mask.any()}
    ci = {key: bootstrap_mae_gap(test.loc[mask].reset_index(drop=True), np.asarray(test_preds[winner])[mask],
                                 np.asarray(test_preds['simple_median'])[mask]) for key, mask in views.items() if key in ('all','over_20m_actual')}
    result = {'setup': {'task': 'post-grouper, pre-verification conditional cost estimate',
                        'training_history': 'discharge < 2024-11-01; verification time unavailable',
                        'test': 'reused Nov-Dec 2024 holdout; not untouched', 'fit': len(fit), 'val': len(val), 'test_n': len(test),
                        'seed': 42, 'device': device, 'min_granular_cell_n': 20, 'feature_names': list(train_x.columns),
                        'source': 'FKL48 verified cost on fully accepted FKRTL claims'},
              'validation': candidates, 'selected_by_val_mae': winner, 'training': meta,
              'test_metrics': scores, 'diagnosis': diag_audit, 'paired_bootstrap_vs_simple_median': ci,
              'learning_curve': learning_curve}
    (OUT / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, default=float), encoding='utf-8')
    print('results ->', OUT / 'results.json', flush=True)


if __name__ == '__main__':
    main()
