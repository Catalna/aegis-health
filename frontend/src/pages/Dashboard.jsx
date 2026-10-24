import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
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
  LineChart,
  Line,
} from 'recharts'
import {
  LayoutDashboard,
  AlertTriangle,
  FileText,
  CheckCircle2,
  Clock,
  ArrowUpRight,
  ArrowRight,
  TrendingUp,
  DollarSign,
  ShieldAlert,
  Activity,
  LayoutGrid,
  BarChart3,
  TrendingDown,
} from 'lucide-react'
import { analyticsApi, safeErrorMessage } from '../api'
import DataFreshness from '../DataFreshness'
import QueueSummary from '../QueueSummary'
import { fetchQueueSummary } from '../queueSummaryData'

const formatRp = (value) => `Rp ${(value || 0).toLocaleString('id-ID')}`

const MONTHS_ID = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']
const dayLabel = (isoDate) => {
  const [y, m, d] = (isoDate || '').split('-').map(Number)
  if (!y || !m || !d) return isoDate
  return `${d} ${MONTHS_ID[m - 1]}`
}

const STATUS_LABELS = {
  pending: 'Menunggu',
  scanning: 'Pemeriksaan',
  processed: 'Analisis AI',
  review_required: 'Perlu Verifikasi',
  verified: 'Diputuskan',
  failed: 'Gagal',
}

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

function MultiLineTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-label">{label}</div>
        {payload.map((entry) => (
          <div className="tooltip-value" key={entry.dataKey}>
            <span className="tooltip-dot" style={{ background: entry.color }} />
            <span style={{ color: '#94a3b8', minWidth: 64 }}>{entry.name}:</span>
            <strong>{(entry.value || 0).toLocaleString('id-ID')}</strong> klaim
          </div>
        ))}
      </div>
    )
  }
  return null
}

