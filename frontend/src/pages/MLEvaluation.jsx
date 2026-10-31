import { useCallback, useEffect, useState } from 'react'
import {
  Brain,
  Gauge,
  Crosshair,
  ListChecks,
  Timer,
  Layers,
  FlaskConical,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Info,
} from 'lucide-react'
import { mlApi } from '../api'
import { humanizeText } from '../humanLanguage'
import DataFreshness from '../DataFreshness'

const TYPE_LABELS = {
  upcoding: 'Tingkat keparahan tidak sesuai',
  cloning: 'Kemiripan antar klaim',
  repeat_billing: 'Pengulangan tagihan',
  phantom_billing: 'Tindakan tidak terbukti',
  prolonged_los: 'Lama rawat tidak biasa',
  inflated_bill: 'Biaya tidak wajar',
  unbundling: 'Pemisahan tagihan',
}

const PROFILE_LABELS = {
  standard: 'Data standar',
  challenge: 'Data menantang',
}

const formatNumber = (value) => Number(value || 0).toLocaleString('id-ID')

const formatDecimal = (value, digits = 1) =>
  Number(value || 0).toFixed(digits).replace('.', ',')

const asPercent = (metric) => (
  metric?.status === 'measured' ? metric.value * 100 : null
)

const deltaValue = (metric) => {
  if (typeof metric === 'number') {
    return `${metric >= 0 ? '+' : ''}${(metric * 100).toFixed(2).replace('.', ',')} poin`
  }
  return 'Belum dapat dihitung'
}

// Angka mengalir dari nol saat kartu pertama kali muncul. Target yang sama
// tidak mengulang animasi supaya refresh tidak membuat kedip.
function useCountUp(target, duration = 700) {
  const [display, setDisplay] = useState(0)
  useEffect(() => {
    if (display === target) return undefined
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setDisplay(target)
      return undefined
    }
    const from = display
    const start = performance.now()
    let raf
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setDisplay(from + (target - from) * eased)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
    // display sengaja tidak masuk deps — restart tiap frame dihindari
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration])
  return display
}

function StatValue({ value, decimals = 0, suffix = '' }) {
  const display = useCountUp(value ?? 0)
  return (
    <>
      {decimals > 0
        ? formatDecimal(display, decimals)
        : Math.round(display).toLocaleString('id-ID')}
      {suffix}
    </>
  )
}

function MetricValue({ metric, decimals = 1, suffix = '%' }) {
  const percent = asPercent(metric)
  if (percent == null) {
    return <span className="eval-value-muted">{humanizeText(metric?.reason) || 'Belum dapat dihitung'}</span>
  }
  return <StatValue value={percent} decimals={decimals} suffix={suffix} />
}

function LoadingState() {
  return (
    <div className="dashboard-container">
      <div className="status-message loading-state" role="status" aria-live="polite">
        <span className="loading-spinner" aria-hidden="true" />
        <strong>Menyiapkan ringkasan penilaian sistem</strong>
        <p>Mengambil hasil pemeriksaan ketepatan penentuan prioritas.</p>
      </div>
    </div>
  )
}

function ErrorState({ message, onRetry, retrying }) {
  return (
    <div className="dashboard-container">
      <div className="status-message error" role="alert">
        <strong>Ringkasan penilaian belum dapat dimuat</strong>
        <p>{message}</p>
        <button type="button" className="btn btn-outline" onClick={onRetry} disabled={retrying} aria-busy={retrying}>
          {retrying ? 'Mencoba kembali...' : 'Coba lagi'}
        </button>
      </div>
    </div>
  )
}

