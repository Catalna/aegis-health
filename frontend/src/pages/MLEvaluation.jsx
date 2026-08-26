import { useState, useEffect } from 'react'
import { mlApi } from '../api'

const METRIC_LABELS = {
  precision: 'Precision',
  recall: 'Recall',
  f1: 'F1-Score',
  roc_auc: 'ROC-AUC',
  pr_auc: 'PR-AUC',
}

const TYPE_LABELS = {
  upcoding: 'Upcoding',
  cloning: 'Cloning',
  repeat_billing: 'Repeat Billing',
  phantom_billing: 'Phantom Billing',
  prolonged_los: 'Prolonged LOS',
  inflated_bill: 'Inflated Bill',
  unbundling: 'Unbundling',
}

export default function MLEvaluation() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    mlApi.evaluation()
      .then(res => setData(res.data))
      .catch(err => {
        if (err?.response?.status === 404) setError('Hasil evaluasi belum tersedia. Jalankan: python scripts/train_all.py')
        else setError('Gagal memuat hasil evaluasi model. Pastikan backend aktif.')
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-8 text-center text-muted">Memuat hasil evaluasi model...</div>
  if (error) return <div className="p-8 text-center" style={{ color: 'var(--risk-high)' }}>⚠ {error}</div>

  const importance = Object.entries(data.feature_importance || {}).slice(0, 7)
  const perType = data.recall_per_anomaly_type || {}
  const ifMetrics = data.isolation_forest || {}

  return (
    <div className="max-w-4xl mx-auto py-8">
      <div className="page-header mb-8">
        <h2 className="glow-text">Machine Learning Evaluation</h2>
        <p>
          Performa model deteksi anomali pada <strong>held-out test set</strong> — dataset independen
          yang digenerate terpisah (seed berbeda) dan tidak pernah dilihat saat tuning.
        </p>
        {data.methodology?.note && (
          <div className="alert-disclaimer mt-2" style={{ fontSize: '0.75rem' }}>
            ⓘ {data.methodology.note}
          </div>
        )}
      </div>

      <div className="grid-2 mb-6">
        <div className="card">
          <h3 className="card-title">Dataset Characteristics</h3>
          <ul className="space-y-2 mt-4 text-sm">
            <li className="flex justify-between"><span>Total Klaim</span> <strong>{(data.dataset.total_samples || 0).toLocaleString('id-ID')}</strong></li>
            <li className="flex justify-between"><span>Training Set</span> <strong>{(data.dataset.train_size || 0).toLocaleString('id-ID')}</strong></li>
            <li className="flex justify-between"><span>Validation Set</span> <strong>{(data.dataset.val_size || 0).toLocaleString('id-ID')}</strong></li>
            <li className="flex justify-between"><span>Held-out Test Set</span> <strong>{(data.dataset.test_size || 0).toLocaleString('id-ID')}</strong></li>
            <li className="flex justify-between"><span>Fraud Rate</span> <strong>{((data.dataset.fraud_rate || 0) * 100).toFixed(1)}%</strong></li>
          </ul>
          {data.xgboost_regressor && (
            <div className="mt-4 text-sm" style={{ borderTop: '1px solid var(--border)', paddingTop: '0.75rem' }}>
              <div className="flex justify-between">
                <span>Regressor MAPE (klaim normal)</span>
                <strong>{data.xgboost_regressor.mape_pct_normal_holdout != null
                  ? `${data.xgboost_regressor.mape_pct_normal_holdout.toFixed(1)}%`
                  : 'N/A'}</strong>
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <h3 className="card-title">Model Comparison (Held-out Test Set)</h3>
          <table className="w-full mt-4 text-sm text-left">
            <thead>
              <tr className="border-b" style={{ borderColor: 'var(--border)' }}>
                <th className="py-2">Metric</th>
                <th>XGBoost</th>
                <th>Baseline (LR)</th>
              </tr>
            </thead>
            <tbody>
              {['precision', 'recall', 'f1', 'roc_auc', 'pr_auc'].map(metric => (
                <tr key={metric} className="border-b" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-2">{METRIC_LABELS[metric]}</td>
                  <td className="font-bold" style={{ color: 'var(--accent-green)' }}>
                    {((data.xgboost_classifier?.[metric] ?? 0) * 100).toFixed(1)}%
                  </td>
                  <td className="text-muted">
                    {((data.logistic_regression_baseline?.[metric] ?? 0) * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recall per jenis anomali */}
      {Object.keys(perType).length > 0 && (
        <div className="card mb-6">
          <h3 className="card-title">Recall per Jenis Anomali (Held-out)</h3>
          <p className="text-xs text-muted mb-4">Seberapa banyak tiap pola fraud yang berhasil dideteksi classifier</p>
          <div className="grid-2" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
            {Object.entries(perType).map(([type, info]) => (
              <div key={type} style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border)' }}>
                <div className="flex justify-between text-sm mb-1">
                  <span>{TYPE_LABELS[type] || type}</span>
                  <strong style={{ color: info.recall >= 0.8 ? 'var(--success)' : info.recall >= 0.5 ? 'var(--warning)' : 'var(--risk-high)' }}>
                    {(info.recall * 100).toFixed(0)}%
                  </strong>
                </div>
                <div className="progress-bar" style={{ height: 4 }}>
                  <div className="progress-fill" style={{ width: `${info.recall * 100}%` }} />
                </div>
                <div className="text-xs text-muted mt-1">{info.count} sampel</div>
              </div>
            ))}
          </div>
          <div className="mt-4" style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.25rem' }}>Catatan: cloning & repeat billing recall rendah di classifier — by design</div>
            <div className="text-xs text-muted" style={{ lineHeight: 1.6 }}>
              Cloning dan repeat billing adalah <strong>anomali relasional</strong> (hubungan antar klaim),
              bukan penyimpangan fitur per-klaim — sehingga tidak terlihat oleh classifier berbasis fitur tunggal.
              Kedua pola ini ditangani oleh <strong>Fraud Agent</strong> via similarity search (LanceDB) dan
              pengecekan repeat billing (SQL pasien + prosedur + tanggal). Pembagian tugas ini sesuai desain
              PRD: satu sinyal per jenis anomali, semuanya explainable.
            </div>
          </div>
        </div>
      )}
      {ifMetrics.detection_rate_anomalies != null && (
        <div className="card mb-6">
          <h3 className="card-title">Isolation Forest (Unsupervised Baseline)</h3>
          <div className="grid-2 mt-3" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8 }}>
              <div className="text-xs text-muted">Deteksi pada klaim anomali</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--accent-green)' }}>
                {(ifMetrics.detection_rate_anomalies * 100).toFixed(1)}%
              </div>
            </div>
            <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8 }}>
              <div className="text-xs text-muted">False positive pada klaim normal</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: ifMetrics.false_positive_rate_normal > 0.15 ? 'var(--risk-high)' : 'var(--success)' }}>
                {((ifMetrics.false_positive_rate_normal || 0) * 100).toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <h3 className="card-title">XGBoost Feature Importance (Top 7)</h3>
        <div className="mt-4">
          {importance.map(([feature, score]) => (
            <div key={feature} className="mb-4">
              <div className="flex justify-between text-sm mb-1">
                <span className="font-mono text-xs">{feature}</span>
                <span>{(score * 100).toFixed(1)}%</span>
              </div>
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: `${score * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted mt-4">
          Metrik dihitung pada held-out test set yang tidak digunakan dalam pelatihan —
          menghindari bias tautologi data sintetis (PRD Section 10). Data tetap sintetis; angka ini
          bukan performa terhadap data JKN riil.
        </p>
      </div>
    </div>
  )
}
