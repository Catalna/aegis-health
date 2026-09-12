import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { claimsApi, createSSEStream, formatRecommendedAction, ANALYSIS_VERSION } from '../api'

const AGENT_LABELS = {
  start: 'Proses Pemeriksaan',
  validation: 'Pemeriksaan Data',
  phase1: 'Pemeriksaan Medis, Biaya, dan Pola',
  phase1_complete: 'Pemeriksaan Awal',
  phase2: 'Perangkuman Temuan',
  phase2_complete: 'Perangkuman Temuan',
  phase3: 'Penentuan Prioritas',
  phase3_complete: 'Penentuan Prioritas',
  phase4: 'Penjelasan Hasil',
  phase4_complete: 'Penjelasan Hasil',
  complete: 'Pemeriksaan Selesai',
  error: 'Sistem',
}

const EVIDENCE_LEVEL_LABELS = {
  strong_multi_signal: 'Banyak Indikasi Kuat',
  single_signal: 'Satu Indikasi',
  weak: 'Tidak Ada Indikasi',
}

function buildClaimPayload(raw) {
  // ClaimRecord DB menyimpan list sebagai CSV/JSON string — rebuild ke format ClaimInput.
  let medication = []
  try {
    medication = raw.medication_json ? JSON.parse(raw.medication_json) : []
  } catch { medication = [] }

  return {
    claim_id: raw.claim_id,
    patient_id: raw.patient_id,
    provider_id: raw.provider_id,
    doctor_id: raw.doctor_id,
    diagnosis_primary: raw.diagnosis_primary,
    diagnosis_secondary: raw.diagnosis_secondary
      ? String(raw.diagnosis_secondary).split(',').map(s => s.trim()).filter(Boolean)
      : [],
    procedure_codes: raw.procedure_codes
      ? String(raw.procedure_codes).split(',').map(s => s.trim()).filter(Boolean)
      : [],
    medication,
    severity_level: raw.severity_level,
    cost_claimed: raw.cost_claimed,
    length_of_stay: raw.length_of_stay,
    admission_date: raw.admission_date || null,
    discharge_date: raw.discharge_date || null,
    referral_info: null,
  }
}

// Guard module-level: cegah analisis dobel akibat double-mount React StrictMode.
// Key termasuk flag rerun agar "Analisis Ulang" tetap bisa jalan.
const _inFlight = new Set()

