import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'
import {
  LayoutDashboard,
  AlertTriangle,
  FileText,
  CheckCircle2,
  Clock,
  Activity,
  ArrowUpRight,
  TrendingUp,
  DollarSign,
  ShieldAlert,
} from 'lucide-react'
import { analyticsApi, safeErrorMessage } from '../api'
import DataFreshness from '../DataFreshness'
import QueueSummary from '../QueueSummary'
import { fetchQueueSummary } from '../queueSummaryData'

// Custom sleek tooltip for charts
function CustomChartTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    const data = payload[0]
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-label">{label || data.name}</div>
        <div className="tooltip-value">
          <span className="tooltip-dot" style={{ background: data.color || data.fill || 'var(--accent-green)' }} />
          <strong>{(data.value || 0).toLocaleString('id-ID')}</strong> klaim
        </div>
      </div>
    )
  }
  return null
}

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

  if (loading) {
    return (
      <div className="status-message loading-state" aria-live="polite">
        <div className="loading-spinner" />
        <strong>Memuat Dashboard</strong>
        <p>Menyiapkan ringkasan klaim dan metrik risiko terkini...</p>
      </div>
    )
  }

  if (error && !stats) {
    return (
      <div className="error-wrapper">
        <div className="status-message error" role="alert">
          <AlertTriangle size={24} className="mb-1 text-error" />
          <strong>Ringkasan belum dapat dimuat</strong>
          <p>{error}</p>
          <button className="btn btn-outline mt-2" onClick={() => window.location.reload()}>
            Coba Lagi
          </button>
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
      </div>
    )
  }

  // Data Distribusi Risiko
  const riskData = [
    { name: 'Risiko Tinggi', value: stats?.high_risk_claims || 0, color: '#ef4444' },
    { name: 'Risiko Sedang', value: stats?.medium_risk_claims || 0, color: '#f59e0b' },
    { name: 'Risiko Rendah', value: stats?.low_risk_claims || 0, color: '#10b981' },
    {
      name: 'Menunggu Analisis',
      value: Math.max(0, (stats?.total_claims || 0) - (stats?.analyzed_claims || 0)),
      color: '#94a3b8',
    },
  ].filter((d) => d.value > 0)

  // Data Perjalanan / Status Klaim
  const statusData = [
    { name: 'Menunggu', total: stats?.pending_claims ?? 0, fullLabel: 'Menunggu Pemeriksaan' },
    { name: 'Scanning', total: stats?.scanning_claims ?? 0, fullLabel: 'Sedang Dianalisis' },
    { name: 'Review', total: stats?.review_required_claims ?? 0, fullLabel: 'Perlu Review Petugas' },
    { name: 'Selesai', total: stats?.processed_status_claims ?? 0, fullLabel: 'Analisis Selesai' },
    { name: 'Verifikasi', total: stats?.verified_claims ?? 0, fullLabel: 'Sudah Diputuskan' },
    { name: 'Gagal', total: stats?.failed_claims ?? 0, fullLabel: 'Pemeriksaan Gagal' },
  ]

  const statCards = [
    {
      label: 'Total Klaim',
      value: stats?.total_claims || 0,
      sub: 'Seluruh berkas masuk',
      icon: <FileText size={20} />,
      iconClass: 'icon-box-primary',
    },
    {
      label: 'Menunggu Analisis',
      value: stats?.pending_claims ?? 0,
      sub: 'Dalam antrean pemrosesan',
      icon: <Clock size={20} />,
      iconClass: 'icon-box-warning',
    },
    {
      label: 'Risiko Tinggi',
      value: stats?.high_risk_claims || 0,
      sub: 'Perlu prioritas verifikasi',
      icon: <ShieldAlert size={20} />,
      iconClass: 'icon-box-danger',
    },
    {
      label: 'Selesai Diputuskan',
      value: stats?.verified_claims || 0,
      sub: 'Verifikasi rampung',
      icon: <CheckCircle2 size={20} />,
      iconClass: 'icon-box-success',
    },
  ]

  const highRiskCount = stats?.high_risk_claims || 0
  const progressPercent = stats?.total_claims
    ? Math.round(((stats.processed_claims || stats.analyzed_claims || 0) / stats.total_claims) * 100)
    : 0

  return (
    <div className="dashboard-container">
      {/* Header Utama dengan Badge Sinkronisasi */}
      <header className="dashboard-header">
        <div>
          <div className="dashboard-title-row">
            <div className="header-icon-badge">
              <LayoutDashboard size={20} />
            </div>
            <h1>Dashboard Utama</h1>
          </div>
          <p className="dashboard-subtitle">
            Pusat kendali pemeriksaan klaim, deteksi anomali risiko, dan pemantauan SLA.
          </p>
        </div>

        <DataFreshness
          label="Dashboard"
          lastUpdatedAt={lastUpdatedAt}
          now={currentTime}
          onRefresh={fetchData}
          refreshing={refreshing}
          partial={partialData}
          error={Boolean(error)}
        />
      </header>

      {/* Priority Banner (Klaim Risiko Tinggi) */}
      {highRiskCount > 0 && (
        <section className="priority-banner mb-3" aria-labelledby="priority-heading">
          <div className="priority-content">
            <div className="priority-badge">
              <ShieldAlert size={15} />
              <span>Prioritas Utama</span>
            </div>
            <div className="priority-text">
              <strong id="priority-heading">
                {highRiskCount.toLocaleString('id-ID')} Klaim Terindikasi Risiko Tinggi
              </strong>
              <p>Segera lakukan verifikasi berkas klaim berisiko tinggi untuk mencegah potensi salah bayar.</p>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-primary btn-priority"
            onClick={() => navigate('/claims?tier=high')}
          >
            <span>Buka Klaim Prioritas</span>
            <ArrowUpRight size={16} />
          </button>
        </section>
      )}

      {/* 4 Kartu Metrik Utama */}
      <section className="metric-cards-grid mb-3">
        {statCards.map((card, idx) => (
          <div className="card stat-card" key={idx}>
            <div className="stat-card-top">
              <span className="stat-card-label">{card.label}</span>
              <div className={`stat-icon-box ${card.iconClass}`}>{card.icon}</div>
            </div>
            <div className="stat-card-value">{(card.value || 0).toLocaleString('id-ID')}</div>
            <div className="stat-card-sub">{card.sub}</div>
          </div>
        ))}
      </section>

      {/* Ringkasan Antrean & SLA */}
      {queueSummary && <QueueSummary summary={queueSummary} now={currentTime} />}

      {/* Visualisasi Data: Grafik Distribusi Risiko & Alur Klaim */}
      <div className="charts-grid mb-3">
        {/* Distribusi Risiko */}
        <div className="card chart-card">
          <div className="chart-header">
            <div>
              <h3 className="chart-title">Distribusi Kategori Risiko</h3>
              <p className="chart-subtitle">Proporsi klaim berdasarkan tingkat anomali dan keparahan</p>
            </div>
          </div>

          <div className="chart-body">
            {riskData.length === 0 ? (
              <div className="chart-empty">Belum ada data klaim yang selesai dianalisis.</div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={riskData}
                    cx="50%"
                    cy="48%"
                    innerRadius={62}
                    outerRadius={95}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {riskData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomChartTooltip />} />
                  <Legend
                    verticalAlign="bottom"
                    iconType="circle"
                    formatter={(value) => (
                      <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', fontWeight: 500 }}>
                        {value}
                      </span>
                    )}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Perjalanan Status Klaim */}
        <div className="card chart-card">
          <div className="chart-header">
            <div>
              <h3 className="chart-title">Status Alur Pemeriksaan</h3>
              <p className="chart-subtitle">Distribusi klaim pada setiap tahapan verifikasi</p>
            </div>
          </div>

          <div className="chart-body">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={statusData} margin={{ top: 15, right: 10, left: -15, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="name"
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 12, fontWeight: 500 }}
                  tickLine={false}
                />
                <YAxis
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  cursor={{ fill: 'var(--bg-card-hover)', opacity: 0.7 }}
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const item = payload[0].payload
                      return (
                        <div className="custom-chart-tooltip">
                          <div className="tooltip-label">{item.fullLabel}</div>
                          <div className="tooltip-value">
                            <span className="tooltip-dot" style={{ background: 'var(--accent-green)' }} />
                            <strong>{(item.total || 0).toLocaleString('id-ID')}</strong> berkas
                          </div>
                        </div>
                      )
                    }
                    return null
                  }}
                />
                <Bar dataKey="total" fill="var(--accent-green)" radius={[6, 6, 0, 0]} maxBarSize={45} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Ringkasan Dampak Finansial & Progress */}
      <section className="card financial-summary-card">
        <div className="summary-col">
          <div className="summary-icon-badge green">
            <CheckCircle2 size={20} />
          </div>
          <div>
            <span className="summary-label">Klaim Telah Dianalisis</span>
            <div className="summary-value">{(stats?.analyzed_claims || 0).toLocaleString('id-ID')}</div>
            <span className="summary-sub">Evaluasi risiko selesai</span>
          </div>
        </div>

        <div className="summary-divider" />

        <div className="summary-col">
          <div className="summary-icon-badge warning">
            <DollarSign size={20} />
          </div>
          <div>
            <span className="summary-label">Perkiraan selisih biaya</span>
            <div className="summary-value" style={{ color: 'var(--warning-text)' }}>
              Rp {(stats?.potential_financial_exposure || 0).toLocaleString('id-ID')}
            </div>
            <span className="summary-sub">Estimasi deviasi biaya klaim</span>
          </div>
        </div>

        <div className="summary-divider" />

        <div className="summary-col">
          <div className="summary-icon-badge primary">
            <TrendingUp size={20} />
          </div>
          <div className="w-full">
            <div className="flex justify-between items-center mb-1">
              <span className="summary-label">Progres Pemeriksaan</span>
              <span className="summary-badge-percent">{progressPercent}%</span>
            </div>
            <div className="progress-bar-container">
              <div className="progress-bar-fill" style={{ width: `${progressPercent}%` }} />
            </div>
            <span className="summary-sub">
              {stats?.analyzed_claims || 0} dari {stats?.total_claims || 0} total klaim
            </span>
          </div>
        </div>
      </section>
    </div>
  )
}
