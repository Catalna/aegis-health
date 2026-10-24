import axios from 'axios'
import {
  ACTION_LABELS,
  ERROR_MESSAGES,
  humanizeText,
} from './humanLanguage'

export { ACTION_LABELS, ERROR_MESSAGES }

// Base URL kosong = same-origin → lewat proxy Vite di dev, dan relatif di produksi.
// Bisa dioverride dengan VITE_API_URL untuk deployment terpisah.
const API_BASE = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

export const claimsApi = {
  list: (params = {}, config = {}) => api.get('/api/claims', { ...config, params }),
  get: (id) => api.get(`/api/claims/${id}`),
  create: (claim) => api.post('/api/claims', claim),
  analyze: (claim, params = {}) => api.post('/api/claims/analyze', claim, { params }),
  submitDecision: (claimId, decision, config = {}) => api.post(`/api/claims/${claimId}/decision`, decision, config),
  getAnalysis: (claimId) => api.get(`/api/claims/${claimId}/analysis`).then(response => ({
    ...response,
    data: publicAnalysisProjection(response.data),
  })),
  getDecision: (claimId) => api.get(`/api/claims/${claimId}/decision`),
  reset: (claimId) => api.delete(`/api/claims/${claimId}`),
}

export const analyticsApi = {
  dashboard: (config = {}) => api.get('/api/analytics/dashboard', config),
  trend: (config = {}) => api.get('/api/analytics/trend', config),
}

export const healthApi = {
  check: (config = {}) => api.get('/api/health', config),
}

const PRIVATE_ANALYSIS_KEYS = new Set([
  'agent_errors', 'error', 'error_code', 'error_detail', 'error_message', 'error_type',
  'exception', 'exception_detail', 'failure_reason', 'fallback_error', 'internal_error',
  'last_analysis_error', 'raw_output', 'stack_trace', 'traceback', 'model_used', 'generated_by',
])
const INTERNAL_ANALYSIS_CONTEXT = /(?:\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0|internal[-_ ]?(?:host|service|api|db))\b|\b[a-z0-9-]+\.(?:internal|local)(?::\d+)?\b|[A-Za-z]:[\\/][^\s]+|(?<!\w)\/(?:app|srv|workspace|home|tmp|var|usr|opt)(?:\/[^\s]*)?|\b(?:sqlalchemy|asyncpg|psycopg|postgres(?:ql)?|lancedb|ollama)\b|file:\/\/[^\s]+)/i
const INTERNAL_ANALYSIS_WORDS = new Set([
  'traceback', 'exception', 'failed', 'failure', 'error', 'gagal', 'unavailable',
  'internal', 'unexpected', 'unhandled', 'runtime', 'value', 'type', 'key', 'json',
  'sql', 'database', 'connection', 'timeout', 'permission', 'assertion',
])
const INTERNAL_ANALYSIS_COMPACT_MARKERS = [
  'traceback', 'stacktrace', 'callstack', 'exception', 'internalerror',
  'runtimeerror', 'valueerror', 'typeerror', 'keyerror', 'jsondecodeerror',
]

function isPrivateAnalysisKey(key) {
  const normalized = String(key).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  return PRIVATE_ANALYSIS_KEYS.has(normalized) || [
    'raw_output', 'traceback', 'stack_trace', 'exception_detail', 'internal_error',
    'error_detail', 'error_message', 'failure_reason', 'fallback_error', 'last_analysis_error',
  ].some(part => normalized.includes(part))
}

function containsInternalAnalysisText(value) {
  const normalized = value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
  const compact = normalized.replace(/ /g, '')
  return INTERNAL_ANALYSIS_COMPACT_MARKERS.some(marker => compact.includes(marker))
    || normalized.split(' ').some(token => INTERNAL_ANALYSIS_WORDS.has(token) || token.endsWith('error') || token.endsWith('exception'))
    || INTERNAL_ANALYSIS_CONTEXT.test(value)
}

export function publicAnalysisProjection(value) {
  if (Array.isArray(value)) return value.map(publicAnalysisProjection)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !isPrivateAnalysisKey(key))
        .map(([key, item]) => [key, publicAnalysisProjection(item)]),
    )
  }
  if (typeof value !== 'string') return value
  const readable = humanizeText(value)
  return containsInternalAnalysisText(readable) ? ERROR_MESSAGES.analysis_retryable : readable
}

