import numpy as np
import pandas as pd

from scripts.bpjs.plot_cost_temporal_audit import PLOT_FILENAMES, write_plots
from scripts.bpjs.cost_improvement_experiment import learning_curve_from_eval


def test_plotter_writes_four_named_model_diagnostics(tmp_path):
    rng = np.random.default_rng(3)
    actual = np.linspace(100, 1000, 120)
    predicted = actual + rng.normal(0, 40, len(actual))
    features = pd.DataFrame({'age': rng.normal(50, 10, len(actual)), 'los': rng.integers(1, 10, len(actual)),
                             'inacbg': pd.Categorical(rng.choice(['A', 'B', 'C'], len(actual)))})
    shap_values = np.column_stack([rng.normal(0, 1, len(actual)) for _ in range(3)])
    history = {'train': {'mae': [80, 50, 30]}, 'validation': {'mae': [90, 55, 42]}}
    written = write_plots(tmp_path, actual, predicted, history, features, shap_values)
    assert set(written) == set(PLOT_FILENAMES.values())
    assert all((tmp_path / name).is_file() and (tmp_path / name).stat().st_size > 1000 for name in PLOT_FILENAMES.values())


def test_log_learning_history_uses_rupiah_metric_for_fit_and_validation():
    evals = {
        'train': {'mae': [0.5, 0.4], 'mae_rupiah': [1000., 800.]},
        'validation': {'mae': [0.6, 0.5], 'mae_rupiah': [1200., 900.]},
    }
    assert learning_curve_from_eval(evals, use_log=True) == {
        'train': {'mae': [1000., 800.]}, 'validation': {'mae': [1200., 900.]}}
