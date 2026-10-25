import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Activity,
  Database,
  Cpu,
  Boxes,
  Network,
  Bot,
  TrendingDown,
  FileText,
  CheckCircle2,
  ShieldAlert,
  BadgeCheck,
  HeartPulse,
  Workflow,
} from 'lucide-react'
import { analyticsApi, healthApi } from '../api'
import DataFreshness from '../DataFreshness'
import { MonitoringSkeleton } from '../Skeleton'
import QueueSummary from '../QueueSummary'
import { fetchQueueSummary } from '../queueSummaryData'
import { SERVICE_LABELS } from '../humanLanguage'

const COMPONENT_ICONS = {
  database: <Database size={16} />,
  llm_ollama: <Bot size={16} />,
  ml_financial: <Cpu size={16} />,
  ml_isolation_forest: <Cpu size={16} />,
  vector_store: <Boxes size={16} />,
  graph_metrics: <Network size={16} />,
  queue_worker: <Activity size={16} />,
}

const COMPONENT_LABELS = SERVICE_LABELS

const AGENT_INFO = [
  { label: 'Pemeriksaan Medis', key: 'llm_ollama', detail: 'Membaca diagnosis dan tindakan' },
  { label: 'Pemeriksaan Biaya', key: 'ml_financial', detail: 'Membandingkan biaya dengan pembanding' },
  { label: 'Pemeriksaan Pola Klaim', key: 'vector_store', detail: 'Mencari kemiripan klaim sebelumnya' },
  { label: 'Perangkuman Temuan', key: 'llm_ollama', detail: 'Menyatukan temuan tiap pemeriksaan' },
  { label: 'Penentuan Prioritas', key: 'database', detail: 'Menghitung skor dan tingkat risiko' },
  { label: 'Penjelasan Hasil', key: 'llm_ollama', detail: 'Menulis alasan dalam bahasa manusia' },
]

const formatRp = (value) => `Rp ${(value || 0).toLocaleString('id-ID')}`

// Angka mengalir ke target baru dengan ease-out kubik. Target yang sama tidak
// mengulang animasi, jadi auto-refresh tiap 5 detik tidak membuat kedip.
function useCountUp(target, duration = 640) {
  const [display, setDisplay] = useState(target)
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
      setDisplay(Math.round(from + (target - from) * eased))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
    // display sengaja tidak masuk deps — restart tiap frame dihindari
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration])
  return display
}

