"""Offline temporal and subject-disjoint cost benchmark; never alters runtime models."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import xgboost as xgb

from scripts.bpjs.cost_audit_utils import fit_context, make_features, metrics, split_masks, subject_bucket

DATA = ROOT / 'backend/app/data/2025/Data Sampel Reguler Edisi 2025/data'
OUT = ROOT / 'backend/app/data/analysis/cost_temporal_audit'
CUTOFF = '2024-11-01'


def load_data():
    cols = ['PSTV01', 'FKL02', 'FKL03', 'FKL04', 'FKL05_NEW', 'FKL09', 'FKL13', 'FKL15A', 'FKL19', 'FKL23', 'FKL30', 'FKL47', 'FKL48']
    df = pd.read_stata(DATA / '202403_fkrtl.dta', columns=cols, convert_categoricals=False)
    los = (df.FKL04 - df.FKL03).dt.days
    mask = df.FKL47.eq(df.FKL48) & (df.FKL48 > 0) & los.between(0, 365) & df.FKL19.fillna('').astype(str).str.strip().ne('')
    df = df.loc[mask].copy()
    df['los'] = los.loc[mask]
    df['inacbg'] = df.FKL19.astype(str).str.strip()
    df['diag'] = df.FKL15A.fillna('').astype(str).str.strip().str.split('.').str[0]
    df['has_proc'] = df.FKL30.fillna('').astype(str).str.strip().ne('').astype('float32')
    df = df.rename(columns={'FKL23': 'sev', 'FKL48': 'cost', 'FKL05_NEW': 'province', 'FKL09': 'provider_type', 'FKL13': 'care_class'})
    participants = pd.read_stata(DATA / '2015202401_kepesertaan.dta', columns=['PSTV01', 'PSTV03'], convert_categoricals=False)
    participants = participants.drop_duplicates('PSTV01', keep='last')
    participants['birth_year'] = pd.to_datetime(participants.PSTV03).dt.year
    df = df.merge(participants[['PSTV01', 'birth_year']], on='PSTV01', how='left', validate='many_to_one')
    df['age'] = (df.FKL03.dt.year - df.birth_year).where(lambda x: x.between(0, 120))
    del participants
    secondary = pd.read_stata(DATA / '202405_diagnosissekunder.dta', columns=['FKL02'], convert_categoricals=False)
    counts = secondary.FKL02.astype(str).value_counts()
    df['n_secondary'] = df.FKL02.astype(str).map(counts).fillna(0)
    return df


def train_model(xfit, yfit, xval, yval):
    fit = xgb.DMatrix(xfit, label=yfit)
    val = xgb.DMatrix(xval, label=yval)
    params = {'objective': 'reg:squarederror', 'eval_metric': 'mae', 'tree_method': 'hist', 'eta': .05,
              'max_depth': 8, 'subsample': .8, 'colsample_bytree': .8, 'nthread': -1, 'seed': 42}
    history = {}
    model = xgb.train(params, fit, num_boost_round=400, evals=[(fit, 'train'), (val, 'validation')],
                      early_stopping_rounds=25, evals_result=history, verbose_eval=False)
    return model[:model.best_iteration + 1], history


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_data()
    fit_mask, val_mask, test_mask = split_masks(df, CUTOFF)
    fit, val, test = (df.loc[m].copy().reset_index(drop=True) for m in (fit_mask, val_mask, test_mask))
    for name, frame in [('fit', fit), ('validation', val), ('test', test)]:
        print(name, 'rows', len(frame), 'subjects', frame.PSTV01.nunique(), 'dates', frame.FKL03.min(), frame.FKL03.max(), flush=True)
    ctx = fit_context(fit)
    xfit, _ = make_features(fit, ctx)
    xval, baseline_val = make_features(val, ctx)
    xtest, baseline_test = make_features(test, ctx)
    # Cross-fit target-derived base rate by participant: no row contributes to its own feature.
    folds = subject_bucket(fit.PSTV01, 5)
    for fold in range(5):
        in_fold = folds == fold
        fold_ctx = fit_context(fit.loc[~in_fold])
        _, rate = make_features(fit.loc[in_fold], fold_ctx)
        xfit.loc[in_fold, 'base_rate'] = rate
    results = {'config': {'cutoff': CUTOFF, 'fit_rows': len(fit), 'validation_rows': len(val), 'test_rows': len(test),
                          'excluded_rows': len(df) - len(fit) - len(val) - len(test),
                          'training_base_rate': '5-fold subject-disjoint cross-fit', 'weighting': 'none',
                          'global_baseline_rp': ctx['global'],
                          'feature_names': list(xfit.columns), 'xgboost_version': xgb.__version__}, 'validation': {}, 'test': {}}
    predictions = {'median_baseline': (baseline_val, baseline_test)}
    for label, use_base in [('xgb_with_base', True), ('xgb_without_base', False)]:
        cols = list(xfit.columns) if use_base else [c for c in xfit.columns if c != 'base_rate']
        model, history = train_model(xfit[cols], fit.cost, xval[cols], val.cost)
        model.save_model(OUT / f'{label}.json')
        predictions[label] = (model.predict(xgb.DMatrix(xval[cols])), model.predict(xgb.DMatrix(xtest[cols])))
        results['config'][label + '_trees'] = model.num_boosted_rounds()
        if label == 'xgb_with_base':
            results['learning_curve'] = history
        print(label, 'trees', model.num_boosted_rounds(), flush=True)
    for label, (pv, pt) in predictions.items():
        results['validation'][label] = metrics(val.cost, pv)
        views = {'all': np.ones(len(test), dtype=bool), 'dialysis': test.inacbg.eq('Q-5-44-0').to_numpy(),
                 'non_dialysis': test.inacbg.ne('Q-5-44-0').to_numpy(), 'above_20m': test.cost.gt(20_000_000).to_numpy()}
        results['test'][label] = {key: metrics(test.cost.to_numpy()[mask], pt[mask]) for key, mask in views.items() if mask.any()}
    results['config']['test_unseen_baseline_rows'] = int((~pd.MultiIndex.from_arrays([test.inacbg, test.sev]).isin(ctx['table'].index)).sum())
    results['config']['diagnosis_unknown_test_rows'] = int((~test.diag.isin(ctx['diagnoses'])).sum())
    (OUT / 'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    ctx['table'].rename('base_rate').reset_index().to_csv(OUT / 'fit_baseline.csv', index=False)
    (OUT / 'diagnosis_mapping.json').write_text(json.dumps(ctx['diagnoses'], ensure_ascii=False), encoding='utf-8')
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    main()
