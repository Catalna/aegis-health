import { useState, useEffect } from 'react'
import { mlApi, formatFeature } from '../api'

const METRIC_LABELS = {
  precision: 'Ketepatan temuan',
  recall: 'Cakupan temuan',
  f1: 'Keseimbangan hasil',
  roc_auc: 'Kemampuan membedakan',
  pr_auc: 'Ketepatan berdasarkan prioritas',
}

const TYPE_LABELS = {
  upcoding: 'Tingkat keparahan tidak sesuai',
  cloning: 'Kemiripan antar klaim',
  repeat_billing: 'Pengulangan tagihan',
  phantom_billing: 'Tindakan tidak terbukti',
  prolonged_los: 'Lama rawat tidak biasa',
  inflated_bill: 'Biaya tidak wajar',
  unbundling: 'Pemisahan tagihan',
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
        else setError('Gagal memuat hasil evaluasi. Pastikan layanan pemeriksaan aktif.')
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="status-message" aria-live="polite"><strong>Menyiapkan evaluasi</strong><p>Ketepatan pemeriksaan sedang dimuat.</p></div>
  if (error) return <div className="status-message error" role="alert"><strong>Hasil evaluasi belum dapat dimuat</strong><p>{error}</p></div>

  const importance = Object.entries(data.feature_importance || {}).slice(0, 7)
  const perType = data.recall_per_anomaly_type || {}
  const ifMetrics = data.isolation_forest || {}

  return (
    <div className="max-w-4xl mx-auto py-8">
      <div className="page-header mb-8">
        <div className="page-kicker">Pemeriksaan kualitas</div>
        <h2 className="glow-text">Evaluasi Ketepatan Sistem</h2>
        <p>
           Ringkasan ketepatan pemeriksaan pada data uji terpisah yang tidak digunakan saat penyusunan aturan.
        </p>
        {data.methodology?.note && (
          <div className="alert-disclaimer mt-2" style={{ fontSize: '0.75rem' }}>
             ⓘ Data uji dibuat terpisah agar angka ketepatan menggambarkan kemampuan pemeriksaan pada kasus baru.
          </div>
        )}
      </div>

      <div className="grid-2 mb-6">
        <div className="card">
           <h3 className="card-title">Data Pengujian</h3>
          <ul className="space-y-2 mt-4 text-sm">
            <li className="flex justify-between"><span>Total Klaim</span> <strong>{(data.dataset.total_samples || 0).toLocaleString('id-ID')}</strong></li>
             <li className="flex justify-between"><span>Data penyusunan</span> <strong>{(data.dataset.train_size || 0).toLocaleString('id-ID')}</strong></li>
             <li className="flex justify-between"><span>Data penyesuaian</span> <strong>{(data.dataset.val_size || 0).toLocaleString('id-ID')}</strong></li>
             <li className="flex justify-between"><span>Data uji terpisah</span> <strong>{(data.dataset.test_size || 0).toLocaleString('id-ID')}</strong></li>
             <li className="flex justify-between"><span>Proporsi klaim bermasalah</span> <strong>{((data.dataset.fraud_rate || 0) * 100).toFixed(1)}%</strong></li>
          </ul>
          {data.xgboost_regressor && (
            <div className="mt-4 text-sm" style={{ borderTop: '1px solid var(--border)', paddingTop: '0.75rem' }}>
              <div className="flex justify-between">
                 <span>Rata-rata perbedaan perkiraan biaya</span>
                <strong>{data.xgboost_regressor.mape_pct_normal_holdout != null
                  ? `${data.xgboost_regressor.mape_pct_normal_holdout.toFixed(1)}%`
                   : 'Belum tersedia'}</strong>
              </div>
            </div>
          )}
        </div>

        <div className="card">
           <h3 className="card-title">Perbandingan Ketepatan</h3>
           <div className="table-container">
           <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b" style={{ borderColor: 'var(--border)' }}>
                <th className="py-2">Metric</th>
                 <th>Pemeriksaan utama</th>
                 <th>Pembanding awal</th>
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
      </div>

      {/* Recall per jenis anomali */}
      {Object.keys(perType).length > 0 && (
        <div className="card mb-6">
           <h3 className="card-title">Cakupan per Jenis Temuan</h3>
           <p className="text-xs text-muted mb-4">Seberapa banyak tiap pola klaim bermasalah yang berhasil ditemukan.</p>
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
             <div style={{ fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.25rem' }}>Catatan: pengulangan dan kemiripan antar klaim dinilai melalui hubungan antar data.</div>
            <div className="text-xs text-muted" style={{ lineHeight: 1.6 }}>
               Pengulangan dan kemiripan antar klaim membutuhkan perbandingan beberapa klaim sekaligus,
               bukan hanya melihat satu klaim. Karena itu, pola ini diperiksa melalui hubungan peserta,
               fasilitas kesehatan, tindakan, biaya, dan tanggal.
            </div>
          </div>
        </div>
      )}
      {ifMetrics.detection_rate_anomalies != null && (
        <div className="card mb-6">
           <h3 className="card-title">Pemeriksaan Pola Tidak Biasa</h3>
          <div className="grid-2 mt-3" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8 }}>
              <div className="text-xs text-muted">Deteksi pada klaim anomali</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--accent-green)' }}>
                {(ifMetrics.detection_rate_anomalies * 100).toFixed(1)}%
              </div>
            </div>
            <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8 }}>
               <div className="text-xs text-muted">Temuan keliru pada klaim wajar</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: ifMetrics.false_positive_rate_normal > 0.15 ? 'var(--risk-high)' : 'var(--success)' }}>
                {((ifMetrics.false_positive_rate_normal || 0) * 100).toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="card">
         <h3 className="card-title">Faktor yang Paling Berpengaruh</h3>
        <div className="mt-4">
          {importance.map(([feature, score]) => (
            <div key={feature} className="mb-4">
              <div className="flex justify-between text-sm mb-1">
                <span>{formatFeature(feature)}</span>
                <span>{(score * 100).toFixed(1)}%</span>
              </div>
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: `${score * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted mt-4">
           Angka dihitung dari data uji terpisah untuk mengurangi bias. Data yang digunakan tetap
           merupakan data simulasi, bukan data klaim JKN nyata.
        </p>
      </div>
    </div>
  )
}
