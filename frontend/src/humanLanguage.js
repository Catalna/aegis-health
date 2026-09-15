export const STATUS_LABELS = {
  pending: 'Menunggu pemeriksaan',
  scanning: 'Sedang diperiksa',
  processed: 'Pemeriksaan selesai',
  review_required: 'Perlu ditinjau petugas',
  failed: 'Pemeriksaan belum berhasil',
  verified: 'Sudah diputuskan petugas',
}

export const TIER_LABELS = { high: 'Tinggi', medium: 'Sedang', low: 'Rendah' }

export const ACTION_LABELS = {
  verify_immediately: 'Periksa segera',
  review_when_available: 'Tinjau saat tersedia',
  low_priority: 'Dapat diperiksa secara rutin',
}

export const DECISION_LABELS = {
  'Verified Valid': 'Klaim valid, setujui',
  'Needs Further Review': 'Perlu peninjauan lebih lanjut',
  Escalate: 'Eskalasi ke supervisor',
  'Request Clarification': 'Minta klarifikasi ke fasilitas kesehatan',
}

export const RULE_LABELS = {
  tariff_deviation_extreme: 'Biaya jauh di atas perkiraan biaya penggantian',
  tariff_deviation_high: 'Biaya di atas perkiraan biaya penggantian',
  severity_proc_mismatch: 'Ketidaksesuaian tingkat keparahan dengan tindakan',
  severity_med_mismatch: 'Perbedaan tingkat keparahan dengan biaya pengobatan',
  los_outlier: 'Lama rawat jauh di atas pola umum',
  upcoding_risk_diag: 'Tingkat keparahan diagnosis perlu diverifikasi',
  unsupported_high_risk_proc: 'Tindakan berbiaya tinggi perlu didukung dokumen',
}

export const SIGNAL_LABELS = {
  repeat_billing: 'Pengulangan klaim pada peserta yang sama',
  cloning: 'Kemiripan tidak wajar antar klaim',
  unbundling: 'Pemisahan tindakan yang perlu diperiksa',
}

export const COMPONENT_LABELS = {
  clinical_rule_flags: 'Temuan medis',
  isolation_forest_anomaly: 'Pola klaim yang menyimpang',
  financial_anomaly: 'Perbedaan biaya',
  evidence_support: 'Kekuatan dasar penilaian',
  similarity_fraud: 'Kemiripan riwayat klaim',
}

export const SERVICE_LABELS = {
  database: 'Penyimpanan data klaim',
  llm_ollama: 'Pemeriksaan tambahan',
  ml_financial: 'Pemeriksaan biaya',
  ml_isolation_forest: 'Pemeriksaan pola klaim',
  vector_store: 'Data pembanding klaim',
  graph_metrics: 'Pola fasilitas kesehatan',
  queue_worker: 'Antrean pemeriksaan',
}

export const ERROR_MESSAGES = {
  analysis_retryable: 'Pemeriksaan belum berhasil. Silakan ulangi pemeriksaan.',
  validation_rejected: 'Klaim tidak dapat diproses karena data belum memenuhi syarat.',
  dependency_unavailable: 'Layanan pemeriksaan sedang tidak tersedia. Silakan coba lagi.',
}

export function humanizeRule(value) {
  return RULE_LABELS[value] || String(value || '').replace(/_/g, ' ')
}

export function humanizeSignal(value) {
  return SIGNAL_LABELS[value] || String(value || '').replace(/_/g, ' ')
}

export function humanizeText(value) {
  if (!value) return value
  let text = String(value)
  Object.entries(RULE_LABELS).forEach(([key, label]) => { text = text.replaceAll(key, label) })
  Object.entries(SIGNAL_LABELS).forEach(([key, label]) => { text = text.replaceAll(key, label) })
  return text
    .replace(/\[[^\]]*(?:mistral|deepseek|qwen|llama)[^\]]*\]\s*/gi, 'Catatan tambahan: ')
    .replace(/\b(?:mistral|deepseek|qwen|llama)[\w.-]*:[\w.-]+\b/gi, 'analisis tambahan')
    .replace(/Sinyal deterministik/gi, 'Temuan berdasarkan aturan pemeriksaan')
    .replace(/Flag(?: klinis)?(?: \(rule engine\))?/gi, 'Temuan medis')
    .replace(/rule engine/gi, 'aturan pemeriksaan')
    .replace(/reimbursement benchmark(?: model)?/gi, 'perkiraan biaya penggantian')
    .replace(/Claimed amount/gi, 'Biaya yang diajukan')
    .replace(/prediksi model/gi, 'perkiraan biaya')
    .replace(/\bmodel ML\b/gi, 'perkiraan biaya')
    .replace(/\b(?:LLM|XGBoost|SHAP|Jaccard)\b/gi, 'analisis tambahan')
    .replace(/\bAI\b/gi, 'otomatis')
    .replace(/\bdeterministik\b/gi, 'berdasarkan aturan pemeriksaan')
    .replace(/\bfallback\b/gi, 'data pembanding')
    .replace(/synthetic labels; external domain validation is deferred/gi, 'Label data uji dibuat secara sintetis; validasi pada data lapangan belum dilakukan')
    .replace(/one or both AP values are unavailable/gi, 'Satu atau kedua nilai ketepatan belum tersedia')
    .replace(/no positive labels/gi, 'Belum ada label positif')
    .replace(/no evaluation rows/gi, 'Belum ada data uji yang berhasil dinilai')
    .replace(/\bseverity\b/gi, 'tingkat keparahan')
    .replace(/\boutlier\b/gi, 'jauh dari pola umum')
}

export const formatRecommendedAction = (action) => ACTION_LABELS[action] || humanizeText(action) || '-'
export const formatDecision = (decision) => DECISION_LABELS[decision] || humanizeText(decision) || '-'
