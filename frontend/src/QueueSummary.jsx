import { Users, Target, ShieldCheck, CheckCircle2, ArrowRight, Timer } from 'lucide-react'
import { formatQueueAge, formatDuration } from './queueSummaryData'

const formatRemaining = (ms) => {
  if (ms == null) return '—'
  if (ms < 0) return 'Batas terlewati'
  const hours = ms / 3600000
  if (hours >= 1.5) return `Sisa ${hours.toFixed(1).replace('.', ',')} jam`
  const minutes = Math.max(5, Math.round(ms / 60000))
  return `Sisa ${minutes} menit`
}

const pctOf = (count, total) => Math.min(100, Math.max(0, Math.round(((count || 0) / (total || 1)) * 100)))

export default function QueueSummary({ summary, now = Date.now(), totalClaims = 0, verifiedCount = 0 }) {
  if (!summary) return null

  const queueStats = [
    { label: 'Menunggu', value: summary.pendingCount ?? 0, sub: 'Antrean masuk' },
    { label: 'Sedang Diperiksa', value: summary.scanningCount ?? 0, sub: 'Analisis AI & ML' },
    { label: 'Perlu Review', value: summary.reviewRequiredCount ?? 0, sub: 'Butuh verifier' },
    { label: 'Antrean Tertua', value: formatQueueAge(summary.oldestQueueAt, now), sub: 'Waktu tunggu max' },
    { label: 'Rata-rata waktu pemeriksaan', value: formatDuration(summary.analysisTiming?.averageMs), sub: 'Kecepatan AI' },
    { label: 'Rata-rata waktu verifikasi', value: formatDuration(summary.verificationTiming?.averageMs), sub: 'Keputusan final' },
  ]

  // Strip alur 4 tahap — memakai sisa jendela SLA dari summary yang dihitung
  // queueSummaryData (queueSla / analysisSla / verificationSla .remainingMs).
  const totalRef = totalClaims || (summary.pendingCount ?? 0) + (summary.scanningCount ?? 0) + (summary.reviewRequiredCount ?? 0)
  const steps = [
    {
      label: 'Antrean Masuk',
      icon: <Users size={15} />,
      value: summary.pendingCount ?? 0,
      remaining: formatRemaining(summary.queueSla?.remainingMs),
      tone: '',
    },
    {
      label: 'Analisis AI & ML',
      icon: <Target size={15} />,
      value: summary.scanningCount ?? 0,
      remaining: formatRemaining(summary.analysisSla?.remainingMs),
      tone: '',
    },
    {
      label: 'Review Verifikator',
      icon: <ShieldCheck size={15} />,
      value: summary.reviewRequiredCount ?? 0,
      remaining: formatRemaining(summary.verificationSla?.remainingMs),
      tone: '',
    },
    {
      label: 'Keputusan Final',
      icon: <CheckCircle2 size={15} />,
      value: verifiedCount,
      remaining: 'Jalur selesai',
      tone: 'tone-slate',
    },
  ]

  return (
    <section className="card queue-overview-card dash-accent mb-3" aria-labelledby="queue-summary-title">
      <div className="section-header-compact">
        <div>
          <div className="section-title-row">
            <span className="section-panel-icon" aria-hidden="true">
              <Timer size={16} />
            </span>
            <div>
              <h2 id="queue-summary-title" className="section-title">Pemantauan Antrean &amp; Kepatuhan SLA</h2>
              <p className="section-subtitle">Status beban kerja operasional dan kecepatan pemrosesan klaim real-time. Dihitung dari maks. 1.000 klaim terbaru.</p>
            </div>
          </div>
        </div>
        <span className="live-pill">
          <span className="live-dot" aria-hidden="true" />
          Monitoring Aktif
        </span>
      </div>

      {/* Grid Status Antrean */}
      <div className="queue-metric-row">
        {queueStats.map((item, idx) => (
          <div className="queue-stat-pill" key={idx}>
            <span className="queue-stat-label">{item.label}</span>
            <span className="queue-stat-num">{item.value}</span>
            <span className="queue-stat-sub">{item.sub}</span>
          </div>
        ))}
      </div>

      {/* Strip Alur Pemeriksaan 4 Tahap */}
      <div className="flow" role="list" aria-label="Alur pemeriksaan klaim">
        {steps.map((step, idx) => (
          <div className="flow-step-wrap" key={idx} role="listitem">
            {idx > 0 && (
              <span className="flow-arrow" aria-hidden="true">
                <ArrowRight size={14} strokeWidth={2.2} />
              </span>
            )}
            <div className="flow-step">
              <div className="flow-top">
                <span className={`flow-icon ${step.tone}`}>{step.icon}</span>
                <span className="flow-label">{step.label}</span>
              </div>
              <div className="flow-value">
                {(step.value || 0).toLocaleString('id-ID')} <span>klaim</span>
              </div>
              <div className="flow-bar">
                <i style={{ width: `${pctOf(step.value, totalRef)}%` }} />
              </div>
              <div className="flow-foot">
                <span>{step.remaining}</span>
                <span>{pctOf(step.value, totalRef)}%</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
