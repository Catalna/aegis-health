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
    { label: 'Total Klaim', value: stats?.total_claims || 0, icon: <FileText size={22} />, color: 'var(--text-primary)', bgGlow: 'rgba(15, 23, 42, 0.05)' },
    { label: 'Menunggu Analisis', value: stats?.pending_claims ?? 0, icon: <Clock size={22} />, color: 'var(--warning)', bgGlow: 'rgba(245, 158, 11, 0.08)' },
    { label: 'Risiko Tinggi', value: stats?.high_risk_claims || 0, icon: <AlertCircle size={22} />, color: 'var(--risk-high)', bgGlow: 'rgba(239, 68, 68, 0.08)' },
    { label: 'Sudah Diverifikasi', value: stats?.verified_claims || 0, icon: <CheckCircle size={22} />, color: 'var(--success)', bgGlow: 'rgba(16, 185, 129, 0.08)' },
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

      <div className="grid-4 mb-3" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1.25rem' }}>
        {statCards.map((card, i) => (
          <div className="card" key={i} style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', padding: '1.5rem' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              backgroundColor: card.bgGlow,
              color: card.color,
              flexShrink: 0
            }}>
              {card.icon}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
              <div className="card-title" style={{ marginBottom: 0, fontSize: '0.72rem', letterSpacing: '0.5px' }}>{card.label}</div>
              <div style={{ fontSize: '2rem', fontWeight: 800, lineHeight: 1.1 }}>
                {(card.value || 0).toLocaleString('id-ID')}
              </div>
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
                  <defs>
                    <linearGradient id="gradHigh" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor="#fca5a5" />
                      <stop offset="100%" stopColor="#ef4444" />
                    </linearGradient>
                    <linearGradient id="gradMedium" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor="#fde047" />
                      <stop offset="100%" stopColor="#eab308" />
                    </linearGradient>
                    <linearGradient id="gradLow" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor="#6ee7b7" />
                      <stop offset="100%" stopColor="#10b981" />
                    </linearGradient>
                    <linearGradient id="gradPending" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor="#cbd5e1" />
                      <stop offset="100%" stopColor="#94a3b8" />
                    </linearGradient>
                  </defs>
                  <Pie
                    data={riskData}
                    cx="50%"
                    cy="50%"
                    innerRadius={65}
                    outerRadius={95}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {riskData.map((entry, index) => {
                      let fillUrl = 'url(#gradPending)';
                      if (entry.name === 'Tinggi') fillUrl = 'url(#gradHigh)';
                      else if (entry.name === 'Sedang') fillUrl = 'url(#gradMedium)';
                      else if (entry.name === 'Rendah') fillUrl = 'url(#gradLow)';
                      return <Cell key={`cell-${index}`} fill={fillUrl} />;
                    })}
                  </Pie>
                  <Legend
                    formatter={(value) => <span style={{ color: 'var(--text-secondary)', fontSize: 12, fontWeight: 500 }}>{value}</span>}
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: '12px',
                      border: '1px solid var(--border)',
                      background: 'var(--tooltip-bg)',
                      backdropFilter: 'blur(8px)',
                      boxShadow: '0 8px 24px rgba(15, 23, 42, 0.08)'
                    }}
                    itemStyle={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '0.8rem' }}
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
                <defs>
                  <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity={0.9} />
                    <stop offset="100%" stopColor="#10b981" stopOpacity={0.3} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} strokeOpacity={0.4} />
                <XAxis dataKey="name" stroke="var(--text-muted)" tick={{ fontSize: 12, fontWeight: 500 }} axisLine={false} tickLine={false} dy={8} />
                <YAxis stroke="var(--text-muted)" tick={{ fontSize: 12 }} allowDecimals={false} axisLine={false} tickLine={false} dx={-8} />
                <Tooltip
                  cursor={{ fill: 'rgba(148, 163, 184, 0.06)' }}
                  contentStyle={{
                    borderRadius: '12px',
                    border: '1px solid var(--border)',
                    background: 'var(--tooltip-bg)',
                    backdropFilter: 'blur(8px)',
                    boxShadow: '0 8px 24px rgba(15, 23, 42, 0.08)'
                  }}
                  itemStyle={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '0.8rem' }}
                />
                <Bar dataKey="total" fill="url(#barGradient)" radius={[6, 6, 0, 0]} barSize={40} />
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
