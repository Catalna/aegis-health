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
  database: 'Database PostgreSQL',
  llm_ollama: 'LLM Lokal (Ollama)',
  ml_financial: 'Financial Engine (XGBoost + SHAP)',
  ml_isolation_forest: 'Isolation Forest',
  vector_store: 'Vector Store (LanceDB)',
  graph_metrics: 'Graph Metrics Provider',
}

const AGENT_INFO = [
  { label: 'Agent 1: Clinical Grouper & Plausibility', key: 'llm_ollama', badge: 'Ollama: Mistral (rule-first, LLM hanya ambigu)' },
  { label: 'Agent 2: Financial Regressor & SHAP', key: 'ml_financial', badge: 'XGBoost (CPU) + SHAP' },
  { label: 'Agent 3: Fraud & Behavioral Isolation', key: 'vector_store', badge: 'LanceDB + Isolation Forest + SQL' },
  { label: 'Agent 4: Review & Synthesis', key: 'llm_ollama', badge: 'Ollama: DeepSeek-R1 / Mistral' },
  { label: 'Agent 5: Risk Score Engine', key: 'database', badge: 'Deterministik (rule + bobot terdokumentasi)' },
  { label: 'Agent 6: Explanation & QA Panel', key: 'llm_ollama', badge: 'Ollama: Qwen / Mistral + validasi angka' },
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
  const statusText = (s) => s === 'ok' ? '● SEHAT' : s === 'warn' ? '● PERINGATAN' : '● ERROR'

  return (
    <div>
      <div className="page-header">
        <h2 className="glow-text" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Activity size={24} color="var(--accent-green)" />
          Monitoring Center
        </h2>
        <p>
          Live analytics & status komponen sistem — diperbarui otomatis setiap 5 detik.
          Status saat ini: <strong style={{ color: statusColor(health?.status) }}>{statusText(health?.status)}</strong>
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

      {/* Potensi Penghematan */}
      <div className="card mb-3" style={{ borderLeft: '4px solid var(--success)' }}>
        <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <TrendingDown size={16} color="var(--success)" /> Estimasi Potensi Penghematan Dana JKN
        </div>
        <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--success)' }}>
          Rp {(stats?.potential_savings || 0).toLocaleString('id-ID')}
        </div>
        <p className="text-xs text-muted mt-1">
          Dihitung dari selisih biaya klaim vs batas atas prediksi model finansial
          (hanya klaim risiko tinggi/sedang). Angka ini adalah estimasi potensi berdasarkan
          pola anomali — bukan nilai final verifikasi.
        </p>
      </div>

      {/* Component Health — status nyata dari /api/health */}
      <div className="card mb-3">
        <div className="card-title">Component Health Status (real-time)</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginTop: '1rem' }}>
          {Object.entries(health?.components || {}).map(([key, comp]) => (
            <div key={key} className="flex items-center justify-between" style={{ padding: '0.4rem 0' }}>
              <span style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {COMPONENT_ICONS[key] || <Cpu size={16} />}
                {COMPONENT_LABELS[key] || key}
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span className="text-xs text-muted">{comp.detail}</span>
                <span className="badge" style={{
                  fontSize: '0.65rem',
                  background: statusColor(comp.status),
                  color: 'white',
                }}>{statusText(comp.status)}</span>
              </span>
            </div>
          ))}
          {!health && <div className="text-sm" style={{ color: 'var(--risk-high)' }}>⚠ Tidak dapat menghubungi endpoint /api/health</div>}
        </div>
      </div>

      {/* Agent Architecture Status */}
      <div className="card">
        <div className="card-title">Agent Health Status</div>
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
