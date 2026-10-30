import numpy as np
import pandas as pd

from scripts.bpjs.cost_audit_utils import split_masks, fit_context, make_features, metrics


def test_split_is_chronological_and_subject_disjoint():
    df = pd.DataFrame({'PSTV01': [1, 2, 3, 4, 4], 'FKL03': pd.to_datetime(['2024-01-01', '2024-02-01', '2024-11-01', '2024-01-01', '2024-12-01'])})
    fit, val, test = split_masks(df, '2024-11-01')
    groups = [set(df.loc[m, 'PSTV01']) for m in (fit, val, test)]
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    assert (df.loc[fit | val, 'FKL03'] < pd.Timestamp('2024-11-01')).all()
    assert (df.loc[test, 'FKL03'] >= pd.Timestamp('2024-11-01')).all()


def test_context_is_fit_only_with_unseen_fallback_and_distinct_diagnosis():
    fit = pd.DataFrame({'inacbg': ['A', 'A', 'B'], 'sev': [1, 1, 1], 'cost': [10., 20., 30.], 'diag': ['J18', 'J18', 'N18'], 'los': [1, 2, 3]})
    ctx = fit_context(fit)
    target = pd.DataFrame({'inacbg': ['A', 'C'], 'sev': [1, 1], 'diag': ['J18', 'UNKNOWN'], 'los': [1, 3]})
    x, base = make_features(target, ctx, include_base=True)
    assert base.tolist() == [15., 20.]
    assert x.loc[0, 'diag_code'] != x.loc[1, 'diag_code']
    assert x.loc[1, 'diag_code'] == -1


def test_metrics_reports_negative_predictions_without_clipping():
    m = metrics(np.array([10., 20.]), np.array([-1., 20.]))
    assert m['negative_predictions'] == 1
    assert m['mae_rp'] == 5.5
