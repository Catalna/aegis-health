import { useState, useEffect, useCallback, useRef } from 'react'
import { Activity, Database, Cpu, Boxes, Network, Bot, TrendingDown } from 'lucide-react'
import { analyticsApi, healthApi } from '../api'
import DataFreshness from '../DataFreshness'
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
  { label: 'Pemeriksaan Medis', key: 'llm_ollama' },
  { label: 'Pemeriksaan Biaya', key: 'ml_financial' },
  { label: 'Pemeriksaan Pola Klaim', key: 'vector_store' },
  { label: 'Perangkuman Temuan', key: 'llm_ollama' },
  { label: 'Penentuan Prioritas', key: 'database' },
  { label: 'Penjelasan Hasil', key: 'llm_ollama' },
]

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

  const fetchAll = useCallback(async () => {
      const generation = ++requestGenerationRef.current
      abortControllerRef.current?.abort()
      const controller = new AbortController()
      setRefreshing(true)
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
      setRefreshing(false)
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
    }
  }, [fetchAll])

  if (loading) return <div className="p-8 text-center text-muted">Memuat data monitoring...</div>

  const statCards = [
    { label: 'Total klaim', value: stats?.total_claims ?? null, color: 'var(--text-primary)' },
    { label: 'Pemeriksaan selesai', value: stats?.processed_claims ?? null, color: 'var(--accent-green)' },
    { label: 'Klaim berisiko tinggi', value: stats?.high_risk_claims ?? null, color: 'var(--error-text)' },
    { label: 'Sudah diputuskan petugas', value: stats?.verified_claims ?? null, color: 'var(--success)' },
  ]

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

  return (
    <div>
      <div className="page-header">
        <div className="page-kicker">Status layanan</div>
         <h1 className="glow-text" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
           <Activity size={22} color="var(--accent-green)" aria-hidden="true" />
           Pemantauan Sistem
         </h1>
         <p>
             Status layanan diperbarui otomatis setiap 5 detik. Kondisi saat ini: <span className="monitoring-live-status" role="status" aria-live="polite" aria-atomic="true"><strong style={{ color: statusTextColor(healthError ? 'error' : health?.status) }}>{statusText(healthError ? 'error' : health?.status)}</strong></span>
         </p>
      </div>

       <DataFreshness
        label="Data monitoring"
        lastUpdatedAt={lastUpdatedAt}
        now={currentTime}
         onRefresh={fetchAll}
        refreshing={refreshing}
         partial={partialData}
         error={analyticsError || healthError || Boolean(queueError)}
       />

        <div className="monitoring-analytics-state" role="alert" aria-live="assertive" aria-atomic="true">
          {analyticsError && (
            <div className="alert-disclaimer mb-3">
              <strong>{stats ? 'Data analitik usang' : 'Data analitik gagal dimuat'}</strong>
              <p>{stats ? 'Menampilkan angka terakhir yang berhasil dimuat.' : 'Metrik belum tersedia; angka tidak ditampilkan sebagai nol.'}</p>
               <button className="btn btn-ghost" onClick={fetchAll}>Coba lagi</button>
            </div>
          )}
        </div>

       <div className="grid-2 mb-3">
        {statCards.map(card => (
          <div className="card text-center" key={card.label}>
            <div className="card-title">{card.label}</div>
            <div style={{ fontSize: '2.5rem', fontWeight: 800, color: card.color, marginTop: '0.5rem' }}>
              {card.value == null ? '—' : card.value.toLocaleString('id-ID')}
            </div>
          </div>
        ))}
      </div>

       {queueSummary && <QueueSummary summary={queueSummary} now={currentTime} />}
       <div className="monitoring-queue-state" role="alert" aria-live="assertive" aria-atomic="true">
         {queueError && <div className="alert-disclaimer mb-3">{queueError} <button className="btn btn-ghost" onClick={fetchAll}>Muat ulang</button></div>}
       </div>

           {/* Perkiraan selisih biaya */}
       <div className="card mb-3" style={{ borderLeft: '4px solid var(--success)' }}>
         <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <TrendingDown size={16} color="var(--success)" /> Perkiraan Selisih Biaya
        </div>
         <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--success)' }}>
            {stats?.potential_financial_exposure == null ? '—' : `Rp ${stats.potential_financial_exposure.toLocaleString('id-ID')}`}
        </div>
        <p className="text-xs text-muted mt-1">
             Perkiraan ini dihitung dari selisih biaya yang diajukan dengan batas
             atas biaya pembanding untuk klaim berprioritas tinggi atau sedang.
             Angka ini bukan nilai akhir setelah keputusan petugas.
        </p>
      </div>

      {/* Component Health — status nyata dari /api/health */}
      <div className="card mb-3">
         <div className="card-title">Kondisi Layanan</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginTop: '1rem' }}>
          {Object.entries(health?.components || {}).map(([key, comp]) => (
            <div key={key} className="flex items-center justify-between" style={{ padding: '0.4rem 0' }}>
              <span style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {COMPONENT_ICONS[key] || <Cpu size={16} />}
                {COMPONENT_LABELS[key] || 'Layanan pemeriksaan'}
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                 <span className="text-xs text-muted">{detailText(key, comp)}</span>
                 <span className="badge" style={{
                   fontSize: '0.65rem',
                   ...statusBadgeColors(comp.status),
                 }}>{statusText(comp.status)}</span>
              </span>
            </div>
          ))}
            <div className="monitoring-health-state" role="alert" aria-live="assertive" aria-atomic="true">
              {healthError && (
                <>
                  <div className="text-sm" style={{ color: 'var(--error-text)' }}>Layanan pemeriksaan belum dapat dihubungi.</div>
                   <button className="btn btn-ghost" onClick={fetchAll}>Coba lagi</button>
                </>
              )}
            </div>
        </div>
      </div>

      {/* Agent Architecture Status */}
       <div className="card">
         <div className="card-title">Tahapan Pemeriksaan</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1rem' }}>
          {AGENT_INFO.map(item => {
            const comp = health?.components?.[item.key]
            const status = comp?.status || 'warn'
            return (
              <div key={item.label} className="flex items-center justify-between">
                <span style={{ fontSize: '0.85rem' }}>{item.label}</span>
                <span className="badge" style={{
                  fontSize: '0.7rem',
                  background: status === 'ok' ? 'var(--accent-green-glow)' : 'var(--bg-card-hover)',
                   color: status === 'ok' ? 'var(--accent-green)' : 'var(--text-secondary)',
                 }}>
                   <span style={{ color: statusTextColor(status) }}>●</span> {statusText(status)}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
