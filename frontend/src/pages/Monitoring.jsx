import { useState, useEffect } from 'react'
import { Activity, Database, Cpu, Boxes, Network, Bot, TrendingDown, AlertCircle } from 'lucide-react'
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
    {
      label: 'Total Klaim di Database',
      value: stats?.total_claims || 0,
      color: 'var(--text-primary)',
      icon: <Database size={20} color="var(--text-secondary)" />,
      bgGlow: 'var(--bg-card-hover)'
    },
    {
      label: 'Teranalisis AI',
      value: stats?.processed_claims || 0,
      color: 'var(--accent-green)',
      icon: <Bot size={20} color="var(--accent-green)" />,
      bgGlow: 'var(--accent-green-glow)'
    },
    {
      label: 'Risiko Tinggi Terdeteksi',
      value: stats?.high_risk_claims || 0,
      color: 'var(--risk-high)',
      icon: <AlertCircle size={20} color="var(--risk-high)" />,
      bgGlow: 'var(--risk-high-bg)'
    },
    {
      label: 'Sudah Diverifikasi Verifier',
      value: stats?.verified_claims || 0,
      color: 'var(--success)',
      icon: <Activity size={20} color="var(--success)" />,
      bgGlow: 'var(--risk-low-bg)'
    },
  ]

  const statusColor = (s) => s === 'ok' ? 'var(--success)' : s === 'warn' ? 'var(--warning)' : 'var(--risk-high)'
  const statusText = (s) => s === 'ok' ? 'SEHAT' : s === 'warn' ? 'PERINGATAN' : 'ERROR'

  const statusBadgeStyle = (status) => {
    if (status === 'ok') {
      return {
        background: 'var(--risk-low-bg)',
        color: 'var(--risk-low)',
        border: '1px solid rgba(16, 185, 129, 0.15)',
        fontSize: '0.65rem'
      };
    } else if (status === 'warn') {
      return {
        background: 'var(--risk-medium-bg)',
        color: 'var(--warning)',
        border: '1px solid rgba(245, 158, 11, 0.15)',
        fontSize: '0.65rem'
      };
    } else {
      return {
        background: 'var(--risk-high-bg)',
        color: 'var(--risk-high)',
        border: '1px solid rgba(239, 68, 68, 0.15)',
        fontSize: '0.65rem'
      };
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2 className="glow-text" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Activity size={24} color="var(--accent-green)" />
          Monitoring Center
        </h2>
        <p>
          Live analytics & status komponen sistem — diperbarui otomatis setiap 5 detik.
          Status saat ini: <strong style={{ color: statusColor(health?.status), display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ fontSize: '0.5rem' }}>●</span> {statusText(health?.status)}
          </strong>
        </p>
      </div>

      <div className="grid-2 mb-3">
        {statCards.map(card => (
          <div className="card" key={card.label} style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: card.bgGlow,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}>
              {card.icon}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
              <div className="card-title" style={{ marginBottom: 0, fontSize: '0.72rem', letterSpacing: '0.5px' }}>{card.label}</div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.1 }}>
                {(card.value || 0).toLocaleString('id-ID')}
              </div>
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
                <span className="badge" style={statusBadgeStyle(comp.status)}>
                  ● {statusText(comp.status)}
                </span>
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
                  background: status === 'ok' ? 'var(--risk-low-bg)' : 'var(--bg-card-hover)',
                  color: status === 'ok' ? 'var(--risk-low)' : 'var(--text-muted)',
                  border: status === 'ok' ? '1px solid rgba(16, 185, 129, 0.15)' : '1px solid var(--border)',
                }}>
                  <span style={{ color: statusColor(status), marginRight: '4px', fontSize: '0.55rem' }}>●</span> {item.badge}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