export function safeErrorMessage(source, fallbackCode = 'analysis_retryable') {
  const payload = source?.response?.data || source || {}
  const code = payload.error_code || payload.code || fallbackCode
  return ERROR_MESSAGES[code] || ERROR_MESSAGES[fallbackCode] || ERROR_MESSAGES.analysis_retryable
}

export const mlApi = {
  evaluation: () => api.get('/api/ml/eval'),
  p1Evaluation: () => api.get('/api/ml/eval/p1'),
}

export function createSSEStream(taskId, callbacks) {
  const url = `${API_BASE}/api/stream/${taskId}`
  const eventSource = new EventSource(url)
  const parsePayload = (event) => publicAnalysisProjection(JSON.parse(event.data))

  eventSource.addEventListener('status', (e) => callbacks.onStatus?.(parsePayload(e)))
  eventSource.addEventListener('phase1_complete', (e) => callbacks.onPhase1?.(parsePayload(e)))
  eventSource.addEventListener('phase2_complete', (e) => callbacks.onPhase2?.(parsePayload(e)))
  eventSource.addEventListener('phase3_complete', (e) => callbacks.onPhase3?.(parsePayload(e)))
  eventSource.addEventListener('phase4_complete', (e) => callbacks.onPhase4?.(parsePayload(e)))
  eventSource.addEventListener('rejected', (e) => { callbacks.onRejected?.(parsePayload(e)); eventSource.close() })
  eventSource.addEventListener('error', (e) => {
    // SSE 'error' event bawaan browser (koneksi putus) vs event error dari pipeline
    let error = { message: 'Koneksi stream terputus' }
    if (e.data) {
      try { error = publicAnalysisProjection(JSON.parse(e.data)) } catch { /* use the transport fallback */ }
    }
    try { callbacks.onError?.(error) } finally { eventSource.close() }
  })
  eventSource.addEventListener('done', () => { callbacks.onDone?.(); eventSource.close() })

  return eventSource
}

// Versi engine analisis — HARUS sinkron dengan ANALYSIS_VERSION di
// backend/app/agents/orchestrator.py. Hasil tersimpan dengan versi berbeda
// dianggap stale (skor dihitung logika lama) dan memicu analisis ulang.
// v6: deterministic evidence contract, no tariff double-counting, behavioral
// context without score contribution, and grounded explanation IDs.
export const ANALYSIS_VERSION = 6

export const formatRecommendedAction = (action) => ACTION_LABELS[action] || action || '-'

// Terjemahan fitur ML untuk tampilan (sinkron dengan FEATURE_LABELS backend)
export const FEATURE_LABELS = {
  primary_diag_encoded: 'Jenis diagnosis',
  num_secondary_diags: 'Jumlah diagnosis sekunder',
  num_procedures: 'Jumlah prosedur',
  num_medications: 'Jumlah jenis obat',
  severity_level: 'Tingkat keparahan',
  length_of_stay: 'Lama rawat',
  cost_claimed_log: 'Besaran biaya klaim',
  cost_vs_peer_ratio: 'Biaya vs rata-rata peer',
  los_vs_expected_ratio: 'Lama rawat vs standar',
  has_high_cost_proc: 'Ada prosedur berbiaya tinggi',
  has_phantom_risk_proc: 'Ada prosedur yang perlu bukti pelaksanaan',
  has_upcoding_risk_diag: 'Ada diagnosis sekunder yang perlu diverifikasi',
  severity_proc_mismatch: 'Tingkat keparahan vs tindakan tidak cocok',
  severity_med_mismatch: 'Tingkat keparahan vs obat tidak cocok',
  los_outlier: 'Lama rawat jauh di atas pola umum',
  cost_outlier: 'Biaya jauh dari pola umum',
  num_total_codes: 'Jumlah total kode medis',
  cost_per_los_log: 'Biaya per hari rawat',
  proc_count_ratio: 'Rasio prosedur vs severity',
  medication_count: 'Jumlah obat',
}

export const formatFeature = (name) => humanizeText(FEATURE_LABELS[name] || name?.replace(/_/g, ' '))

export default api
