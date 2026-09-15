import { STALE_DATA_AFTER_MS } from './queueSummaryData'

export default function DataFreshness({ label, lastUpdatedAt, now = Date.now(), onRefresh, refreshing = false, partial = false, error = false, errorMessage = null }) {
  if (!lastUpdatedAt && !partial && !error) return null

  const age = lastUpdatedAt ? now - lastUpdatedAt : Infinity
  const stale = partial || age > STALE_DATA_AFTER_MS
  const updatedAt = lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleTimeString('id-ID', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }) : null

  return (
    <div className={`data-freshness ${stale ? 'stale' : ''}`} role="status" aria-live="polite" aria-atomic="true">
      <span>{error ? `${label} belum berhasil diperbarui.` : refreshing ? `${label} sedang diperbarui.` : partial ? `${label} belum lengkap.` : stale ? `${label} perlu diperbarui.` : `${label} sudah diperbarui.`}{errorMessage ? ` ${errorMessage}` : ''}{updatedAt ? ` Terakhir: ${updatedAt}` : ''}</span>
      <button type="button" className="btn btn-ghost" onClick={onRefresh} disabled={refreshing}>
        {refreshing ? 'Memuat...' : 'Muat ulang'}
      </button>
    </div>
  )
}
