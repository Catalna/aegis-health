import { Clock, ShieldCheck, AlertTriangle, AlertCircle, CheckCircle2, Timer } from 'lucide-react'
import { formatDuration, formatQueueAge, formatSlaWindow, SLA_TARGETS } from './queueSummaryData'

export default function QueueSummary({ summary, now = Date.now() }) {
  if (!summary) return null

  const queueStats = [
    { label: 'Menunggu', value: summary.pendingCount ?? 0, sub: 'Antrean masuk' },
    { label: 'Sedang Diperiksa', value: summary.scanningCount ?? 0, sub: 'Analisis AI & ML' },
    { label: 'Perlu Review', value: summary.reviewRequiredCount ?? 0, sub: 'Butuh verifier' },
    { label: 'Antrean Tertua', value: formatQueueAge(summary.oldestQueueAt, now), sub: 'Waktu tunggu max' },
    { label: 'Rata-rata waktu pemeriksaan', value: formatDuration(summary.analysisTiming?.averageMs), sub: 'Kecepatan AI' },
    { label: 'Rata-rata waktu verifikasi', value: formatDuration(summary.verificationTiming?.averageMs), sub: 'Keputusan final' },
  ]

  const slaConfigs = [
    {
      title: 'Tunggu Antrean',
      metric: summary.queueSla,
      targetMs: SLA_TARGETS.queueWaitMs,
      targetLabel: 'Maks. 4 jam',
    },
    {
      title: 'Pemeriksaan Otomatis',
      metric: summary.analysisSla,
      targetMs: SLA_TARGETS.analysisMs,
      targetLabel: 'Maks. 30 menit',
    },
    {
      title: 'Verifikasi Petugas',
      metric: summary.verificationSla,
      targetMs: SLA_TARGETS.verificationMs,
      targetLabel: 'Maks. 24 jam',
    },
  ]

  return (
    <section className="card queue-overview-card mb-3" aria-labelledby="queue-summary-title">
      <div className="section-header-compact">
        <div>
          <h2 id="queue-summary-title" className="section-title">
            <Timer size={18} className="text-emerald" aria-hidden="true" />
            Pemantauan Antrean & Kepatuhan SLA
          </h2>
          <p className="section-subtitle">Status beban kerja operasional dan kecepatan pemrosesan klaim real-time. Dihitung dari maks. 1.000 klaim terbaru.</p>
        </div>
        <span className="sample-badge">Monitoring Aktif</span>
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

      {/* SLA Progress Cards */}
      <div className="sla-monitor-grid">
        {slaConfigs.map((sla, idx) => {
          const maxElapsed = sla.metric?.maxElapsedMs ?? 0
          const target = sla.metric?.targetMs ?? sla.targetMs
          const progressPct = Math.min(100, Math.round((maxElapsed / target) * 100))
          const isBreached = sla.metric?.breachCount > 0 || (sla.metric?.remainingMs != null && sla.metric.remainingMs < 0)
          const isAtRisk = !isBreached && (sla.metric?.atRiskCount > 0 || progressPct >= 75)

          const statusBadge = isBreached ? (
            <span className="sla-badge breach">
              <AlertCircle size={12} /> Melewati Batas ({sla.metric?.breachCount || 1})
            </span>
          ) : isAtRisk ? (
            <span className="sla-badge warning">
              <AlertTriangle size={12} /> Mendekati Batas
            </span>
          ) : (
            <span className="sla-badge normal">
              <CheckCircle2 size={12} /> Sesuai Target
            </span>
          )

          return (
            <div className={`sla-card ${isBreached ? 'breach' : isAtRisk ? 'at-risk' : ''}`} key={idx}>
              <div className="sla-card-head">
                <span className="sla-card-title">{sla.title}</span>
                {statusBadge}
              </div>

              <div className="sla-duration-row">
                <div className="sla-val-block">
                  <span className="sla-tiny-label">Durasi Terlama</span>
                  <span className="sla-val-text">{formatDuration(maxElapsed)}</span>
                </div>
                <div className="sla-val-block text-right">
                  <span className="sla-tiny-label">Target SLA</span>
                  <span className="sla-target-text">{sla.targetLabel}</span>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="sla-progress-track">
                <div
                  className={`sla-progress-bar ${isBreached ? 'bg-error' : isAtRisk ? 'bg-warning' : 'bg-emerald'}`}
                  style={{ width: `${progressPct}%` }}
                />
              </div>

              <div className="sla-footer-row">
                <span className="sla-window-status">{formatSlaWindow(maxElapsed, target)}</span>
                <span className="sla-sample-count">Sampel: {sla.metric?.sampleCount || 0} klaim</span>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
