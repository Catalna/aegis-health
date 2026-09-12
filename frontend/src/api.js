import axios from 'axios'

// Base URL kosong = same-origin → lewat proxy Vite di dev, dan relatif di produksi.
// Bisa dioverride dengan VITE_API_URL untuk deployment terpisah.
const API_BASE = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

export const claimsApi = {
  list: (params = {}) => api.get('/api/claims', { params }),
  get: (id) => api.get(`/api/claims/${id}`),
  create: (claim) => api.post('/api/claims', claim),
  analyze: (claim) => api.post('/api/claims/analyze', claim),
  submitDecision: (claimId, decision) => api.post(`/api/claims/${claimId}/decision`, decision),
  getAnalysis: (claimId) => api.get(`/api/claims/${claimId}/analysis`),
  getDecision: (claimId) => api.get(`/api/claims/${claimId}/decision`),
  reset: (claimId) => api.delete(`/api/claims/${claimId}`),
}

export const analyticsApi = {
  dashboard: () => api.get('/api/analytics/dashboard'),
}

export const healthApi = {
  check: () => api.get('/api/health'),
}

export const mlApi = {
  evaluation: () => api.get('/api/ml/eval'),
}

export function createSSEStream(taskId, callbacks) {
  const url = `${API_BASE}/api/stream/${taskId}`
  const eventSource = new EventSource(url)

  eventSource.addEventListener('status', (e) => callbacks.onStatus?.(JSON.parse(e.data)))
  eventSource.addEventListener('phase1_complete', (e) => callbacks.onPhase1?.(JSON.parse(e.data)))
  eventSource.addEventListener('phase2_complete', (e) => callbacks.onPhase2?.(JSON.parse(e.data)))
  eventSource.addEventListener('phase3_complete', (e) => callbacks.onPhase3?.(JSON.parse(e.data)))
  eventSource.addEventListener('phase4_complete', (e) => callbacks.onPhase4?.(JSON.parse(e.data)))
  eventSource.addEventListener('rejected', (e) => { callbacks.onRejected?.(JSON.parse(e.data)); eventSource.close() })
  eventSource.addEventListener('error', (e) => {
    // SSE 'error' event bawaan browser (koneksi putus) vs event error dari pipeline
    if (e.data) {
      try { callbacks.onError?.(JSON.parse(e.data)) } catch { callbacks.onError?.({ message: 'Koneksi stream terputus' }) }
    }
    eventSource.close()
  })
  eventSource.addEventListener('done', () => { callbacks.onDone?.(); eventSource.close() })

  return eventSource
}

export const ACTION_LABELS = {
  verify_immediately: 'Verifikasi Segera',
  review_when_available: 'Tinjau Saat Tersedia',
  low_priority: 'Prioritas Rendah - Dapat Diproses Rutin',
}

// Versi engine analisis — HARUS sinkron dengan ANALYSIS_VERSION di
// backend/app/agents/orchestrator.py. Hasil tersimpan dengan versi berbeda
// dianggap stale (skor dihitung logika lama) dan memicu analisis ulang.
// v5: scoring deterministik tanpa pengaruh level LLM, model biaya tanpa target
// leakage, serta sinyal prosedur tidak sesuai dan pemecahan klaim.
export const ANALYSIS_VERSION = 5

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
  cost_outlier: 'Biaya outlier',
  num_total_codes: 'Jumlah total kode medis',
  cost_per_los_log: 'Biaya per hari rawat',
  proc_count_ratio: 'Rasio prosedur vs severity',
  medication_count: 'Jumlah obat',
}

export const formatFeature = (name) => FEATURE_LABELS[name] || name?.replace(/_/g, ' ')

export default api
