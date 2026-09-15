import { claimsApi } from './api'

export const STALE_DATA_AFTER_MS = 60 * 1000
export const SLA_TARGETS = Object.freeze({
  queueWaitMs: 4 * 60 * 60 * 1000,
  analysisMs: 30 * 60 * 1000,
  verificationMs: 24 * 60 * 60 * 1000,
  atRiskRatio: 0.75,
})

const toTimestamp = (value) => {
  if (!value) return null
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? null : timestamp
}

const durationBetween = (item, startKey, endKey, now, openStatuses = []) => {
  const start = toTimestamp(item[startKey])
  const storedEnd = toTimestamp(item[endKey])
  const end = storedEnd ?? (openStatuses.includes(item.status) ? now : null)
  return start != null && end != null && end >= start ? end - start : null
}

const summarizeSla = (items, durationFor, targetMs) => {
  const durations = items.map(durationFor).filter(duration => duration != null)

  if (!durations.length) return null
  const maxElapsedMs = Math.max(...durations)
  const riskThresholdMs = targetMs * SLA_TARGETS.atRiskRatio
  return {
    averageMs: durations.reduce((sum, duration) => sum + duration, 0) / durations.length,
    sampleCount: durations.length,
    targetMs,
    riskThresholdMs,
    atRiskCount: durations.filter(duration => duration >= riskThresholdMs && duration <= targetMs).length,
    breachCount: durations.filter(duration => duration > targetMs).length,
    maxElapsedMs,
    remainingMs: targetMs - maxElapsedMs,
  }
}

export const fetchQueueSummary = async (config = {}) => {
  const [pendingResponse, scanningResponse, processedResponse, reviewResponse, verifiedResponse] = await Promise.all([
    claimsApi.list({ status: 'pending', limit: 1000, sort: 'queue' }, config),
    claimsApi.list({ status: 'scanning', limit: 1000, sort: 'queue' }, config),
    claimsApi.list({ status: 'processed', limit: 1000, sort: 'queue' }, config),
    claimsApi.list({ status: 'review_required', limit: 1000, sort: 'queue' }, config),
    claimsApi.list({ status: 'verified', limit: 1000, sort: 'queue' }, config),
  ])

  const pendingItems = pendingResponse.data.items || []
  const scanningItems = scanningResponse.data.items || []
  const openQueueItems = [...pendingItems, ...scanningItems]
  const oldestQueueItem = openQueueItems
    .filter(item => toTimestamp(item.received_at) != null)
    .sort((left, right) => toTimestamp(left.received_at) - toTimestamp(right.received_at))[0]
  const verifiedItems = verifiedResponse.data.items || []
  const processedItems = processedResponse.data.items || []
  const reviewItems = reviewResponse.data.items || []
  const now = Date.now()
  // Analysis measures scanning work plus every status with a completed analysis.
  const analysisItems = [...scanningItems, ...processedItems, ...reviewItems, ...verifiedItems]
  // Verification measures claims waiting for or completing human verification.
  const verificationItems = [...processedItems, ...reviewItems, ...verifiedItems]
  const queueSla = summarizeSla(
    openQueueItems,
    item => durationBetween(item, 'received_at', null, now, ['pending', 'scanning']),
    SLA_TARGETS.queueWaitMs,
  )
  const analysisSla = summarizeSla(
    analysisItems,
    item => durationBetween(item, 'analysis_started_at', 'analyzed_at', now, ['scanning']),
    SLA_TARGETS.analysisMs,
  )
  const verificationSla = summarizeSla(
    verificationItems,
    item => durationBetween(item, 'analyzed_at', 'verified_at', now, ['processed', 'review_required']),
    SLA_TARGETS.verificationMs,
  )

  return {
    queuedCount: (pendingResponse.data.total || 0) + (scanningResponse.data.total || 0),
    pendingCount: pendingResponse.data.total || 0,
    scanningCount: scanningResponse.data.total || 0,
    reviewRequiredCount: reviewResponse.data.total || 0,
    oldestQueueAt: oldestQueueItem?.received_at || null,
    queueSla,
    analysisSla,
    verificationSla,
    analysisTiming: analysisSla,
    verificationTiming: verificationSla,
  }
}

export const formatQueueAge = (value, now = Date.now()) => {
  const received = toTimestamp(value)
  if (received == null) return '—'
  const minutes = Math.max(0, Math.floor((now - received) / 60000))
  if (minutes < 60) return `${minutes} mnt`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} jam`
  return `${Math.floor(hours / 24)} hari`
}

export const formatDuration = (milliseconds) => {
  if (milliseconds == null) return 'Belum tersedia'
  if (milliseconds < 1000) return 'kurang dari 1 detik'
  const seconds = milliseconds / 1000
  if (seconds < 60) return `${seconds.toFixed(1).replace('.', ',')} detik`
  const minutes = seconds / 60
  if (minutes < 60) return `${minutes.toFixed(1).replace('.', ',')} menit`
  return `${(minutes / 60).toFixed(1).replace('.', ',')} jam`
}

export const formatSlaWindow = (elapsedMs, targetMs) => {
  if (elapsedMs == null || targetMs == null) return 'Belum tersedia'
  const delta = targetMs - elapsedMs
  if (delta < 0) return `Terlambat ${formatDuration(Math.abs(delta))}`
  if (delta === 0) return 'Tepat target'
  return `Sisa ${formatDuration(delta)}`
}