export default function MLEvaluation() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [retrying, setRetrying] = useState(false)
  const [error, setError] = useState(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null)
  const [now, setNow] = useState(() => Date.now())

  const loadEvaluation = useCallback(async (isRetry = false) => {
    if (isRetry) setRetrying(true)
    else setLoading(true)
    setError(null)
    try {
      const response = await mlApi.p1Evaluation()
      setData(response.data)
      setLastUpdatedAt(Date.now())
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

  useEffect(() => {
    const ticker = setInterval(() => setNow(Date.now()), 5000)
    return () => clearInterval(ticker)
  }, [])

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={() => loadEvaluation(true)} retrying={retrying} />
  if (!data?.metrics) return <ErrorState message="Ringkasan penilaian tidak memiliki data yang dapat ditampilkan." onRetry={() => loadEvaluation(true)} retrying={retrying} />

  const metrics = data.metrics
  const candidate = data.ablation?.find(item => item.config_version === 'behavioral-context-candidate')
  const slices = Object.entries(metrics.by_anomaly_type || {})
  const hasErrors = (data.errors || []).length > 0
  const profile = data.dataset?.profile || 'standard'
  const profileLabel = PROFILE_LABELS[profile] || humanizeText(profile)
  const claimCount = data.dataset?.counts
    ? Object.values(data.dataset.counts).reduce((sum, count) => sum + count, 0)
    : 0
  const mainDelta = candidate?.delta_vs_p0_core?.average_precision
  const mainDeltaPositive = typeof mainDelta === 'number' && mainDelta >= 0

  const statCards = [
    {
      label: 'Ketepatan Rata-rata',
      value: asPercent(metrics.average_precision),
      decimals: 1,
      suffix: '%',
      sub: 'Kualitas urutan prioritas keseluruhan',
      icon: <Gauge size={22} />,
      tone: 'tone-green',
      accent: 'stat-accent-green',
      meta: null,
    },
    {
      label: 'Ketepatan 50 Teratas',
      value: asPercent(metrics.precision_at_k?.['50']),
      decimals: 1,
      suffix: '%',
      sub: 'Dari 50 klaim teratas yang perlu perhatian',
      icon: <Crosshair size={22} />,
      tone: 'tone-blue',
      accent: 'stat-accent-blue',
      meta: null,
    },
    {
      label: 'Cakupan 50 Teratas',
      value: asPercent(metrics.recall_at_k?.['50']),
      decimals: 1,
      suffix: '%',
      sub: 'Klaim penting yang berhasil masuk 50 teratas',
      icon: <ListChecks size={22} />,
      tone: 'tone-violet',
      accent: 'stat-accent-violet',
      meta: null,
    },
    {
      label: 'Klaim Uji',
      value: claimCount,
      decimals: 0,
      suffix: '',
      sub: profileLabel,
      icon: <Layers size={22} />,
      tone: 'tone-slate',
      accent: 'stat-accent-slate',
      meta: `ulangan ${data.dataset?.seed ?? '-'}`,
    },
  ]

  const rankingRows = [
    {
      name: 'Ketepatan 50 prioritas teratas',
      detail: 'Bagian dari 50 klaim teratas yang memang perlu perhatian',
      metric: metrics.precision_at_k?.['50'],
    },
    {
      name: 'Cakupan 50 prioritas teratas',
      detail: 'Bagian dari seluruh klaim penting yang berhasil masuk 50 teratas',
      metric: metrics.recall_at_k?.['50'],
    },
    {
      name: 'Ketepatan rata-rata urutan',
      detail: 'Ketepatan urutan secara keseluruhan',
      metric: metrics.average_precision,
    },
  ]

  return (
    <div className="dashboard-container">
      <header className="dashboard-header page-topbar">
        <div>
          <div className="dashboard-title-row">
            <div className="header-icon-badge">
              <Brain size={20} />
            </div>
            <h1 className="evaluation-title">Ketepatan Penentuan Prioritas</h1>
          </div>
          <p className="dashboard-subtitle">
            Ringkasan seberapa tepat sistem menempatkan klaim yang perlu perhatian lebih dahulu berdasarkan data uji.
          </p>
        </div>
        <DataFreshness
          label="Data penilaian"
          lastUpdatedAt={lastUpdatedAt}
          now={now}
          onRefresh={() => loadEvaluation(true)}
          refreshing={retrying}
        />
      </header>

      {hasErrors && (
        <div className="alert-disclaimer mb-3" role="status">
          <strong>Sebagian klaim gagal dinilai</strong>
          <p>Metrik hanya dihitung dari baris yang berhasil. Rincian error tersedia di artifact penilaian.</p>
        </div>
      )}

      <section className="metric-cards-grid mb-3" aria-label="Ringkasan ketepatan">
        {statCards.map((card) => (
          <div className={`card stat-card ${card.accent}`} key={card.label}>
            <div className="stat-head">
              <span className="stat-card-label">{card.label}</span>
              <div className={`stat-icon ${card.tone}`}>{card.icon}</div>
            </div>
            <div className="stat-card-value">
              {card.value == null ? (
                <span className="eval-value-muted">Belum dapat dihitung</span>
              ) : (
                <StatValue value={card.value} decimals={card.decimals} suffix={card.suffix} />
              )}
            </div>
            <div className="stat-bottom">
              <span className="stat-card-sub">{card.sub}</span>
              {card.meta && <span className="mon-stat-meta">{card.meta}</span>}
            </div>
          </div>
        ))}
      </section>

      <div className="mon-pair-grid">
        <section className="card dash-accent" aria-labelledby="evaluation-headline">
          <div className="chart-head-row chart-head-between">
            <div className="chart-head-left">
              <span className="chart-panel-icon" aria-hidden="true"><Gauge size={16} /></span>
              <div>
                <h2 id="evaluation-headline" className="chart-title">Ukuran Ketepatan Urutan</h2>
                <p className="chart-subtitle">Dihitung pada data uji yang tidak dipakai saat pelatihan</p>
              </div>
            </div>
            <span className="badge badge-neutral">Data uji</span>
          </div>

          <ul className="eval-list">
            {rankingRows.map((row) => (
              <li className="eval-row" key={row.name}>
                <span className="eval-row-body">
                  <span className="eval-row-name">{row.name}</span>
                  <span className="eval-row-detail">{row.detail}</span>
                </span>
                <span className="eval-row-value">
                  <MetricValue metric={row.metric} />
                </span>
              </li>
            ))}
            <li className="eval-row">
              <span className="eval-row-body">
                <span className="eval-row-name">Waktu tanggap</span>
                <span className="eval-row-detail">Median dan waktu terlama saat menilai satu klaim</span>
              </span>
              <span className="eval-row-value eval-row-value-inline">
                <Timer size={15} aria-hidden="true" />
                {metrics.latency?.p50_ms != null
                  ? `${formatDecimal(metrics.latency.p50_ms)} / ${formatDecimal(metrics.latency.p95_ms)} ms`
                  : 'Belum tersedia'}
              </span>
            </li>
          </ul>

          <p className="eval-footnote">
            {formatNumber(metrics.latency?.count)} klaim berhasil dinilai. Waktu tanggap diukur tanpa pemanggilan model bahasa.
          </p>
        </section>

        <section className="card dash-accent" aria-labelledby="ablation-title">
          <div className="chart-head-row chart-head-between">
            <div className="chart-head-left">
              <span className="chart-panel-icon" aria-hidden="true"><FlaskConical size={16} /></span>
              <div>
                <h2 className="chart-title" id="ablation-title">Perbandingan Tambahan</h2>
                <p className="chart-subtitle">Catatan pola perilaku diuji sebagai pembanding, belum mengubah penilaian utama</p>
              </div>
            </div>
          </div>

          <div className={`eval-delta ${mainDeltaPositive ? 'pos' : 'neg'}`}>
            <span className="eval-delta-icon" aria-hidden="true">
              {mainDeltaPositive ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}
            </span>
            <span className="eval-delta-body">
              <span className="eval-delta-label">Perubahan ketepatan rata-rata</span>
              <span className="eval-delta-value">{deltaValue(mainDelta)}</span>
            </span>
          </div>

          <ul className="eval-list">
            <li className="eval-row">
              <span className="eval-row-body">
                <span className="eval-row-name">Ketepatan 50 teratas</span>
              </span>
              <span className={`eval-row-value ${typeof candidate?.delta_vs_p0_core?.precision_at_k?.['50'] === 'number' && candidate.delta_vs_p0_core.precision_at_k['50'] >= 0 ? 'pos' : 'neg'}`}>
                {deltaValue(candidate?.delta_vs_p0_core?.precision_at_k?.['50'])}
              </span>
            </li>
            <li className="eval-row">
              <span className="eval-row-body">
                <span className="eval-row-name">Cakupan 50 teratas</span>
              </span>
              <span className={`eval-row-value ${typeof candidate?.delta_vs_p0_core?.recall_at_k?.['50'] === 'number' && candidate.delta_vs_p0_core.recall_at_k['50'] >= 0 ? 'pos' : 'neg'}`}>
                {deltaValue(candidate?.delta_vs_p0_core?.recall_at_k?.['50'])}
              </span>
            </li>
          </ul>

          <p className="eval-footnote">
            Pembanding hanya untuk melihat dampak catatan pola perilaku. Angka utama tetap memakai konfigurasi inti.
          </p>
        </section>
      </div>

      <section className="card dash-accent mb-3" aria-labelledby="slice-title">
        <div className="chart-head-row chart-head-between">
          <div className="chart-head-left">
            <span className="chart-panel-icon" aria-hidden="true"><Layers size={16} /></span>
            <div>
              <h2 className="chart-title" id="slice-title">Hasil Berdasarkan Jenis Temuan</h2>
              <p className="chart-subtitle">Temuan terlewat adalah klaim penting yang tidak masuk 50 prioritas teratas</p>
            </div>
          </div>
          <span className="badge badge-neutral">{slices.length} jenis</span>
        </div>

        {slices.length === 0 ? (
          <p className="eval-footnote">Belum ada jenis temuan yang dapat dihitung.</p>
        ) : (
          <div className="table-container">
            <table className="eval-table">
              <caption className="sr-only">Metrik per jenis temuan</caption>
              <thead>
                <tr>
                  <th scope="col">Jenis temuan</th>
                  <th scope="col" className="num">Jumlah</th>
                  <th scope="col" className="num">Masuk 50 teratas</th>
                  <th scope="col" className="num">Terlewat</th>
                  <th scope="col" className="num">Rentang nilai</th>
                </tr>
              </thead>
              <tbody>
                {slices.map(([type, slice]) => {
                  const missed = slice.false_negative_at_k?.['50']
                  return (
                    <tr key={type}>
                      <th scope="row">{TYPE_LABELS[type] || 'Jenis temuan lainnya'}</th>
                      <td className="num">{slice.positive_count}</td>
                      <td className="num">{slice.top_k_hits?.['50'] ?? '-'}</td>
                      <td className="num">
                        <span className={missed ? 'eval-missed' : 'eval-clean'}>
                          {missed ?? '-'}
                        </span>
                      </td>
                      <td className="num eval-range">
                        {slice.score_distribution
                          ? `${formatDecimal(slice.score_distribution.min)} – ${formatDecimal(slice.score_distribution.max)}`
                          : '-'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card dash-accent eval-limits" aria-labelledby="limitations-title">
        <div className="chart-head-row">
          <div className="chart-head-left">
            <span className="chart-panel-icon" aria-hidden="true"><Info size={16} /></span>
            <div>
              <h2 className="chart-title" id="limitations-title">Batasan Interpretasi</h2>
              <p className="chart-subtitle">Hal yang perlu dipertimbangkan saat membaca angka di atas</p>
            </div>
          </div>
        </div>
        <ul className="eval-limit-list">
          {(data.limitations || ['Data contoh belum menggantikan pengujian di lapangan']).map(limitation => (
            <li key={limitation}>
              <AlertTriangle size={14} aria-hidden="true" />
              <span>{humanizeText(limitation)}</span>
            </li>
          ))}
          <li>
            <AlertTriangle size={14} aria-hidden="true" />
            <span>Data uji berisi contoh yang sengaja dibuat menantang agar penilaian tidak terlihat terlalu mudah.</span>
          </li>
        </ul>
      </section>
    </div>
  )
}
