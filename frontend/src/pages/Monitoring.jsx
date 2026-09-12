import { useState, useEffect } from 'react'
import { Activity, Database, Cpu, Boxes, Network, Bot, TrendingDown } from 'lucide-react'
import { analyticsApi, healthApi } from '../api'

const COMPONENT_ICONS = {
  database: <Database size={16} />,
  llm_ollama: <Bot size={16} />,
  ml_financial: <Cpu size={16} />,
  ml_isolation_forest: <Cpu size={16} />,
  vector_store: <Boxes size={16} />,
  graph_metrics: <Network size={16} />,
}

const COMPONENT_LABELS = {
  database: 'Penyimpanan Data Klaim',
  llm_ollama: 'Pemeriksaan Tambahan',
  ml_financial: 'Pemeriksaan Biaya',
  ml_isolation_forest: 'Pemeriksaan Pola Klaim',
  vector_store: 'Data Pembanding Klaim',
  graph_metrics: 'Pola Fasilitas Kesehatan',
}

const AGENT_INFO = [
  { label: 'Pemeriksaan Medis', key: 'llm_ollama', badge: 'Berjalan' },
  { label: 'Pemeriksaan Biaya', key: 'ml_financial', badge: 'Berjalan' },
  { label: 'Pemeriksaan Pola Klaim', key: 'vector_store', badge: 'Berjalan' },
  { label: 'Perangkuman Temuan', key: 'llm_ollama', badge: 'Berjalan' },
  { label: 'Penentuan Prioritas', key: 'database', badge: 'Berjalan' },
  { label: 'Penjelasan Hasil', key: 'llm_ollama', badge: 'Berjalan' },
]

export default function Monitoring() {
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const fetchAll = async () => {
      try {
        const [statsRes, healthRes] = await Promise.allSettled([
          analyticsApi.dashboard(),
          healthApi.check(),
        ])
        if (cancelled) return
        if (statsRes.status === 'fulfilled') setStats(statsRes.value.data)
        if (healthRes.status === 'fulfilled') setHealth(healthRes.value.data)
        else setHealth({ status: 'error', components: {} })
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchAll()
    const interval = setInterval(fetchAll, 5000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  if (loading) return <div className="p-8 text-center text-muted">Memuat data monitoring...</div>

  const statCards = [
    { label: 'Total Klaim di Database', value: stats?.total_claims || 0, color: 'var(--text-primary)' },
    { label: 'Teranalisis AI', value: stats?.processed_claims || 0, color: 'var(--accent-green)' },
    { label: 'Risiko Tinggi Terdeteksi', value: stats?.high_risk_claims || 0, color: 'var(--risk-high)' },
    { label: 'Sudah Diverifikasi Verifier', value: stats?.verified_claims || 0, color: 'var(--success)' },
  ]

  const statusColor = (s) => s === 'ok' ? 'var(--success)' : s === 'warn' ? 'var(--warning)' : 'var(--risk-high)'
  const statusText = (s) => s === 'ok' ? 'Sehat' : s === 'warn' ? 'Perlu perhatian' : 'Gangguan'
  const detailText = (key, comp) => comp?.status === 'ok'
    ? ({
        database: 'Penyimpanan data tersedia',
        llm_ollama: 'Pemeriksaan tambahan tersedia',
        ml_financial: 'Pemeriksaan biaya tersedia',
        ml_isolation_forest: 'Pemeriksaan pola tersedia',
        vector_store: 'Data pembanding tersedia',
        graph_metrics: 'Data fasilitas kesehatan tersedia',
      }[key] || 'Layanan tersedia')
    : 'Layanan perlu diperiksa'

  return (
    <div>
      <div className="page-header">
        <div className="page-kicker">Status layanan</div>
        <h2 className="glow-text" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Activity size={22} color="var(--accent-green)" aria-hidden="true" />
          Pemantauan Sistem
        </h2>
        <p>
          Status layanan diperbarui otomatis setiap 5 detik. Kondisi saat ini: <strong style={{ color: statusColor(health?.status) }}>{statusText(health?.status)}</strong>
        </p>
      </div>

      <div className="grid-2 mb-3">
        {statCards.map(card => (
          <div className="card text-center" key={card.label}>
            <div className="card-title">{card.label}</div>
            <div style={{ fontSize: '2.5rem', fontWeight: 800, color: card.color, marginTop: '0.5rem' }}>
              {(card.value || 0).toLocaleString('id-ID')}
            </div>
          </div>
        ))}
      </div>

       {/* Potential financial exposure */}
       <div className="card mb-3" style={{ borderLeft: '4px solid var(--success)' }}>
         <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
           <TrendingDown size={16} color="var(--success)" /> Potential Financial Exposure
        </div>
        <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--success)' }}>
           Rp {(stats?.potential_financial_exposure || 0).toLocaleString('id-ID')}
        </div>
        <p className="text-xs text-muted mt-1">
            Dihitung dari selisih claimed amount dengan batas atas benchmark
            (hanya klaim prioritas tinggi/sedang). Angka ini adalah exposure awal,
            bukan nilai akhir hasil verifikasi.
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
                {COMPONENT_LABELS[key] || key}
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                 <span className="text-xs text-muted">{detailText(key, comp)}</span>
                <span className="badge" style={{
                  fontSize: '0.65rem',
                  background: statusColor(comp.status),
                  color: 'white',
                }}>{statusText(comp.status)}</span>
              </span>
            </div>
          ))}
           {!health && <div className="text-sm" style={{ color: 'var(--risk-high)' }}>⚠ Layanan pemeriksaan belum dapat dihubungi.</div>}
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
                  color: status === 'ok' ? 'var(--accent-green)' : 'var(--text-muted)',
                }}>
                  <span style={{ color: statusColor(status) }}>●</span> {item.badge}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