export default function Investigation() {
  const { claimId } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isRerun = searchParams.get('rerun') === '1'

  const [logs, setLogs] = useState([])
  const [clinical, setClinical] = useState(null)
  const [financial, setFinancial] = useState(null)
  const [fraud, setFraud] = useState(null)
  const [review, setReview] = useState(null)
  const [risk, setRisk] = useState(null)
  const [explanation, setExplanation] = useState(null)
  const [partial, setPartial] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)
  const [rejected, setRejected] = useState(null)
  const [checkingExisting, setCheckingExisting] = useState(true)
  const logsEndRef = useRef(null)
  const startedRef = useRef(false) // guard React StrictMode double-effect (dev)

  const resultRef = useRef({})

  const addLog = (step, message, status = 'done') => {
    const time = new Date().toLocaleTimeString('id-ID', { hour12: false })
    setLogs(prev => [...prev, { time, step, message, agent: AGENT_LABELS[step] || 'Sistem', status }])
  }

  useEffect(() => {
    const runKey = `${claimId}${isRerun ? ':rerun' : ''}`
    if (startedRef.current || _inFlight.has(runKey)) return
    startedRef.current = true
    _inFlight.add(runKey)

    const init = async () => {
      setCheckingExisting(true)

      // Kecuali mode rerun: kalau analisis sudah ada di DB (dan versinya masih
      // current), langsung ke halaman hasil. Versi lama = stale → analisis ulang.
      if (!isRerun) {
        try {
          const analysisRes = await claimsApi.getAnalysis(claimId)
          if (analysisRes.data.status === 'analyzed') {
            const existing = analysisRes.data.result
            if (existing && existing.risk && existing.explanation && existing.analysis_version === ANALYSIS_VERSION) {
              sessionStorage.setItem(`result_${claimId}`, JSON.stringify({
                analysis_version: existing.analysis_version,
                clinical: existing.clinical,
                financial: existing.financial,
                fraud: existing.fraud,
                review: existing.review,
                risk: existing.risk,
                explanation: existing.explanation,
              }))
              navigate(`/assessment/${claimId}`, { replace: true })
              return
            }
          }
        } catch (e) {
          console.warn('Could not check existing analysis:', e.message)
        }
      }

      setCheckingExisting(false)

      // Ambil data klaim LENGKAP dari DB (termasuk tanggal & obat — bukan lagi payload kosong)
      let claimData = {}
      try {
        const claimRes = await claimsApi.get(claimId)
        claimData = buildClaimPayload(claimRes.data)
      } catch (e) {
        claimData = JSON.parse(sessionStorage.getItem(`claim_${claimId}`) || 'null')
        if (!claimData) {
          setError(`Klaim ${claimId} tidak ditemukan di database.`)
          addLog('error', `Klaim ${claimId} tidak ditemukan.`, 'error')
          return
        }
        console.warn('DB fetch gagal, pakai sessionStorage fallback:', e.message)
      }

      try {
        addLog('start', 'Memulai pemeriksaan data klaim...')
        const res = await claimsApi.analyze(claimData)
        const { task_id } = res.data

        const sse = createSSEStream(task_id, {
          onStatus: (data) => addLog(data.step || 'status', data.message, 'running'),
          onPhase1: (data) => {
            setClinical(data.clinical)
            setFinancial(data.financial)
            setFraud(data.fraud)
            setPartial(!!data.partial)
            resultRef.current = { ...resultRef.current, clinical: data.clinical, financial: data.financial, fraud: data.fraud }
             const devPct = data.financial.deviation_pct?.toFixed(1)
            const ifScore = ((data.fraud.isolation_forest_score || 0) * 100).toFixed(0)
            addLog('phase1_complete',
              `Selesai — Flag klinis: ${data.clinical.rule_flags?.length || 0}, ` +
               `Deviasi terhadap benchmark: ${devPct ?? 'belum tersedia'}%, ` +
               `Konteks perilaku pendukung: ${ifScore}%`
              + (data.partial ? ' (sebagian pemeriksaan memakai data cadangan)' : '')
            )
          },
          onPhase2: (data) => {
            setReview(data.review)
            resultRef.current = { ...resultRef.current, review: data.review }
            const levelLabel = EVIDENCE_LEVEL_LABELS[data.review.evidence_level] || data.review.evidence_level
            addLog('phase2_complete', `Sintesis selesai — Kekuatan indikasi: ${levelLabel}`)
          },
          onPhase3: (data) => {
            setRisk(data.risk)
            resultRef.current = { ...resultRef.current, risk: data.risk }
            const tierLabel = data.risk.priority_tier === 'high' ? 'Tinggi' : data.risk.priority_tier === 'medium' ? 'Sedang' : 'Rendah'
            addLog('phase3_complete', `Skor dihitung: ${data.risk.total_score} — Prioritas ${tierLabel}`)
          },
          onPhase4: (data) => {
            setExplanation(data.explanation)
            resultRef.current = { ...resultRef.current, explanation: data.explanation }
            addLog('phase4_complete', `Laporan dihasilkan (${data.explanation.generated_by}) — ${formatRecommendedAction(data.explanation.recommended_action)}`)
          },
          onRejected: (data) => {
            setRejected(data.reason)
            setError(data.reason)
            addLog('error', `KLAIM DITOLAK: ${data.reason}`, 'error')
            _inFlight.delete(runKey)
          },
          onError: (data) => {
            setError(data.message)
            addLog('error', `Error: ${data.message}`, 'error')
            _inFlight.delete(runKey)
          },
          onDone: () => {
            sessionStorage.setItem(`result_${claimId}`, JSON.stringify({
              ...resultRef.current,
              analysis_version: ANALYSIS_VERSION,
            }))
            addLog('complete', 'Investigasi selesai. Klik tombol untuk melihat hasil lengkap.', 'done')
            setDone(true)
            _inFlight.delete(runKey)
          },
        })

        return () => sse.close()
      } catch (e) {
        const msg = e?.response?.data?.detail || e.message
        setError(msg)
        addLog('error', `Gagal menghubungi backend: ${msg}`, 'error')
      }
    }

    init()
  }, [claimId, isRerun, navigate])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const tierColor = { high: 'var(--risk-high)', medium: 'var(--risk-medium)', low: 'var(--risk-low)' }

  if (checkingExisting) {
    return (
      <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
        <div style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>⏳</div>
              <div>Memeriksa riwayat klaim {claimId}...</div>
        <p style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>
          Jika analisis sudah ada, Anda akan diarahkan otomatis ke halaman hasil.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <div className="flex items-center justify-between">
          <div>
            <h2>{isRerun ? 'Periksa Ulang Klaim' : 'Pemeriksaan Klaim'}</h2>
            <p className="font-mono text-sm" style={{ color: 'var(--text-muted)' }}>Klaim: {claimId}</p>
          </div>
          {done && (
            <button className="btn btn-primary" onClick={() => navigate(`/assessment/${claimId}`)}>
              Lihat Hasil Analisis →
            </button>
          )}
        </div>
      </div>

      {rejected && (
        <div className="alert-disclaimer mb-3" style={{ borderLeft: '4px solid var(--risk-high)', color: 'var(--risk-high)' }}>
          <strong>Klaim ditolak oleh validasi deterministik:</strong> {rejected}
        </div>
      )}

      {partial && !rejected && (
        <div className="alert-disclaimer mb-3" style={{ borderLeft: '4px solid var(--warning)' }}>
           ⚠ <strong>Pemeriksaan belum lengkap:</strong> sebagian data tidak tersedia sehingga hasil perlu dibaca dengan perhatian tambahan.
        </div>
      )}

      <div className="grid-2" style={{ gap: '1.5rem' }}>
        {/* Live Timeline */}
        <div className="card">
          <div className="card-title">Riwayat Proses (Live)</div>
          <div className="timeline">
            {logs.map((log, i) => (
              <div className="timeline-item" key={i}>
                <span className="timeline-time">{log.time}</span>
                <div className={`timeline-dot ${i === logs.length - 1 && !done ? 'running' : 'done'}`}
                  style={log.status === 'error' ? { background: 'var(--risk-high)' } : {}} />
                <div className="timeline-content">
                  <div className="timeline-agent" style={log.status === 'error' ? { color: 'var(--risk-high)' } : {}}>
                    {log.agent}
                  </div>
                  <div className="timeline-msg">{log.message}</div>
                </div>
              </div>
            ))}
            {!done && !error && (
              <div className="timeline-item">
                <span className="timeline-time">--:--:--</span>
                <div className="timeline-dot running" />
                <div className="timeline-content">
                  <div className="timeline-agent">Sistem</div>
                  <div className="timeline-msg" style={{ color: 'var(--text-muted)' }}>Menunggu respons agen...</div>
                </div>
              </div>
            )}
            <div ref={logsEndRef} />
          </div>
        </div>

        {/* Hasil sementara (real-time) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {clinical && (
            <div className="card">
                 <div className="card-title">✓ Pemeriksaan Medis</div>
              <div className="flex items-center justify-between mb-1">
                <span>Kewajaran Klinis</span>
                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                  <span className={`badge badge-${clinical.plausibility === 'implausible' ? 'high' : clinical.plausibility === 'questionable' ? 'medium' : 'low'}`}>
               {clinical.plausibility === 'implausible' ? 'Tidak Wajar' : clinical.plausibility === 'questionable' ? 'Meragukan' : clinical.plausibility === 'n/a' ? 'Belum tersedia' : 'Wajar'}
                  </span>
                  {clinical.evidence_source !== 'rule_engine' && (
                    <span className="badge badge-blue" style={{ fontSize: '0.6rem' }}>
                       {clinical.evidence_source === 'llm_local' ? 'Analisis tambahan' : 'Data cadangan'}
                    </span>
                  )}
                </div>
              </div>
              {clinical.rule_flags?.length > 0 && (
                <div className="text-xs mb-1" style={{ color: 'var(--risk-medium)' }}>
                   Temuan yang perlu diperhatikan: {clinical.rule_flags.length}
                </div>
              )}
              {clinical.grouper_result && (
                <div className="flex items-center justify-between mb-1">
                  <span>Kode INA-CBG</span>
                  <span className="badge badge-blue font-mono">{clinical.grouper_result.cbg_code}</span>
                </div>
              )}
              {clinical.tariff_deviation_pct != null && (
                <div className="flex items-center justify-between">
                  <span>Deviasi Tarif Standar</span>
                  <span style={{ fontWeight: 700, color: Math.abs(clinical.tariff_deviation_pct) > 30 ? 'var(--risk-high)' : 'var(--text-primary)' }}>
                    {clinical.tariff_deviation_pct > 0 ? '+' : ''}{clinical.tariff_deviation_pct?.toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          )}

          {financial && (
            <div className="card">
                 <div className="card-title">✓ Pemeriksaan Biaya</div>
              {financial.method === 'zscore_peer_fallback' && (
               <div className="text-xs mb-1" style={{ color: 'var(--warning)' }}>⚠ Menggunakan perbandingan biaya cadangan</div>
              )}
              <div className="flex items-center justify-between mb-1">
                  <span>Perbedaan Claimed Amount dari Benchmark</span>
                <span style={{ fontWeight: 700, color: Math.abs(financial.deviation_pct) > 30 ? 'var(--risk-high)' : 'var(--success)' }}>
                  {financial.deviation_pct > 0 ? '+' : ''}{financial.deviation_pct?.toFixed(1)}%
                </span>
              </div>
              <div className="flex items-center justify-between mb-1">
                <span>Tingkat Anomali Biaya</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <div className="progress-bar" style={{ width: 80 }}>
                    <div className="progress-fill" style={{ width: `${(financial.anomaly_score || 0) * 100}%` }} />
                  </div>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{(financial.anomaly_score * 100).toFixed(0)}%</span>
                </div>
              </div>
            </div>
          )}

          {fraud && (
            <div className="card">
               <div className="card-title">✓ Pemeriksaan Pola Klaim</div>
              <div className="flex items-center justify-between mb-1">
                 <span>Pola yang Perlu Diperiksa</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <div className="progress-bar" style={{ width: 80 }}>
                    <div className="progress-fill" style={{ width: `${(fraud.isolation_forest_score || 0) * 100}%`, background: fraud.isolation_forest_score > 0.7 ? 'var(--risk-high)' : 'var(--accent-green)' }} />
                  </div>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: fraud.isolation_forest_score > 0.7 ? 'var(--risk-high)' : 'inherit' }}>{((fraud.isolation_forest_score || 0) * 100).toFixed(0)}%</span>
                </div>
              </div>
              <div className="flex items-center justify-between mb-1">
                 <span>Kemiripan dengan Klaim Lain</span>
                <span style={{ fontWeight: 700, color: fraud.similarity_max_score > 0.85 ? 'var(--risk-high)' : 'var(--text-primary)' }}>
                  {((fraud.similarity_max_score || 0) * 100).toFixed(0)}%
                </span>
              </div>
              <div className="flex items-center justify-between mb-1">
                 <span>Indikasi Pengulangan Klaim</span>
                <span className={`badge ${fraud.repeat_billing_flag ? 'badge-high' : 'badge-low'}`}>
                  {fraud.repeat_billing_flag ? 'Terdeteksi' : 'Tidak Ada'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                 <span>Pola Fasilitas Kesehatan</span>
                <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{((fraud.graph_cluster_anomaly_score || 0) * 100).toFixed(0)}%</span>
              </div>
            </div>
          )}

          {review && (
            <div className="card">
               <div className="card-title">✓ Ringkasan Temuan</div>
              <div className="flex items-center justify-between mb-1">
                <span>Kekuatan Indikasi</span>
                <span className={`badge ${review.evidence_level === 'strong_multi_signal' ? 'badge-high' : review.evidence_level === 'single_signal' ? 'badge-medium' : 'badge-low'}`}>
                  {EVIDENCE_LEVEL_LABELS[review.evidence_level] || review.evidence_level}
                </span>
              </div>
              <div className="text-xs text-muted mb-1">
                 Cara merangkum: {review.reasoning_source === 'rule_fallback' ? 'aturan pemeriksaan' : 'analisis tambahan'}
              </div>
              {review.corroborating_signals?.length > 0 && (
                <div className="text-xs text-muted">{review.corroborating_signals.join(' • ')}</div>
              )}
            </div>
          )}

          {risk && (
            <div className="card" style={{ borderColor: tierColor[risk.priority_tier] }}>
              <div className="card-title">✓ Skor Risiko Final</div>
              <div className="flex items-center gap-3">
                <div className={`score-circle ${risk.priority_tier}`} style={{ width: 80, height: 80, fontSize: '1.5rem' }}>
                  <span>{risk.total_score}</span>
                </div>
                <div>
                  <span className={`badge badge-${risk.priority_tier}`}>
                    {risk.priority_tier === 'high' ? 'Prioritas Tinggi' : risk.priority_tier === 'medium' ? 'Prioritas Sedang' : 'Prioritas Rendah'}
                  </span>
                  {explanation && (
                    <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                      → {formatRecommendedAction(explanation.recommended_action)}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
