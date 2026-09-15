import { formatDuration, formatQueueAge, formatSlaWindow, SLA_TARGETS } from './queueSummaryData'

export default function QueueSummary({ summary, now = Date.now() }) {
  const items = [
    { label: 'Menunggu pemeriksaan', value: summary.queuedCount },
    { label: 'Sedang diperiksa', value: summary.scanningCount },
    { label: 'Perlu ditinjau petugas', value: summary.reviewRequiredCount },
    { label: 'Usia antrean tertua', value: formatQueueAge(summary.oldestQueueAt, now) },
    { label: 'Rata-rata waktu pemeriksaan', value: formatDuration(summary.analysisTiming?.averageMs) },
    { label: 'Rata-rata waktu verifikasi', value: formatDuration(summary.verificationTiming?.averageMs) },
  ]
  const slaItems = [
    { label: 'Target waktu antrean', metric: summary.queueSla, targetMs: SLA_TARGETS.queueWaitMs },
    { label: 'Target waktu pemeriksaan', metric: summary.analysisSla, targetMs: SLA_TARGETS.analysisMs },
    { label: 'Target waktu verifikasi', metric: summary.verificationSla, targetMs: SLA_TARGETS.verificationMs },
  ]

  return (
    <section className="card queue-summary mb-3" aria-labelledby="queue-summary-title">
      <div className="section-heading-row">
        <div>
       <h2 id="queue-summary-title">Ringkasan Pekerjaan dan Target Waktu</h2>
           <p className="evaluation-copy">Jumlah pekerjaan yang menunggu serta waktu penyelesaiannya.</p>
           <p className="evaluation-copy">Waktu pemeriksaan mencakup klaim yang sedang diperiksa atau sudah selesai.</p>
           <p className="evaluation-copy">Waktu verifikasi mencakup klaim yang menunggu atau sudah mendapat keputusan petugas.</p>
        </div>
          <span className="text-xs text-muted">Sampel hingga 1.000 klaim</span>
      </div>
      <div className="queue-summary-grid">
        {items.map(item => (
          <div className="queue-summary-item" key={item.label}>
            <div className="queue-summary-label">{item.label}</div>
            <strong className="queue-summary-value">{item.value}</strong>
          </div>
        ))}
      </div>
      <div className="queue-summary-sla-grid">
        {slaItems.map(item => (
          <div className="queue-summary-item" key={item.label} data-sla={item.label}>
            <div className="queue-summary-label">{item.label}</div>
            <strong className="queue-summary-value">{formatDuration(item.metric?.maxElapsedMs)}</strong>
            <div className="queue-summary-label">Target: {formatDuration(item.metric?.targetMs ?? item.targetMs)}</div>
         <div className="queue-summary-label">Perlu perhatian mulai: {formatDuration(item.metric?.riskThresholdMs ?? item.targetMs * SLA_TARGETS.atRiskRatio)}</div>
             <div className="queue-summary-label">Mendekati batas: {item.metric?.atRiskCount ?? 0}</div>
             <div className="queue-summary-label">Melewati batas: {item.metric?.breachCount ?? 0}</div>
            <div className="queue-summary-label" style={{ color: item.metric?.remainingMs < 0 ? 'var(--error-text)' : 'var(--text-secondary)' }}>
              {formatSlaWindow(item.metric?.maxElapsedMs, item.metric?.targetMs ?? item.targetMs)}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
