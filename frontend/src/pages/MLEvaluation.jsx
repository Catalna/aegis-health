import { useCallback, useEffect, useState } from 'react'
import { mlApi } from '../api'
import { humanizeText } from '../humanLanguage'

const TYPE_LABELS = {
  upcoding: 'Tingkat keparahan tidak sesuai',
  cloning: 'Kemiripan antar klaim',
  repeat_billing: 'Pengulangan tagihan',
  phantom_billing: 'Tindakan tidak terbukti',
  prolonged_los: 'Lama rawat tidak biasa',
  inflated_bill: 'Biaya tidak wajar',
  unbundling: 'Pemisahan tagihan',
}

const formatNumber = (value) => Number(value || 0).toLocaleString('id-ID')

const measuredValue = (metric, formatter = (value) => `${(value * 100).toFixed(1)}%`) => (
  metric?.status === 'measured' ? formatter(metric.value) : 'Belum dapat dihitung'
)

const deltaValue = (metric) => {
  if (typeof metric === 'number') {
    return `${metric >= 0 ? '+' : ''}${(metric * 100).toFixed(2)} poin`
  }
  return 'Belum dapat dihitung'
}

function MetricCell({ metric, formatter }) {
  if (metric?.status !== 'measured') {
    return <span className="evaluation-unavailable">{humanizeText(metric?.reason) || 'Belum dapat dihitung'}</span>
  }
  return <strong>{formatter ? formatter(metric.value) : `${(metric.value * 100).toFixed(1)}%`}</strong>
}

function LoadingState() {
  return (
    <div className="status-message" aria-live="polite">
       <strong>Menyiapkan ringkasan penilaian sistem</strong>
       <p>Mengambil hasil pemeriksaan ketepatan penentuan prioritas.</p>
    </div>
  )
}

function ErrorState({ message, onRetry, retrying }) {
  return (
    <div className="status-message error" role="alert">
      <strong>Ringkasan penilaian belum dapat dimuat</strong>
      <p>{message}</p>
      <button type="button" className="btn btn-outline" onClick={onRetry} disabled={retrying} aria-busy={retrying}>
        {retrying ? 'Mencoba kembali...' : 'Coba lagi'}
      </button>
    </div>
  )
}