export default function Monitoring() {
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [queueSummary, setQueueSummary] = useState(null)
  const [queueError, setQueueError] = useState(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null)
  const [currentTime, setCurrentTime] = useState(Date.now())
  const [refreshing, setRefreshing] = useState(false)
  const [partialData, setPartialData] = useState(false)
  const [analyticsError, setAnalyticsError] = useState(false)
  const [healthError, setHealthError] = useState(false)
  const requestGenerationRef = useRef(0)
  const abortControllerRef = useRef(null)
  const inFlightRef = useRef(false)

  const fetchAll = useCallback(async ({ manual = false } = {}) => {
      // Tick otomatis dilewati kalau permintaan sebelumnya belum selesai,
      // supaya request lambat tidak terus dibatalkan dan halaman tidak
      // berhenti di skeleton selamanya.
      if (inFlightRef.current && !manual) return
      const generation = ++requestGenerationRef.current
      abortControllerRef.current?.abort()
      const controller = new AbortController()
      abortControllerRef.current = controller
      inFlightRef.current = true
      // Hanya klik pengguna yang menampilkan status "sedang diperbarui".
      // Auto-refresh tiap 5 detik tidak boleh membuat pill berkedip "Memuat".
      if (manual) setRefreshing(true)
      try {
        const [statsRes, healthRes, queueRes] = await Promise.allSettled([
          analyticsApi.dashboard({ signal: controller.signal }),
          healthApi.check({ signal: controller.signal }),
          fetchQueueSummary({ signal: controller.signal }),
        ])
        if (generation !== requestGenerationRef.current) return
        if (statsRes.status === 'fulfilled') {
          setStats(statsRes.value.data)
          setAnalyticsError(false)
        } else {
          setAnalyticsError(true)
        }
        if (healthRes.status === 'fulfilled') {
          setHealth(healthRes.value.data)
          setHealthError(false)
        } else {
          setHealthError(true)
        }
        if (queueRes.status === 'fulfilled') {
          setQueueSummary(queueRes.value)
          setQueueError(null)
        } else {
          setQueueError('Ringkasan antrean belum dapat dimuat.')
        }
        const completeRefresh = statsRes.status === 'fulfilled' && healthRes.status === 'fulfilled' && queueRes.status === 'fulfilled'
        setPartialData(!completeRefresh)
        if (completeRefresh) setLastUpdatedAt(Date.now())
        setLoading(false)
      } finally {
        if (generation === requestGenerationRef.current) {
          inFlightRef.current = false
          setRefreshing(false)
        }
      }
  }, [])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 5000)
    const clock = setInterval(() => setCurrentTime(Date.now()), 5000)
    return () => {
      clearInterval(interval)
      clearInterval(clock)
      abortControllerRef.current?.abort()
      requestGenerationRef.current += 1
      inFlightRef.current = false
    }
  }, [fetchAll])

  // Semua hook wajib dipanggil sebelum early-return apa pun.
  const animTotal = useCountUp(stats?.total_claims ?? 0)
  const animProcessed = useCountUp(stats?.processed_claims ?? 0)
  const animHighRisk = useCountUp(stats?.high_risk_claims ?? 0)
  const animVerified = useCountUp(stats?.verified_claims ?? 0)
  const animExposure = useCountUp(stats?.potential_financial_exposure ?? 0)

  const statusBadgeColors = (s) => s === 'ok'
    ? { background: 'var(--risk-low-bg)', color: 'var(--accent-green)' }
    : s === 'warn' || s === 'degraded'
      ? { background: 'var(--risk-medium-bg)', color: 'var(--warning-text)' }
      : { background: 'var(--risk-high-bg)', color: 'var(--error-text)' }
  const statusTextColor = (s) => s === 'ok' ? 'var(--success)' : s === 'warn' || s === 'degraded' ? 'var(--warning-text)' : 'var(--error-text)'
  const statusText = (s) => s === 'ok' ? 'Sehat' : s === 'warn' || s === 'degraded' ? 'Perlu perhatian' : 'Gangguan'
  const detailText = (key, comp) => comp?.status === 'ok'
    ? ({
        database: 'Penyimpanan data tersedia',
        llm_ollama: 'Pemeriksaan tambahan tersedia',
        ml_financial: 'Pemeriksaan biaya tersedia',
        ml_isolation_forest: 'Pemeriksaan pola tersedia',
        vector_store: 'Data pembanding tersedia',
        graph_metrics: 'Data fasilitas kesehatan tersedia',
        queue_worker: 'Antrean pemeriksaan aktif',
      }[key] || 'Layanan tersedia')
    : 'Layanan perlu diperiksa'

  const healthStatus = healthError ? 'error' : health?.status
  const statusLabel = health ? statusText(healthStatus) : 'Sedang memeriksa layanan'

  const pageHeader = (
    <header className="dashboard-header page-topbar">
      <div>
        <div className="dashboard-title-row">
          <div className="header-icon-badge">
            <Activity size={20} />
          </div>
          <h1>Pemantauan Sistem</h1>
        </div>
        <p className="dashboard-subtitle">
          Status layanan diperbarui otomatis tiap 5 detik. Kondisi saat ini:{' '}
          <span className="monitoring-live-status" role="status" aria-live="polite" aria-atomic="true">
            <strong style={{ color: health ? statusTextColor(healthStatus) : 'var(--text-muted)' }}>{statusLabel}</strong>
          </span>
        </p>
      </div>
      <DataFreshness
        label="Data monitoring"
        lastUpdatedAt={lastUpdatedAt}
        now={currentTime}
        onRefresh={() => fetchAll({ manual: true })}
        refreshing={refreshing}
        partial={partialData}
        error={analyticsError || healthError || Boolean(queueError)}
      />
    </header>
  )

  if (loading) {
    return (
      <div className="dashboard-container">
        {pageHeader}
        <MonitoringSkeleton />
      </div>
    )
  }

  const totalClaims = stats?.total_claims ?? 0
  const pctOfTotal = (value) => totalClaims > 0 ? Math.round(((value || 0) / totalClaims) * 100) : 0

  const statCards = [
    {
      label: 'Total Klaim',
      value: animTotal,
      sub: 'Seluruh berkas masuk',
      icon: <FileText size={22} />,
      tone: 'tone-slate',
      accent: 'stat-accent-slate',
      meta: null,
    },
    {
      label: 'Pemeriksaan Selesai',
      value: animProcessed,
      sub: 'Analisis risiko rampung',
      icon: <CheckCircle2 size={22} />,
      tone: 'tone-green',
      accent: 'stat-accent-green',
      meta: pctOfTotal(stats?.processed_claims),
    },
    {
      label: 'Risiko Tinggi',
      value: animHighRisk,
      sub: 'Perlu prioritas verifikasi',
      icon: <ShieldAlert size={22} />,
      tone: 'tone-red',
      accent: 'stat-accent-red',
      meta: pctOfTotal(stats?.high_risk_claims),
    },
    {
      label: 'Sudah Diputuskan',
      value: animVerified,
      sub: 'Keputusan petugas tercatat',
      icon: <BadgeCheck size={22} />,
      tone: 'tone-green',
      accent: 'stat-accent-green',
      meta: pctOfTotal(stats?.verified_claims),
    },
  ]

  const components = Object.entries(health?.components || {})
  const healthyCount = components.filter(([, comp]) => comp.status === 'ok').length
  const allHealthy = components.length > 0 && healthyCount === components.length

  return (
    <div className="dashboard-container">
      {pageHeader}

      <div className="monitoring-analytics-state" role="alert" aria-live="assertive" aria-atomic="true">
        {analyticsError && (
          <div className="alert-disclaimer mb-3">
            <strong>{stats ? 'Data analitik usang' : 'Data analitik gagal dimuat'}</strong>
            <p>{stats ? 'Menampilkan angka terakhir yang berhasil dimuat.' : 'Metrik belum tersedia; angka tidak ditampilkan sebagai nol.'}</p>
            <button className="btn btn-ghost" onClick={() => fetchAll({ manual: true })}>Coba lagi</button>
          </div>
        )}
      </div>

      {/* 4 kartu metrik — pola sama dengan Dashboard Utama */}
      <section className="metric-cards-grid mb-3">
        {statCards.map((card) => (
          <div className={`card stat-card ${card.accent}`} key={card.label}>
            <div className="stat-head">
              <span className="stat-card-label">{card.label}</span>
              <div className={`stat-icon ${card.tone}`}>{card.icon}</div>
            </div>
            <div className="stat-card-value">{card.value.toLocaleString('id-ID')}</div>
            <div className="stat-bottom">
              <span className="stat-card-sub">{card.sub}</span>
              {card.meta != null && (
                <span className="mon-stat-meta"><strong>{card.meta}%</strong> dari total</span>
              )}
            </div>
          </div>
        ))}
      </section>

      {queueSummary && <QueueSummary summary={queueSummary} now={currentTime} />}

      <div className="monitoring-queue-state" role="alert" aria-live="assertive" aria-atomic="true">
        {queueError && (
          <div className="alert-disclaimer mb-3">
            {queueError} <button className="btn btn-ghost" onClick={() => fetchAll({ manual: true })}>Muat ulang</button>
          </div>
        )}
      </div>

      {/* Perkiraan selisih biaya */}
      <section className="card dash-accent mb-3 mon-exposure" aria-labelledby="exposure-title">
        <div className="chart-head-row chart-head-between">
          <div className="chart-head-left">
            <span className="chart-panel-icon" aria-hidden="true"><TrendingDown size={16} /></span>
            <div>
              <h3 className="chart-title" id="exposure-title">Perkiraan Selisih Biaya</h3>
              <p className="chart-subtitle">Selisih biaya pengajuan terhadap batas atas biaya pembanding</p>
            </div>
          </div>
          <span className="badge badge-neutral">Estimasi</span>
        </div>
        <div className="mon-exposure-value">{formatRp(animExposure)}</div>
        <p className="mon-exposure-note">
          Dihitung dari klaim berprioritas tinggi atau sedang. Angka ini bukan nilai akhir setelah keputusan petugas.
        </p>
      </section>

      {/* Kondisi layanan + tahapan — dua daftar berdampingan supaya tidak
          menyisakan rongga kosong selebar kartu. */}
      <div className="mon-pair-grid">
      <section className="card dash-accent" aria-labelledby="health-title">
        <div className="chart-head-row chart-head-between">
          <div className="chart-head-left">
            <span className="chart-panel-icon" aria-hidden="true"><HeartPulse size={16} /></span>
            <div>
              <h3 className="chart-title" id="health-title">Kondisi Layanan</h3>
              <p className="chart-subtitle">Pemeriksaan langsung ke setiap komponen sistem</p>
            </div>
          </div>
          <span className={`mon-health-score ${allHealthy ? 'ok' : 'warn'}`}>
            {components.length === 0 ? 'Belum ada data' : `${healthyCount} dari ${components.length} sehat`}
          </span>
        </div>

        {components.length > 0 && (
          <div
            className="mon-health-bar"
            role="img"
            aria-label={`${healthyCount} dari ${components.length} layanan dalam kondisi sehat`}
          >
            {components.map(([key, comp]) => (
              <span
                key={key}
                className={`mon-health-seg ${comp.status === 'ok' ? 'ok' : comp.status === 'error' ? 'error' : 'warn'}`}
              />
            ))}
          </div>
        )}

        <ul className="mon-health-list">
          {components.map(([key, comp]) => (
            <li className="mon-health-row" key={key}>
              <span
                className="mon-health-icon"
                style={{
                  background: comp.status === 'ok' ? 'var(--risk-low-bg)' : comp.status === 'error' ? 'var(--risk-high-bg)' : 'var(--risk-medium-bg)',
                  color: statusTextColor(comp.status),
                }}
                aria-hidden="true"
              >
                {COMPONENT_ICONS[key] || <Cpu size={16} />}
              </span>
              <span className="mon-health-body">
                <span className="mon-health-name">{COMPONENT_LABELS[key] || 'Layanan pemeriksaan'}</span>
                <span className="mon-health-detail">{detailText(key, comp)}</span>
              </span>
              <span className="badge" style={statusBadgeColors(comp.status)}>
                {statusText(comp.status)}
              </span>
            </li>
          ))}
        </ul>

        <div className="monitoring-health-state" role="alert" aria-live="assertive" aria-atomic="true">
          {healthError && (
            <>
              <div className="text-sm" style={{ color: 'var(--error-text)' }}>Layanan pemeriksaan belum dapat dihubungi.</div>
              <button className="btn btn-ghost" onClick={() => fetchAll({ manual: true })}>Coba lagi</button>
            </>
          )}
        </div>
      </section>

      {/* Tahapan pemeriksaan — stepper vertikal */}
      <section className="card dash-accent" aria-labelledby="steps-title">
        <div className="chart-head-row chart-head-between">
          <div className="chart-head-left">
            <span className="chart-panel-icon" aria-hidden="true"><Workflow size={16} /></span>
            <div>
              <h3 className="chart-title" id="steps-title">Tahapan Pemeriksaan</h3>
              <p className="chart-subtitle">Urutan pemeriksaan yang dilalui setiap klaim</p>
            </div>
          </div>
          <span className="badge badge-neutral">{AGENT_INFO.length} tahap</span>
        </div>

        <ol className="mon-steps">
          {AGENT_INFO.map((item, index) => {
            const comp = health?.components?.[item.key]
            const status = comp?.status || 'warn'
            return (
              <li className={`mon-step ${status === 'ok' ? 'ok' : status === 'error' ? 'error' : 'warn'}`} key={`${item.label}-${index}`}>
                <span className="mon-step-marker" aria-hidden="true">
                  <span className="mon-step-index">{index + 1}</span>
                </span>
                <span className="mon-step-body">
                  <span className="mon-step-name">{item.label}</span>
                  <span className="mon-step-detail">{item.detail}</span>
                </span>
                <span className="badge" style={statusBadgeColors(status)}>
                  {statusText(status)}
                </span>
              </li>
            )
          })}
        </ol>
      </section>
      </div>
    </div>
  )
}
