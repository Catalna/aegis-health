import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts'
import { LayoutDashboard, AlertCircle, FileText, CheckCircle, Clock, Brain } from 'lucide-react'
import { analyticsApi, safeErrorMessage } from '../api'
import DataFreshness from '../DataFreshness'
import QueueSummary from '../QueueSummary'
import { fetchQueueSummary } from '../queueSummaryData'

export default function Dashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [queueSummary, setQueueSummary] = useState(null)
  const [queueError, setQueueError] = useState(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null)
  const [currentTime, setCurrentTime] = useState(Date.now())
  const [refreshing, setRefreshing] = useState(false)
  const [partialData, setPartialData] = useState(false)
  const requestGenerationRef = useRef(0)
  const abortControllerRef = useRef(null)

  const fetchData = useCallback(async () => {
      const generation = ++requestGenerationRef.current
      abortControllerRef.current?.abort()
      const controller = new AbortController()
      setRefreshing(true)
      const [dashboardResult, queueResult] = await Promise.allSettled([
        analyticsApi.dashboard({ signal: controller.signal }),
        fetchQueueSummary({ signal: controller.signal }),
      ])
      if (generation !== requestGenerationRef.current) return
      if (dashboardResult.status === 'fulfilled') {
        setStats(dashboardResult.value.data)
        setError(null)
      } else {
       setError(safeErrorMessage(dashboardResult.reason, 'dependency_unavailable'))
      }
      if (queueResult.status === 'fulfilled') {
        setQueueSummary(queueResult.value)
        setQueueError(null)
      } else {
        setQueueError('Ringkasan antrean belum dapat dimuat.')
      }
      const completeRefresh = dashboardResult.status === 'fulfilled' && queueResult.status === 'fulfilled'
      setPartialData(!completeRefresh)
      if (completeRefresh) setLastUpdatedAt(Date.now())
      setLoading(false)
      setRefreshing(false)
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    const clock = setInterval(() => setCurrentTime(Date.now()), 5000)
    return () => {
      clearInterval(interval)
      clearInterval(clock)
      abortControllerRef.current?.abort()
      requestGenerationRef.current += 1
    }
  }, [fetchData])

  if (loading) return <div className="status-message" aria-live="polite"><strong>Menyiapkan ringkasan klaim</strong><p>Data terbaru sedang dimuat.</p></div>
  if (error && !stats) return (
    <>
      <div className="status-message error" role="alert"><strong>Ringkasan belum dapat dimuat</strong><p>{error}</p><button className="btn btn-outline" style={{ marginTop: '1rem' }} onClick={() => window.location.reload()}>Coba lagi</button></div>
       <DataFreshness label="Data dashboard" lastUpdatedAt={lastUpdatedAt} now={currentTime} onRefresh={fetchData} refreshing={refreshing} partial={partialData} error={Boolean(error)} />
    </>
  )

  // Distribusi risiko dari agregasi server (bukan fetch ratusan klaim)
  const riskData = [
    { name: 'Tinggi', value: stats?.high_risk_claims || 0, color: 'var(--risk-high)' },
    { name: 'Sedang', value: stats?.medium_risk_claims || 0, color: 'var(--risk-medium)' },
    { name: 'Rendah', value: stats?.low_risk_claims || 0, color: 'var(--risk-low)' },
    { name: 'Menunggu pemeriksaan', value: Math.max(0, (stats?.total_claims || 0) - (stats?.analyzed_claims || 0)), color: '#94a3b8' },
  ].filter(d => d.value > 0)

  const statusData = [
    { name: 'Menunggu', total: stats?.pending_claims ?? 0 },
    { name: 'Sedang diperiksa', total: stats?.scanning_claims ?? 0 },
    { name: 'Perlu ditinjau petugas', total: stats?.review_required_claims ?? 0 },
    { name: 'Pemeriksaan selesai', total: stats?.processed_status_claims ?? 0 },
    { name: 'Sudah diputuskan petugas', total: stats?.verified_claims ?? 0 },
    { name: 'Pemeriksaan belum berhasil', total: stats?.failed_claims ?? 0 },
  ]

  const statCards = [
    { label: 'Total Klaim', value: stats?.total_claims || 0, icon: <FileText size={20} />, color: 'var(--text-primary)' },
    { label: 'Menunggu pemeriksaan', value: stats?.pending_claims ?? 0, icon: <Clock size={20} />, color: 'var(--warning-text)' },
    { label: 'Risiko Tinggi', value: stats?.high_risk_claims || 0, icon: <AlertCircle size={20} />, color: 'var(--error-text)' },
    { label: 'Sudah diputuskan petugas', value: stats?.verified_claims || 0, icon: <CheckCircle size={20} />, color: 'var(--success)' },
  ]

  return (
    <div>
      <div className="page-header">
        <div className="page-kicker">Pusat kerja verifier</div>
         <h1 className="glow-text" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
           <LayoutDashboard size={22} color="var(--accent-green)" aria-hidden="true" /> Dashboard Utama
         </h1>
        <p>Ringkasan antrian klaim, tingkat risiko, dan pekerjaan yang perlu ditindaklanjuti.</p>
       </div>

       <DataFreshness
         label="Data dashboard"
         lastUpdatedAt={lastUpdatedAt}
         now={currentTime}
          onRefresh={fetchData}
         refreshing={refreshing}
         partial={partialData}
         error={Boolean(error)}
       />

       {error && <div className="alert-disclaimer mb-3" role="status">Data terakhir ditampilkan. Pembaruan berikutnya akan dicoba otomatis.</div>}

       {queueSummary && <QueueSummary summary={queueSummary} now={currentTime} />}
       {queueError && <div className="alert-disclaimer mb-3" role="alert">{queueError} <button className="btn btn-ghost" onClick={() => window.location.reload()}>Muat ulang</button></div>}

      <section className="priority-strip mb-3" aria-labelledby="priority-title">
        <div>
          <div className="page-kicker" id="priority-title">Yang perlu dilihat lebih dulu</div>
          <strong>{(stats?.high_risk_claims || 0).toLocaleString('id-ID')} klaim berisiko tinggi</strong>
          <p>Periksa klaim berisiko tinggi sebelum melanjutkan ke antrian lainnya.</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/claims?tier=high')}>Buka klaim prioritas</button>
      </section>

      <div className="grid-4 mb-3" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
        {statCards.map((card, i) => (
          <div className="card metric-card" key={i}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="card-title" style={{ marginBottom: 0 }}>{card.label}</div>
              <div style={{ color: card.color }}>{card.icon}</div>
            </div>
            <div className="metric-value" style={{ fontSize: '2.5rem', fontWeight: 800 }}>
              {(card.value || 0).toLocaleString('id-ID')}
            </div>
          </div>
        ))}
      </div>

      <div className="grid-2 mb-3">
        <div className="card">
          <div className="section-heading"><div><div className="card-title">Distribusi Risiko</div><p className="section-subtitle">Jumlah klaim berdasarkan tingkat kebutuhan pemeriksaan.</p></div></div>
          <div style={{ height: 300 }}>
            {riskData.length === 0 ? (
              <div className="status-message">Belum ada klaim yang selesai diperiksa.<p>Distribusi risiko akan muncul setelah data tersedia.</p></div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={riskData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {riskData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Legend
                    formatter={(value) => <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{value}</span>}
                  />
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--bg-card)' }}
                    itemStyle={{ color: 'var(--text-primary)' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="card">
          <div className="section-heading"><div><div className="card-title">Perjalanan Klaim</div><p className="section-subtitle">Posisi klaim dari masuk sampai selesai ditinjau.</p></div></div>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={statusData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="name" stroke="var(--text-secondary)" tick={{ fontSize: 12 }} />
                <YAxis stroke="var(--text-secondary)" tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip
                  cursor={{ fill: 'var(--bg-card-hover)' }}
                  contentStyle={{ borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--bg-card)' }}
                />
                <Bar dataKey="total" fill="var(--accent-green)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card summary-card" style={{ borderLeft: '4px solid var(--accent-green)' }}>
        <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Brain size={16} color="var(--accent-green)" aria-hidden="true" /> Ringkasan Aktivitas
        </div>
        <div className="grid-3" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', marginTop: '0.5rem' }}>
          <div>
            <div className="text-xs text-muted">Klaim sudah diperiksa</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{(stats?.analyzed_claims || 0).toLocaleString('id-ID')}</div>
          </div>
          <div>
             <div className="text-xs text-muted">Perkiraan selisih biaya</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--success)' }}>
               Rp {(stats?.potential_financial_exposure || 0).toLocaleString('id-ID')}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted">Kemajuan pemeriksaan</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
              {stats?.total_claims ? Math.round((stats.processed_claims / stats.total_claims) * 100) : 0}%
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
