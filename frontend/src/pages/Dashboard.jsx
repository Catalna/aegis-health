import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts'
import { LayoutDashboard, AlertCircle, FileText, CheckCircle, Clock, Brain } from 'lucide-react'
import { analyticsApi } from '../api'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    const fetchData = async () => {
      try {
        const res = await analyticsApi.dashboard()
        if (!cancelled) {
          setStats(res.data)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError('Gagal memuat data dashboard. Pastikan backend aktif.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  if (loading) return <div className="p-8 text-center text-muted">Memuat data dashboard...</div>
  if (error && !stats) return <div className="p-8 text-center" style={{ color: 'var(--risk-high)' }}>{error}</div>

  // Distribusi risiko dari agregasi server (bukan fetch ratusan klaim)
  const riskData = [
    { name: 'Tinggi', value: stats?.high_risk_claims || 0, color: 'var(--risk-high)' },
    { name: 'Sedang', value: stats?.medium_risk_claims || 0, color: 'var(--risk-medium)' },
    { name: 'Rendah', value: stats?.low_risk_claims || 0, color: 'var(--risk-low)' },
    { name: 'Belum Dianalisis', value: Math.max(0, (stats?.total_claims || 0) - (stats?.processed_claims || 0)), color: '#94a3b8' },
  ].filter(d => d.value > 0)

  const statusData = [
    { name: 'Menunggu', total: stats?.pending_claims ?? 0 },
    { name: 'Terproses AI', total: stats?.processed_claims ?? 0 },
    { name: 'Diverifikasi', total: stats?.verified_claims ?? 0 },
  ]

  const statCards = [
    { label: 'Total Klaim', value: stats?.total_claims || 0, icon: <FileText size={20} />, color: 'var(--text-primary)' },
    { label: 'Menunggu Analisis', value: stats?.pending_claims ?? 0, icon: <Clock size={20} />, color: 'var(--warning)' },
    { label: 'Risiko Tinggi', value: stats?.high_risk_claims || 0, icon: <AlertCircle size={20} />, color: 'var(--risk-high)' },
    { label: 'Sudah Diverifikasi', value: stats?.verified_claims || 0, icon: <CheckCircle size={20} />, color: 'var(--success)' },
  ]

  return (
    <div>
      <div className="page-header">
        <h2 className="glow-text" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <LayoutDashboard size={24} color="var(--accent-green)" />
          Dashboard Utama
        </h2>
        <p>Ringkasan performa verifikasi klaim dan analisis risiko.</p>
      </div>

      {error && <div className="alert-disclaimer mb-3" style={{ color: 'var(--risk-high)' }}>⚠ {error} — menampilkan data terakhir.</div>}

      <div className="grid-4 mb-3" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
        {statCards.map((card, i) => (
          <div className="card" key={i} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="card-title" style={{ marginBottom: 0 }}>{card.label}</div>
              <div style={{ color: card.color }}>{card.icon}</div>
            </div>
            <div style={{ fontSize: '2.5rem', fontWeight: 800 }}>
              {(card.value || 0).toLocaleString('id-ID')}
            </div>
          </div>
        ))}
      </div>

      <div className="grid-2 mb-3">
        <div className="card">
          <div className="card-title">Distribusi Risiko Klaim</div>
          <div style={{ height: 300 }}>
            {riskData.length === 0 ? (
              <div className="text-center text-muted" style={{ paddingTop: '8rem' }}>Belum ada klaim teranalisis</div>
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
          <div className="card-title">Status Penyelesaian Klaim</div>
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

      <div className="card" style={{ borderLeft: '4px solid var(--accent-green)' }}>
        <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Brain size={16} color="var(--accent-green)" /> Ringkasan Sistem
        </div>
        <div className="grid-3" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', marginTop: '0.5rem' }}>
          <div>
            <div className="text-xs text-muted">Klaim Teranalisis AI</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{(stats?.processed_claims || 0).toLocaleString('id-ID')}</div>
          </div>
          <div>
            <div className="text-xs text-muted">Estimasi Potensi Penghematan</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--success)' }}>
              Rp {(stats?.potential_savings || 0).toLocaleString('id-ID')}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted">Tingkat Analisis</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
              {stats?.total_claims ? Math.round((stats.processed_claims / stats.total_claims) * 100) : 0}%
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