function DeltaBadge({ current, previous, tone = 'auto' }) {
  const diff = (current ?? 0) - (previous ?? 0)
  const base = previous ?? 0
  const isUp = diff > 0
  const Arrow = isUp ? ArrowUpRight : TrendingDown
  let cls = 'delta-flat'
  let text = '0%'
  if (diff !== 0) {
    text = base > 0 ? `${isUp ? '+' : ''}${Math.round((diff / base) * 100)}%` : `${isUp ? '+' : ''}${diff}`
    if (tone === 'red') cls = 'delta-red'
    else if (tone === 'down') cls = 'delta-down'
    else cls = 'delta-up'
  }
  return (
    <span className="delta">
      <span className={`delta-val ${cls}`}>
        <Arrow size={11} />{text}
      </span>
      <span className="delta-cap">vs. kemarin</span>
    </span>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [trend, setTrend] = useState(null)
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
    const [dashboardResult, trendResult, queueResult] = await Promise.allSettled([
      analyticsApi.dashboard({ signal: controller.signal }),
      analyticsApi.trend({ signal: controller.signal }),
      fetchQueueSummary({ signal: controller.signal }),
    ])

    if (generation !== requestGenerationRef.current) return

    if (dashboardResult.status === 'fulfilled') {
      setStats(dashboardResult.value.data)
      setError(null)
    } else {
      setError(safeErrorMessage(dashboardResult.reason, 'dependency_unavailable'))
    }

    if (trendResult.status === 'fulfilled') {
      setTrend(trendResult.value.data)
    } else {
      setTrend(null)
    }

    if (queueResult.status === 'fulfilled') {
      setQueueSummary(queueResult.value)
      setQueueError(null)
    } else {
      setQueueError('Ringkasan antrean belum dapat dimuat.')
    }

    const completeRefresh =
      dashboardResult.status === 'fulfilled' && queueResult.status === 'fulfilled'
    setPartialData(!completeRefresh)
    if (completeRefresh) setLastUpdatedAt(Date.now())
    setLoading(false)
    setRefreshing(false)
    abortControllerRef.current = controller
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

  // Data Distribusi Risiko — urutan mirip mockup: menunggu dulu, lalu tier risiko.
  const riskData = [
    {
      name: 'Menunggu Analisis',
      value: Math.max(0, (stats?.total_claims || 0) - (stats?.analyzed_claims || 0)),
      color: '#94a3b8',
    },
    { name: 'Risiko Rendah', value: stats?.low_risk_claims || 0, color: '#10b981' },
    { name: 'Risiko Sedang', value: stats?.medium_risk_claims || 0, color: '#f59e0b' },
    { name: 'Risiko Tinggi', value: stats?.high_risk_claims || 0, color: '#ef4444' },
  ].filter((d) => d.value > 0)
  const riskTotal = riskData.reduce((sum, d) => sum + d.value, 0)

  // Data Status Alur Pemeriksaan
  const statusData = [
    { name: 'Menunggu', total: stats?.pending_claims ?? 0, fullLabel: 'Menunggu Pemeriksaan' },
    { name: 'Scanning', total: stats?.scanning_claims ?? 0, fullLabel: 'Sedang Dianalisis' },
    { name: 'Review', total: stats?.review_required_claims ?? 0, fullLabel: 'Perlu Review Petugas' },
    { name: 'Selesai', total: stats?.processed_status_claims ?? 0, fullLabel: 'Analisis Selesai' },
    { name: 'Verifikasi', total: stats?.verified_claims ?? 0, fullLabel: 'Sudah Diputuskan' },
    { name: 'Gagal', total: stats?.failed_claims ?? 0, fullLabel: 'Pemeriksaan Gagal' },
  ]

  const highRiskCount = stats?.high_risk_claims || 0
  const progressPercent = stats?.total_claims
    ? Math.round(((stats.processed_claims || stats.analyzed_claims || 0) / stats.total_claims) * 100)
    : 0

  // Delta "vs. kemarin" dari agregasi endpoint trend
  const tDays = trend?.days || []
  const tToday = tDays[tDays.length - 1] || {}
  const tYesterday = trend?.yesterday || {}
  const todayVerified = trend?.today_verified ?? 0

  const statCards = [
    {
      label: 'Total Klaim',
      value: stats?.total_claims || 0,
      sub: 'Seluruh berkas masuk',
      icon: <FileText size={22} />,
      toneClass: 'tone-green',
      accentClass: 'stat-accent-green',
      delta: <DeltaBadge current={tToday.total} previous={tYesterday.total} />,
    },
    {
      label: 'Menunggu Analisis',
      value: stats?.pending_claims ?? 0,
      sub: 'Dalam antrean pemrosesan',
      icon: <Clock size={22} />,
      toneClass: 'tone-amber',
      accentClass: 'stat-accent-amber',
      delta: <DeltaBadge current={tToday.pending} previous={tYesterday.pending} />,
    },
    {
      label: 'Risiko Tinggi',
      value: highRiskCount,
      sub: 'Perlu prioritas verifikasi',
      icon: <ShieldAlert size={22} />,
      toneClass: 'tone-red',
      accentClass: 'stat-accent-red',
      delta: <DeltaBadge current={tToday.high_risk} previous={tYesterday.high_risk} tone="red" />,
    },
    {
      label: 'Selesai Diputuskan',
      value: stats?.verified_claims || 0,
      sub: 'Verifikasi rampung',
      icon: <CheckCircle2 size={22} />,
      toneClass: 'tone-green',
      accentClass: 'stat-accent-green',
      delta: <DeltaBadge current={todayVerified} previous={tYesterday.verified} tone="down" />,
    },
  ]

  const priority = trend?.priority_claim
  const recentClaims = trend?.recent_claims || []

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

      {/* Banner Prioritas — 3 zona: identitas | fakta klaim | aksi */}
      {highRiskCount > 0 && (
        <section className="dash-banner dash-accent-red mb-3" aria-labelledby="priority-heading">
          <div className="banner-icon" aria-hidden="true">
            <AlertTriangle size={26} strokeWidth={2.1} />
          </div>
          <div className="banner-main">
            <span className="banner-kicker">
              <ShieldAlert size={11} strokeWidth={2.4} />
              Prioritas Utama
            </span>
            <div className="banner-title" id="priority-heading">
              {highRiskCount.toLocaleString('id-ID')} Klaim Terindikasi Risiko Tinggi
            </div>
            <p className="banner-sub">
              Segera lakukan verifikasi berkas klaim berisiko tinggi untuk mencegah potensi salah bayar.
            </p>
          </div>
          {priority && (
            <div className="banner-facts">
              <div className="fact">
                <span className="fact-label">ID Klaim</span>
                <span className="fact-value mono">{priority.claim_id}</span>
              </div>
              <i className="fact-sep" aria-hidden="true" />
              <div className="fact">
                <span className="fact-label">Skor Risiko</span>
                <span className="fact-value">{priority.risk_score ?? '-'}</span>
              </div>
              <i className="fact-sep" aria-hidden="true" />
              {priority.reason && (
                <div className="fact">
                  <span className="fact-label">Alasan</span>
                  <span className="fact-value">{priority.reason}</span>
                </div>
              )}
            </div>
          )}
          <button
            type="button"
            className="btn-danger"
            onClick={() => navigate('/claims?tier=high')}
          >
            Buka Klaim Prioritas
            <ArrowUpRight size={14} />
          </button>
        </section>
      )}

      {/* 4 Kartu Metrik Utama */}
      <section className="metric-cards-grid mb-3">
        {statCards.map((card, idx) => (
          <div className={`card stat-card ${card.accentClass}`} key={idx}>
            <div className="stat-head">
              <span className="stat-card-label">{card.label}</span>
              <div className={`stat-icon ${card.toneClass}`}>{card.icon}</div>
            </div>
            <div className="stat-card-value">{(card.value || 0).toLocaleString('id-ID')}</div>
            <div className="stat-bottom">
              <span className="stat-card-sub">{card.sub}</span>
              {card.delta}
            </div>
          </div>
        ))}
      </section>

      {/* Ringkasan Antrean & SLA */}
      {queueSummary && (
        <QueueSummary
          summary={queueSummary}
          now={currentTime}
          totalClaims={stats?.total_claims || 0}
          verifiedCount={stats?.verified_claims || 0}
        />
      )}

      {/* Visualisasi Data: Distribusi Risiko & Status Alur */}
      <div className="charts-grid mb-3">
        {/* Distribusi Risiko — donut + legend kanan */}
        <div className="card chart-card dash-accent">
          <div className="chart-header chart-head-row">
            <span className="chart-panel-icon" aria-hidden="true"><LayoutGrid size={16} /></span>
            <div>
              <h3 className="chart-title">Distribusi Kategori Risiko</h3>
              <p className="chart-subtitle">Proporsi klaim berdasarkan tingkat anomali dan keparahan</p>
            </div>
          </div>

          <div className="donut-wrap">
            {riskData.length === 0 ? (
              <div className="chart-empty">Belum ada data klaim yang selesai dianalisis.</div>
            ) : (
              <>
                <div className="donut-box">
                  <ResponsiveContainer width={198} height={198}>
                    <PieChart>
                      <Pie
                        data={riskData}
                        cx="50%"
                        cy="50%"
                        innerRadius={53}
                        outerRadius={84}
                        paddingAngle={1}
                        startAngle={90}
                        endAngle={-270}
                        dataKey="value"
                        isAnimationActive={false}
                      >
                        {riskData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} stroke="transparent" />
                        ))}
                      </Pie>
                      <Tooltip content={<CustomChartTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="donut-center" aria-hidden="true">
                    <strong>{riskTotal.toLocaleString('id-ID')}</strong>
                    <span>klaim</span>
                  </div>
                </div>
                <div className="donut-legend">
                  {riskData.map((entry) => (
                    <div className="legend-row" key={entry.name}>
                      <span className="legend-dot" style={{ background: entry.color }} />
                      <span className="legend-name">{entry.name}</span>
                      <span className="legend-pct">
                        {riskTotal ? Math.round((entry.value / riskTotal) * 100) : 0}%
                      </span>
                      <span className="legend-count">{(entry.value || 0).toLocaleString('id-ID')} klaim</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
          <div className="chart-foot">
            Total {(stats?.total_claims || 0).toLocaleString('id-ID')} klaim · {(stats?.analyzed_claims || 0).toLocaleString('id-ID')} sudah dianalisis,
            {(Math.max(0, (stats?.total_claims || 0) - (stats?.analyzed_claims || 0))).toLocaleString('id-ID')} menunggu antrean
          </div>
        </div>

        {/* Status Alur Pemeriksaan */}
        <div className="card chart-card dash-accent">
          <div className="chart-header chart-head-row">
            <span className="chart-panel-icon" aria-hidden="true"><BarChart3 size={16} /></span>
            <div>
              <h3 className="chart-title">Status Alur Pemeriksaan</h3>
              <p className="chart-subtitle">Distribusi klaim pada setiap tahapan verifikasi</p>
            </div>
          </div>

          <div className="chart-body">
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={statusData} margin={{ top: 18, right: 6, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="name"
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 11, fontWeight: 500 }}
                  tickLine={false}
                />
                <YAxis
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 11 }}
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
                <Bar dataKey="total" fill="var(--accent-green)" radius={[5, 5, 0, 0]} maxBarSize={42} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-foot">
            Sampel {(stats?.total_claims || 0).toLocaleString('id-ID')} klaim terbaru · diperbarui otomatis tiap 10 detik
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
              {formatRp(stats?.potential_financial_exposure)}
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

      {/* Bottom: Tren 7 Hari + Klaim Terbaru */}
      <div className="bottom-grid mt-3">
        {/* Tren Klaim 7 Hari */}
        <div className="card chart-card chart-card-tall dash-accent">
          <div className="chart-header chart-head-row chart-head-between">
            <div className="chart-head-left">
              <span className="chart-panel-icon" aria-hidden="true"><Activity size={16} /></span>
              <div>
                <h3 className="chart-title">Tren Klaim 7 Hari Terakhir</h3>
                <p className="chart-subtitle">Perbandingan jumlah klaim, yang berisiko, dan yang selesai</p>
              </div>
            </div>
            <div className="trend-legend">
              <span className="tl-item"><span className="legend-dot" style={{ background: 'var(--accent-green)' }} />Total Klaim</span>
              <span className="tl-item"><span className="legend-dot" style={{ background: 'var(--risk-high)' }} />Risiko Tinggi</span>
              <span className="tl-item"><span className="legend-dot" style={{ background: '#34d399' }} />Selesai</span>
            </div>
          </div>

          <div className="chart-body">
            {tDays.length === 0 ? (
              <div className="chart-empty">Data tren belum tersedia.</div>
            ) : (
              <ResponsiveContainer width="100%" height={228}>
                <LineChart data={tDays.map((d) => ({ ...d, label: dayLabel(d.date) }))} margin={{ top: 10, right: 14, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis
                    dataKey="label"
                    stroke="var(--text-muted)"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                  />
                  <YAxis
                    stroke="var(--text-muted)"
                    tick={{ fontSize: 10.5 }}
                    tickLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip content={<MultiLineTooltip />} />
                  <Line type="monotone" dataKey="total" name="Total" stroke="var(--accent-green)" strokeWidth={2.4} dot={{ r: 3.2, strokeWidth: 0, fill: 'var(--accent-green)' }} activeDot={{ r: 4.5 }} isAnimationActive={false} />
                  <Line type="monotone" dataKey="high_risk" name="Risiko Tinggi" stroke="var(--risk-high)" strokeWidth={2} dot={{ r: 2.8, strokeWidth: 0, fill: 'var(--risk-high)' }} activeDot={{ r: 4.2 }} isAnimationActive={false} />
                  <Line type="monotone" dataKey="done" name="Selesai" stroke="#34d399" strokeWidth={2} dot={{ r: 2.8, strokeWidth: 0, fill: '#34d399' }} activeDot={{ r: 4.2 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="chart-foot">Agregasi harian berdasarkan tanggal penerimaan klaim</div>
        </div>

        {/* Klaim Terbaru */}
        <div className="card tbl-card dash-accent">
          <div className="chart-header chart-head-row chart-head-between">
            <div className="chart-head-left">
              <span className="chart-panel-icon" aria-hidden="true"><FileText size={16} /></span>
              <div>
                <h3 className="chart-title">Klaim Terbaru</h3>
                <p className="chart-subtitle">5 berkas terakhir yang masuk</p>
              </div>
            </div>
            <Link className="link-more" to="/claims">
              Lihat semua <ArrowRight size={11} />
            </Link>
          </div>

          <div className="table-scroll-x">
            <table className="recent-table">
              <thead>
                <tr>
                  <th>ID Klaim</th>
                  <th>Fasilitas</th>
                  <th>Diagnosis</th>
                  <th className="cell-right">Biaya</th>
                  <th className="cell-right">Skor</th>
                  <th>Prioritas</th>
                  <th>Status</th>
                  <th aria-label="Aksi" />
                </tr>
              </thead>
              <tbody>
                {recentClaims.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="chart-empty" style={{ textAlign: 'center' }}>
                      Belum ada klaim yang masuk.
                    </td>
                  </tr>
                ) : (
                  recentClaims.map((claim) => (
                    <tr key={claim.claim_id}>
                      <td><span className="claim-id">{claim.claim_id}</span></td>
                      <td className="cell-text">{claim.provider_id}</td>
                      <td className="cell-text">{claim.diagnosis_primary}</td>
                      <td className="cost">{formatRp(claim.cost_claimed)}</td>
                      <td className="score">{claim.risk_score ?? '-'}</td>
                      <td>
                        <span className={`dash-pill dash-pill-${claim.priority_tier || 'none'}`}>
                          {claim.priority_tier === 'high' ? 'Tinggi'
                            : claim.priority_tier === 'medium' ? 'Sedang'
                            : claim.priority_tier === 'low' ? 'Rendah' : '—'}
                        </span>
                      </td>
                      <td><span className="dash-pill dash-pill-neutral">{STATUS_LABELS[claim.status] || claim.status}</span></td>
                      <td>
                        <Link className="row-action" to={`/investigate/${claim.claim_id}`}>Lihat</Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