export default function MLEvaluation() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [retrying, setRetrying] = useState(false)
  const [error, setError] = useState(null)

  const loadEvaluation = useCallback(async (isRetry = false) => {
    if (isRetry) setRetrying(true)
    else setLoading(true)
    setError(null)
    try {
      const response = await mlApi.p1Evaluation()
      setData(response.data)
    } catch (err) {
      if (err?.response?.status === 404) {
        setError('Ringkasan penilaian belum tersedia. Minta administrator memperbarui data penilaian sistem.')
      } else {
        setError('Periksa koneksi backend, lalu coba lagi.')
      }
    } finally {
      setLoading(false)
      setRetrying(false)
    }
  }, [])

  useEffect(() => {
    loadEvaluation()
  }, [loadEvaluation])

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={() => loadEvaluation(true)} retrying={retrying} />
  if (!data?.metrics) return <ErrorState message="Ringkasan penilaian tidak memiliki data yang dapat ditampilkan." onRetry={() => loadEvaluation(true)} retrying={retrying} />

  const metrics = data.metrics
  const candidate = data.ablation?.find(item => item.config_version === 'behavioral-context-candidate')
  const slices = Object.entries(metrics.by_anomaly_type || {})
  const hasErrors = (data.errors || []).length > 0
  const profile = data.dataset?.profile || 'standard'

  return (
    <div className="evaluation-page">
      <header className="evaluation-header">
        <div>
          <div className="page-kicker">Penilaian kualitas sistem</div>
          <h1 className="evaluation-title">Ketepatan Penentuan Prioritas</h1>
          <p>Ringkasan seberapa tepat sistem menempatkan klaim yang perlu perhatian lebih dahulu berdasarkan data uji.</p>
        </div>
        <button type="button" className="btn btn-outline" onClick={() => loadEvaluation(true)} disabled={retrying} aria-busy={retrying}>
          {retrying ? 'Memuat...' : 'Muat ulang'}
        </button>
      </header>

      {hasErrors && (
        <div className="evaluation-notice warning" role="status">
          Sebagian klaim gagal dinilai. Metrik hanya dihitung dari baris yang berhasil dan daftar error tersedia di artifact.
        </div>
      )}

      <section className="evaluation-hero" aria-labelledby="evaluation-headline">
        <div>
          <p className="evaluation-label">Ketepatan rata-rata urutan</p>
          <h2 id="evaluation-headline">{measuredValue(metrics.average_precision)}</h2>
          <p className="evaluation-note">Mengukur kualitas urutan prioritas, bukan kepastian bahwa suatu klaim bermasalah.</p>
        </div>
        <dl className="evaluation-facts">
           <div><dt>Jenis data uji</dt><dd>{profile === 'standard' ? 'Data standar' : humanizeText(profile)}</dd></div>
           <div><dt>Jumlah klaim uji</dt><dd>{formatNumber(data.dataset?.counts ? Object.values(data.dataset.counts).reduce((sum, count) => sum + count, 0) : 0)} klaim</dd></div>
           <div><dt>Nomor pengulangan</dt><dd>{data.dataset?.seed ?? '-'}</dd></div>
           <div><dt>Waktu tanggap terlama</dt><dd>{metrics.latency?.p95_ms != null ? `${metrics.latency.p95_ms.toFixed(1).replace('.', ',')} milidetik` : 'Belum tersedia'}</dd></div>
        </dl>
      </section>

      <div className="evaluation-grid">
        <section className="card" aria-labelledby="ranking-title">
           <h3 id="ranking-title" className="card-title">Ukuran Ketepatan Urutan</h3>
          <div className="table-container">
            <table className="evaluation-table">
              <caption className="sr-only">Metrik ranking pada data holdout</caption>
              <thead><tr><th scope="col">Metrik</th><th scope="col">Hasil</th><th scope="col">Keterangan</th></tr></thead>
              <tbody>
                 <tr><th scope="row">Ketepatan 50 prioritas teratas</th><td><MetricCell metric={metrics.precision_at_k?.['50']} /></td><td>Bagian dari 50 klaim teratas yang memang perlu perhatian</td></tr>
                 <tr><th scope="row">Cakupan 50 prioritas teratas</th><td><MetricCell metric={metrics.recall_at_k?.['50']} /></td><td>Bagian dari seluruh klaim penting yang berhasil masuk 50 teratas</td></tr>
                 <tr><th scope="row">Ketepatan rata-rata urutan</th><td><MetricCell metric={metrics.average_precision} /></td><td>Ketepatan urutan secara keseluruhan</td></tr>
                 <tr><th scope="row">Waktu tanggap (median / terlama)</th><td><strong>{metrics.latency?.p50_ms?.toFixed(1) ?? '-'} / {metrics.latency?.p95_ms?.toFixed(1) ?? '-'} milidetik</strong></td><td>{metrics.latency?.count || 0} klaim berhasil dinilai</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section className="card" aria-labelledby="ablation-title">
           <h3 id="ablation-title" className="card-title">Perbandingan Tambahan</h3>
           <p className="evaluation-copy">Catatan pola perilaku diuji sebagai perbandingan dan belum mengubah penilaian utama.</p>
          <div className="ablation-result">
             <span>Perubahan ketepatan rata-rata</span>
            <strong>{deltaValue(candidate?.delta_vs_p0_core?.average_precision)}</strong>
          </div>
          <dl className="evaluation-detail-list">
             <div><dt>Perubahan ketepatan 50 teratas</dt><dd>{deltaValue(candidate?.delta_vs_p0_core?.precision_at_k?.['50'])}</dd></div>
             <div><dt>Perubahan cakupan 50 teratas</dt><dd>{deltaValue(candidate?.delta_vs_p0_core?.recall_at_k?.['50'])}</dd></div>
          </dl>
        </section>
      </div>

      <section className="card" aria-labelledby="slice-title">
        <div className="section-heading-row">
          <div>
             <h3 id="slice-title" className="card-title">Hasil Berdasarkan Jenis Temuan</h3>
             <p className="evaluation-copy">Temuan terlewat adalah klaim penting yang tidak masuk 50 prioritas teratas.</p>
          </div>
          <span className="badge badge-neutral">{slices.length} jenis</span>
        </div>
        {slices.length === 0 ? (
           <p className="evaluation-empty">Belum ada jenis temuan yang dapat dihitung.</p>
        ) : (
          <div className="table-container">
            <table className="evaluation-table evaluation-table-wide">
               <caption className="sr-only">Metrik per jenis temuan</caption>
               <thead><tr><th scope="col">Jenis</th><th scope="col">Jumlah temuan</th><th scope="col">Masuk 50 teratas</th><th scope="col">Temuan terlewat</th><th scope="col">Rentang nilai</th></tr></thead>
              <tbody>
                {slices.map(([type, slice]) => (
                  <tr key={type}>
                    <th scope="row">{TYPE_LABELS[type] || 'Jenis temuan lainnya'}</th>
                    <td>{slice.positive_count}</td>
                    <td>{slice.top_k_hits?.['50'] ?? '-'}</td>
                    <td>{slice.false_negative_at_k?.['50'] ?? '-'}</td>
                    <td>{slice.score_distribution ? `${slice.score_distribution.min.toFixed(1)} – ${slice.score_distribution.max.toFixed(1)}` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="evaluation-notice" aria-labelledby="limitations-title">
        <h3 id="limitations-title">Batasan interpretasi</h3>
        <ul>
           {(data.limitations || ['Data contoh belum menggantikan pengujian di lapangan']).map(limitation => <li key={limitation}>{humanizeText(limitation)}</li>)}
           <li>Data uji berisi contoh yang sengaja dibuat menantang agar penilaian tidak terlihat terlalu mudah.</li>
        </ul>
      </section>
    </div>
  )
}
