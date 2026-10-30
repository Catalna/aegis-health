"""Shared, train-only feature and evaluation utilities for offline BPJS audit."""
from zlib import crc32

import numpy as np
import pandas as pd


def subject_bucket(values, modulus=10):
    return np.fromiter((crc32(str(v).encode()) % modulus for v in values), dtype=np.uint8, count=len(values))


def split_masks(df, cutoff):
    bucket = subject_bucket(df['PSTV01'])
    past = df['FKL03'] < pd.Timestamp(cutoff)
    return past & (bucket < 6), past & np.isin(bucket, [6, 7]), ~past & np.isin(bucket, [8, 9])


def fit_context(df):
    table = df.groupby(['inacbg', 'sev'], observed=True)['cost'].median()
    diags = sorted(df['diag'].fillna('').astype(str).unique())
    return {'table': table, 'global': float(df['cost'].median()), 'diagnoses': {v: i for i, v in enumerate(diags)}}


def make_features(df, ctx, include_base=True):
    keys = pd.MultiIndex.from_arrays([df['inacbg'], df['sev']], names=['inacbg', 'sev'])
    base = ctx['table'].reindex(keys).fillna(ctx['global']).to_numpy(dtype='float32')
    x = pd.DataFrame({'diag_code': df['diag'].fillna('').astype(str).map(ctx['diagnoses']).fillna(-1).to_numpy(dtype='float32'),
                      'los': df['los'].to_numpy(dtype='float32')})
    for name in ('sev', 'age', 'n_secondary', 'has_proc', 'province', 'provider_type', 'care_class'):
        if name in df:
            x[name] = pd.to_numeric(df[name], errors='coerce').to_numpy(dtype='float32')
    if include_base:
        x['base_rate'] = base
    return x, base


def metrics(actual, predicted):
    y = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    err = p - y
    ape = np.abs(err) / y
    variance = np.square(y - y.mean()).sum()
    return {'n': len(y), 'mape_pct': float(100 * ape.mean()), 'medape_pct': float(100 * np.median(ape)),
            'mae_rp': float(np.abs(err).mean()), 'rmse_rp': float(np.sqrt(np.square(err).mean())),
            'r2': float(1 - np.square(err).sum() / variance) if variance else None,
            'within10_pct': float(100 * (ape <= .1).mean()), 'negative_predictions': int((p < 0).sum())}
