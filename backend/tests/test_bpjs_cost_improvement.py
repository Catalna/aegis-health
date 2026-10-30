import numpy as np
import pandas as pd

from scripts.bpjs.cost_improvement_utils import eligible_history, tariff_tables, lookup_tariff, crossfit_tariffs
from scripts.bpjs.cost_improvement_experiment import model_matrix, select_on_validation, inverse_target, raw_mae_metric, save_inference_context


def sample():
    return pd.DataFrame({
        'PSTV01': [1, 1, 2, 3, 4, 5],
        'FKL03': pd.to_datetime(['2024-09-01'] * 6),
        'FKL04': pd.to_datetime(['2024-09-03'] * 5 + ['2024-11-01']),
        'inacbg': ['A'] * 6, 'sev': [1] * 6,
        'province': [1, 1, 1, 2, 2, 1],
        'provider_type': [1] * 6, 'care_class': [3] * 6,
        'cost': [100., 100., 200., 500., 700., 1000.],
    })


def test_history_excludes_visits_not_discharged_before_cutoff():
    eligible = eligible_history(sample(), '2024-11-01')
    assert len(eligible) == 5
    assert eligible.FKL04.max() < pd.Timestamp('2024-11-01')


def test_hierarchical_tariff_falls_back_to_group_then_global():
    history = sample().iloc[:5]
    table = tariff_tables(history, min_count=2)
    query = history.iloc[[0, 2, 3]].copy()
    query.loc[3, 'inacbg'] = 'UNKNOWN'
    prices = lookup_tariff(query, table)
    assert prices[0] == 100  # province 1 has three claims (median 100)
    assert prices[1] == 100  # province 1 median is 100 for this case
    assert prices[2] == 200  # unseen group falls back to global median


def test_crossfit_does_not_train_on_own_subject():
    history = sample().iloc[:5]
    prices, fold_ids = crossfit_tariffs(history, min_count=2, folds=3)
    assert len(prices) == len(history)
    assert fold_ids[0] == fold_ids[1]
    for index, subject in enumerate(history.PSTV01):
        available = history.loc[fold_ids != fold_ids[index]]
        expected = lookup_tariff(history.iloc[[index]], tariff_tables(available, min_count=2))[0]
        assert prices[index] == expected


def test_matrix_is_fit_vocabulary_only_and_never_includes_cost_or_participant():
    fit = sample().iloc[:5].copy()
    fit['diag'] = ['A00', 'A00', 'B00', 'C00', 'C00']
    query = sample().iloc[5:].copy()
    query['diag'] = ['NOT_SEEN']
    fit['los'] = 2
    query['los'] = 2
    xfit, xquery = model_matrix(fit, query, np.ones(5), np.ones(1))
    assert 'cost' not in xfit and 'PSTV01' not in xfit and 'FKL03' not in xfit
    assert xfit['inacbg'].dtype.name == 'category'
    assert xquery['diag_code'].iloc[0] == -1


def test_selection_is_by_validation_mae_and_log_inverse_is_positive():
    names = {'a': {'mae_rp': 20, 'mape_pct': 1}, 'b': {'mae_rp': 10, 'mape_pct': 5}}
    assert select_on_validation(names) == 'b'
    assert np.all(inverse_target(np.array([-20., np.log1p(100.)])) >= 0)


def test_log_objective_is_stopped_using_mae_in_rupiah_not_log_space():
    import xgboost as xgb

    truth = np.array([100., 10000.])
    matrix = xgb.DMatrix(np.zeros((2, 1)), label=np.log1p(truth))
    score, value = raw_mae_metric(np.log1p([110., 9000.]), matrix)
    assert score == 'mae_rupiah'
    assert abs(value - 505.) < .01  # DMatrix stores log-labels as float32


def test_inference_context_persists_only_aggregate_lookup_and_vocab(tmp_path):
    history = sample().iloc[:5].copy()
    history['diag'] = ['A00', 'A00', 'B00', 'C00', 'C00']
    save_inference_context(tmp_path, history, tariff_tables(history, min_count=2), min_count=2)
    import json
    doc = json.loads((tmp_path / 'feature_context.json').read_text(encoding='utf-8'))
    assert doc['min_count'] == 2 and doc['inacbg_categories'] == ['A']
    assert doc['diagnoses']['A00'] == 0
    assert 'PSTV01' not in (tmp_path / 'feature_context.json').read_text(encoding='utf-8')
    assert len(list(tmp_path.glob('tariff_level_*.csv'))) == 4
