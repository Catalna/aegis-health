import { RotateCw, CheckCircle2, AlertCircle } from 'lucide-react'
import { STALE_DATA_AFTER_MS } from './queueSummaryData'

export default function DataFreshness({
  label = 'Data',
  lastUpdatedAt,
  now = Date.now(),
  onRefresh,
  refreshing = false,
  partial = false,
  error = false,
}) {
  if (!lastUpdatedAt && !partial && !error) return null

  const age = lastUpdatedAt ? now - lastUpdatedAt : Infinity
  const stale = partial || age > STALE_DATA_AFTER_MS
  // Error harus menang atas stale: kegagalan refresh tidak boleh tampil sebagai "data lama".
  const state = error ? 'error' : stale ? 'stale' : 'live'
  const updatedAt = lastUpdatedAt
    ? new Date(lastUpdatedAt).toLocaleTimeString('id-ID', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : null

  return (
    <div
      className={`data-freshness data-freshness-pill ${state}`}
      role="status" aria-live="polite" aria-atomic="true"
    >
      <div className="freshness-indicator">
        {error ? (
          <AlertCircle size={13} className="text-error" aria-hidden="true" />
        ) : (
          <span className={`status-dot ${refreshing ? 'processing' : 'online'}`} aria-hidden="true" />
        )}
        <span className="freshness-text">
          {refreshing ? `${label} sedang diperbarui.` : error ? `${label} belum berhasil diperbarui.` : `${label} sudah diperbarui.`}
        </span>
        {updatedAt && !refreshing && !error && (
          <span className="freshness-time">Sinkron {updatedAt}</span>
        )}
      </div>
      {onRefresh && (
        <button
          type="button"
          className="btn freshness-refresh-btn"
          onClick={onRefresh}
          disabled={refreshing}
          title="Segarkan data sekarang"
          aria-label="Muat ulang data"
        >
          <RotateCw size={12} className={refreshing ? 'animate-spin' : ''} />
          <span>{refreshing ? 'Memuat' : 'Muat ulang'}</span>
        </button>
      )}
    </div>
  )
}
