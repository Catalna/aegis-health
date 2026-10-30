"""As-of cohort filtering and subject-cross-fitted empirical tariff lookups."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.bpjs.cost_audit_utils import subject_bucket

GROUP_KEYS = (
    ('inacbg', 'sev', 'province', 'provider_type', 'care_class'),
    ('inacbg', 'sev', 'province', 'provider_type'),
    ('inacbg', 'sev', 'province'),
    ('inacbg', 'sev'),
)


def eligible_history(frame: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    boundary = pd.Timestamp(cutoff)
    return frame.loc[(frame['FKL03'] < boundary) & (frame['FKL04'] < boundary)].copy()


def tariff_tables(fit: pd.DataFrame, min_count: int = 20) -> dict:
    if fit.empty:
        raise ValueError('Cannot fit tariff lookup without past, verified rows')
    levels = []
    for keys in GROUP_KEYS:
        agg = fit.groupby(list(keys), observed=True)['cost'].agg(['median', 'size'])
        # Use small cells only at broader levels when no supported finer peer group exists.
        required = min_count if len(keys) > 2 else 1
        levels.append(agg['median'].where(agg['size'] >= required).astype('float32'))
    return {'levels': levels, 'global': float(fit.cost.median())}


def lookup_tariff(query: pd.DataFrame, tables: dict) -> np.ndarray:
    result = np.full(len(query), np.nan, dtype='float32')
    for keys, series in zip(GROUP_KEYS, tables['levels']):
        index = pd.MultiIndex.from_frame(query[list(keys)])
        matched = series.reindex(index).to_numpy(dtype='float32')
        result = np.where(np.isnan(result), matched, result)
    return np.where(np.isnan(result), tables['global'], result).astype('float32')


def crossfit_tariffs(fit: pd.DataFrame, min_count: int = 20, folds: int = 5):
    if folds < 2:
        raise ValueError('Cross-fitting requires at least two subject folds')
    buckets = subject_bucket(fit.PSTV01, folds)
    values = np.empty(len(fit), dtype='float32')
    for fold in range(folds):
        mask = buckets == fold
        if mask.any():
            table = tariff_tables(fit.loc[~mask], min_count=min_count)
            values[mask] = lookup_tariff(fit.loc[mask], table)
    return values, buckets
