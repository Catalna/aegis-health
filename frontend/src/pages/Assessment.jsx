import { useState, useEffect, useRef, Fragment } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts'
import { RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'
import { claimsApi, formatRecommendedAction, formatFeature, ANALYSIS_VERSION, safeErrorMessage, publicAnalysisProjection } from '../api'
import { COMPONENT_LABELS as PLAIN_COMPONENT_LABELS, RULE_LABELS, SIGNAL_LABELS, humanizeText } from '../humanLanguage'

// Maps for technical terms -> human readable
const COMPONENT_LABELS = PLAIN_COMPONENT_LABELS

const EVIDENCE_LEVEL_LABELS = {
  strong_multi_signal: 'Banyak Indikasi Kuat',
  single_signal: 'Satu Indikasi',
  weak: 'Bukti Belum Menguat',
}

const fmtRp = (x) => `Rp ${Math.round(x || 0).toLocaleString('id-ID')}`
const INTERNAL_ANALYSIS_TEXT = /(?:\b(?:traceback|stack\s*trace|call\s*stack|exception)\b|\b(?:internal|unexpected|unhandled|runtime|value|type|key|json|sql|database|connection|timeout|permission|assertion)\s*[-_ ]?(?:error|failure|exception)\b|\b(?:failed|failure|error|gagal|tidak\s+tersedia)\b|\bsecret(?:[_\s-]+[a-z0-9]+)+\b|\[[^\]]*\b(?:fallback|error|exception|unavailable)\b[^\]]*\])/i

function plainText(value, section) {
  if (!value) return value
  const text = String(value)
  if (
    ((['clinical', 'financial', 'fraud', 'review'].includes(section)) && INTERNAL_ANALYSIS_TEXT.test(text))
    || /(?:clinical|financial|fraud)\s+(?:agent|engine)\s+gagal:/i.test(text)
    || /Penilaian klinis LLM tidak tersedia\s*\(/i.test(text)
    || /\[Fallback (?:z-score peer|rule-count)[^\]]*:/i.test(text)
  ) {
    return safeErrorMessage({ code: 'analysis_retryable' })
  }
  return humanizeText(text
    .replace(/phantom billing/gi, 'tindakan yang belum terbukti')
    .replace(/repeat billing/gi, 'pengulangan klaim')
    .replace(/cloning/gi, 'kemiripan tidak wajar antar klaim')
    .replace(/upcoding/gi, 'tingkat keparahan yang tidak sesuai')
    .replace(/agent\s*\d+/gi, 'pemeriksaan')
    .replace(/XGBoost\s*\+\s*SHAP/gi, 'analisis biaya')
    .replace(/XGBoost/gi, 'analisis biaya')
    .replace(/SHAP/gi, 'faktor biaya')
    .replace(/\bseverity\b/gi, 'tingkat keparahan')
    .replace(/\boutlier\b/gi, 'jauh dari pola umum')
    .replace(/\bfallback\b/gi, 'data cadangan')
    .replace(/\bN\/A\b/gi, 'tidak tersedia')
    .replace(/fallback/gi, 'data cadangan')
    .replace(/rule engine/gi, 'aturan pemeriksaan')
    .replace(/LLM/gi, 'analisis tambahan')
    .replace(/\bmodel\b/gi, 'perkiraan')
    .replace(/\bCBG\b/gi, 'kelompok biaya')
    .replace(/ACUTE MYOCARDIAL INFARCTION/gi, 'serangan jantung akut')
    .replace(/diagnosis-prosedur-severity/gi, 'diagnosis, tindakan, dan tingkat keparahan')
    .replace(/deviasi/gi, 'perbedaan')
    .replace(/evidence/gi, 'temuan'))
}

export default function Assessment() {
  const { claimId } = useParams()
  const navigate = useNavigate()

  const [data, setData] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const [stale, setStale] = useState(false)
  const [analysisError, setAnalysisError] = useState(null)
  const [analysisRetryGeneration, setAnalysisRetryGeneration] = useState(0)
  const [expandedSimilar, setExpandedSimilar] = useState(null)
  const [decision, setDecision] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [existingDecision, setExistingDecision] = useState(null)
  const [loadingDecision, setLoadingDecision] = useState(true)
  const [decisionLoadError, setDecisionLoadError] = useState(null)
  const [decisionError, setDecisionError] = useState(null)
  const [decisionRetryGeneration, setDecisionRetryGeneration] = useState(0)
  const [savingDecision, setSavingDecision] = useState(false)
  const analysisGenerationRef = useRef(0)
  const analysisClaimRef = useRef(claimId)
  const decisionGenerationRef = useRef(0)
  const decisionClaimRef = useRef(claimId)
  const decisionPostGenerationRef = useRef(0)
  const decisionPostControllerRef = useRef(null)

  // Load analysis result: sessionStorage → fallback DB.
  // Guard versi: hasil dengan analysis_version berbeda = stale (dihitung
  // logika engine lama) → jangan ditampilkan, minta analisis ulang.
  useEffect(() => {
    const generation = ++analysisGenerationRef.current
    let cancelled = false
    const isCurrent = () => !cancelled && generation === analysisGenerationRef.current
    const forceFetch = analysisClaimRef.current === claimId && analysisRetryGeneration > 0
    analysisClaimRef.current = claimId

    if (!forceFetch) setData(null)
    setNotFound(false)
    setStale(false)
    setAnalysisError(null)
    const stored = forceFetch ? null : sessionStorage.getItem(`result_${claimId}`)
    if (stored) {
      try {
        const parsed = publicAnalysisProjection(JSON.parse(stored))
        if (isCurrent() && parsed.analysis_version === ANALYSIS_VERSION) {
          sessionStorage.setItem(`result_${claimId}`, JSON.stringify(parsed))
          setData(parsed)
          return () => { cancelled = true }
        }
        sessionStorage.removeItem(`result_${claimId}`)
      } catch { /* fallthrough */ }
    }
    const loadAnalysis = async () => {
      try {
        const res = await claimsApi.getAnalysis(claimId)
        if (!isCurrent()) return
        const existing = publicAnalysisProjection(res.data)
        if (existing.status === 'stale') {
          setStale(true)
          setNotFound(true)
          return
        }
        if (existing.status === 'analyzed' && existing.result?.risk && existing.result?.explanation) {
          if (existing.result.analysis_version !== ANALYSIS_VERSION) {
            setStale(true)
            setNotFound(true)
            return
          }
          const rebuilt = publicAnalysisProjection({
            analysis_version: existing.result.analysis_version,
            clinical: existing.result.clinical,
            financial: existing.result.financial,
            fraud: existing.result.fraud,
            review: existing.result.review,
            risk: existing.result.risk,
            explanation: existing.result.explanation,
          })
          if (!isCurrent()) return
          sessionStorage.setItem(`result_${claimId}`, JSON.stringify(rebuilt))
          setData(rebuilt)
        } else {
          setNotFound(true)
        }
      } catch (error) {
        if (!isCurrent()) return
        if (error?.response?.status === 404) setNotFound(true)
        else setAnalysisError(safeErrorMessage(error, 'dependency_unavailable'))
      }
    }
    loadAnalysis()
    return () => { cancelled = true }
  }, [claimId, analysisRetryGeneration])

  // Keputusan verifier tersimpan di DB — persisten lintas reload
  useEffect(() => {
    const generation = ++decisionGenerationRef.current
    let cancelled = false
    const isCurrent = () => !cancelled && generation === decisionGenerationRef.current

    const preserveDecision = decisionClaimRef.current === claimId && decisionRetryGeneration > 0
    decisionClaimRef.current = claimId
    if (!preserveDecision) {
      setExistingDecision(null)
      setSubmitted(false)
      setDecision('')
    }
    setLoadingDecision(true)
    setDecisionLoadError(null)
    const fetchDecision = async () => {
      try {
        const res = await claimsApi.getDecision(claimId)
        if (!isCurrent()) return
        if (res.data.status === 'decided') {
          setExistingDecision(res.data)
          setSubmitted(true)
          setDecision(res.data.decision)
        } else {
          setExistingDecision(null)
          setSubmitted(false)
          setDecision('')
        }
     } catch (e) {
         if (isCurrent()) setDecisionLoadError(safeErrorMessage(e, 'dependency_unavailable'))
      } finally {
        if (isCurrent()) setLoadingDecision(false)
      }
    }
    fetchDecision()
    return () => {
      cancelled = true
      decisionGenerationRef.current += 1
      decisionPostGenerationRef.current += 1
      decisionPostControllerRef.current?.abort()
    }
  }, [claimId, decisionRetryGeneration])

  const handleAnalysisRetry = () => {
    setAnalysisError(null)
    setNotFound(false)
    setStale(false)
    setAnalysisRetryGeneration(generation => generation + 1)
  }

  const handleDecisionRetry = () => {
    setDecisionLoadError(null)
    setDecisionRetryGeneration(generation => generation + 1)
  }

  const handleSubmitDecision = async () => {
    if (!decision) return
    const generation = ++decisionPostGenerationRef.current
    const controller = new AbortController()
    decisionPostControllerRef.current = controller
    const isCurrent = () => generation === decisionPostGenerationRef.current
    setSavingDecision(true)
    setDecisionError(null)
    try {
      const response = await claimsApi.submitDecision(claimId, {
        claim_id: claimId,
        decision,
        reviewer: 'BPJS-VERIFIER-01',
      }, { signal: controller.signal })
      if (!isCurrent()) return
      setSubmitted(true)
      setExistingDecision({
        decision,
        reviewer: 'BPJS-VERIFIER-01',
        verified_at: response.data.verified_at,
      })
    } catch (e) {
      if (isCurrent() && e?.code !== 'ERR_CANCELED' && e?.name !== 'CanceledError') {
        setDecisionError(safeErrorMessage(e, 'dependency_unavailable'))
      }
    } finally {
      if (isCurrent()) setSavingDecision(false)
      if (decisionPostControllerRef.current === controller) {
        decisionPostControllerRef.current = null
      }
    }
  }

  const handleRerun = async () => {
    if (!confirm('Analisis ulang akan menghapus hasil dan keputusan yang tersimpan untuk klaim ini. Lanjutkan?')) return
    try {
      await claimsApi.reset(claimId)
      sessionStorage.removeItem(`result_${claimId}`)
      navigate(`/investigate/${claimId}?rerun=1`)
    } catch (e) {
      alert('Gagal mereset klaim untuk analisis ulang.')
    }
  }

  if (analysisError && !data) return (
    <div className="status-message error" role="alert">
      <strong>Hasil pemeriksaan belum dapat dimuat</strong>
      <p>{analysisError}</p>
      <button className="btn btn-outline" style={{ marginTop: '1rem' }} onClick={handleAnalysisRetry}>
        Coba muat lagi
      </button>
    </div>
  )

  if (notFound) return (
    <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
      <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>⚠</div>
      {stale ? (
        <>
           <div>Hasil pemeriksaan tersimpan dibuat dengan <strong>aturan pemeriksaan yang lama</strong>.</div>
          <p style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>
             Hasil lama perlu diperbarui agar sesuai dengan aturan pemeriksaan terbaru.
          </p>
        </>
      ) : (
        <p style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>Silakan jalankan investigasi terlebih dahulu dari Daftar Klaim.</p>
      )}
      <button className="btn btn-primary" style={{ marginTop: '1rem' }} onClick={handleRerun}>
         <RefreshCw size={14} aria-hidden="true" /> Periksa Ulang
      </button>
    </div>
  )

  if (!data) return <div className="p-8 text-center text-muted">Memuat hasil analisis...</div>

  const { risk, explanation, clinical, financial, fraud, review } = data
  const tierColor = { high: 'var(--risk-high)', medium: 'var(--risk-medium)', low: 'var(--risk-low)' }

  // Breakdown skor untuk chart
  const shapData = Object.entries(risk.breakdown || {})
    .map(([key, val]) => ({ name: COMPONENT_LABELS[key] || 'Komponen pemeriksaan', value: val }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))

  // SHAP features asli dari model (bukan breakdown bobot)
  const shapFeatures = financial?.shap_top_features || []

  const similarClaims = fraud?.similar_claims || []
  const deterministicEvidence = (risk?.evidence || [])
    .filter(item => item.source_family !== 'behavioral_context')

  const DECISION_OPTIONS = [
    { value: 'Verified Valid', label: 'Klaim Valid — Setujui' },
    { value: 'Needs Further Review', label: 'Perlu Peninjauan Lebih Lanjut' },
    { value: 'Escalate', label: 'Eskalasi ke Supervisor' },
    { value: 'Request Clarification', label: 'Minta Klarifikasi ke Faskes' },
  ]
  const DECISION_LABELS = Object.fromEntries(DECISION_OPTIONS.map(o => [o.value, o.label]))

  return (
    <div>
      <div className="page-header">
        <div className="flex items-center justify-between">
          <div>
            <h1>Hasil Pemeriksaan Klaim</h1>
            <p className="font-mono text-sm" style={{ color: 'var(--text-muted)' }}>Klaim: {claimId}</p>
          </div>
          <div className="flex gap-1">
             <button className="btn btn-ghost" onClick={handleRerun} title="Hapus hasil lama dan periksa kembali">
               <RefreshCw size={14} aria-hidden="true" /> Periksa Ulang
            </button>
            <button className="btn btn-ghost" onClick={() => navigate('/claims')}>
              ← Daftar Klaim
            </button>
          </div>
        </div>
      </div>

      {analysisError && (
        <div className="alert-disclaimer mb-3" role="alert">
          <strong>Hasil pemeriksaan terbaru belum dapat dimuat.</strong> {analysisError}
          <button className="btn btn-ghost" style={{ marginLeft: '0.75rem' }} onClick={handleAnalysisRetry}>Coba muat lagi</button>
        </div>
      )}

      {data.partial && (
        <div className="alert-disclaimer mb-3" style={{ borderLeft: '4px solid var(--warning-text)' }}>
         ⚠ <strong>Pemeriksaan belum lengkap</strong> — sebagian data tidak tersedia sehingga temuan perlu dibaca dengan perhatian tambahan.
        </div>
      )}

      <div className="alert-disclaimer mb-4">
        ⓘ <strong>PENTING:</strong> Sistem ini membantu menentukan prioritas verifikasi — keputusan akhir tetap di tangan petugas verifier BPJS.
      </div>

      <div className="grid-2" style={{ gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Executive Result */}
        <div className="card" style={{ borderTop: `4px solid ${tierColor[risk.priority_tier]}` }}>
          <div className="card-title">Ringkasan Hasil</div>
          <div className="flex items-center gap-3">
            <div className={`score-circle ${risk.priority_tier}`}>
              {risk.total_score}
            </div>
            <div>
              <div className="text-xs text-muted mb-1">Makin tinggi, makin perlu diverifikasi lebih dulu</div>
              <div className="mb-1">
                <span className={`badge badge-${risk.priority_tier}`}>
                  Prioritas {risk.priority_tier === 'high' ? 'Tinggi' : risk.priority_tier === 'medium' ? 'Sedang' : 'Rendah'}
                </span>
              </div>
               <p style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.2rem' }}>
                 {formatRecommendedAction(explanation.recommended_action)}
               </p>
              <p className="text-muted text-sm">
                 {clinical?.rule_flags?.length > 0
                   ? `${clinical.rule_flags.length} temuan medis perlu diperhatikan`
                   : 'Tidak ada temuan medis yang perlu ditindaklanjuti'}
              </p>
            </div>
          </div>
        </div>

        {/* Human Decision */}
        <div className="card">
          <div className="card-title">Keputusan Petugas Verifier</div>
          {submitted ? (
            <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--success)' }}>
              <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>✓</div>
              <div style={{ fontWeight: 600 }}>Keputusan Berhasil Disimpan</div>
              {existingDecision && (
                <>
                  <p className="text-sm text-muted" style={{ marginTop: '0.25rem' }}>
                    Keputusan: <strong style={{ color: 'var(--text-secondary)' }}>
                      {DECISION_LABELS[existingDecision.decision] || existingDecision.decision}
                    </strong>
                  </p>
                  <p className="text-sm text-muted">Dicatat oleh: {existingDecision.reviewer}</p>
                  {existingDecision.verified_at && (
                    <p className="text-xs text-muted" style={{ marginTop: '0.25rem' }}>
                      Diverifikasi: {new Date(existingDecision.verified_at).toLocaleString('id-ID')}
                    </p>
                  )}
                </>
              )}
              <button
                className="btn btn-ghost"
                style={{ marginTop: '0.75rem', fontSize: '0.75rem' }}
                onClick={() => { setSubmitted(false); setExistingDecision(null) }}
              >
                Ubah Keputusan
              </button>
              {decisionLoadError && (
                <div className="status-message error" role="alert" style={{ marginTop: '1rem', textAlign: 'left' }}>
                  <strong>Riwayat keputusan belum dapat diperbarui</strong>
                  <p>{decisionLoadError}</p>
                  <button className="btn btn-outline" style={{ marginTop: '0.75rem' }} onClick={handleDecisionRetry}>
                    Muat keputusan lagi
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div>
              {decisionLoadError ? (
                <div className="status-message error" role="alert" style={{ padding: '1rem' }}>
                  <strong>Riwayat keputusan belum dapat dimuat</strong>
                  <p>{decisionLoadError}</p>
                  <button className="btn btn-outline" style={{ marginTop: '0.75rem' }} onClick={handleDecisionRetry}>
                    Muat keputusan lagi
                  </button>
                </div>
              ) : loadingDecision ? (
                <div className="text-sm text-muted text-center" style={{ padding: '1rem' }}>
                  Memeriksa riwayat keputusan...
                </div>
              ) : (
                <>
                  {decisionError && (
                    <div className="status-message error" role="alert" style={{ padding: '1rem', marginBottom: '1rem' }}>
                      <strong>Keputusan belum tersimpan</strong>
                      <p>{decisionError}</p>
                      <button className="btn btn-outline" style={{ marginTop: '0.75rem' }} onClick={handleSubmitDecision} disabled={savingDecision}>
                        Coba simpan lagi
                      </button>
                    </div>
                  )}
                  <fieldset className="assessment-decision-fieldset">
                    <legend className="sr-only">Keputusan Petugas Verifier</legend>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
                      {DECISION_OPTIONS.map(opt => (
                        <label key={opt.value} className="assessment-decision-option" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', padding: '0.5rem 0.75rem', background: 'var(--bg-secondary)', borderRadius: '6px', border: decision === opt.value ? '1px solid var(--accent-green)' : '1px solid var(--border)' }}>
                          <input type="radio" name="decision" value={opt.value} checked={decision === opt.value} onChange={e => setDecision(e.target.value)} />
                          <span style={{ fontSize: '0.85rem' }}>{opt.label}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleSubmitDecision} disabled={!decision || savingDecision}>
                    {savingDecision ? '⟳ Menyimpan...' : 'Simpan Keputusan'}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="grid-2" style={{ gap: '1.5rem' }}>
        <div className="flex-col" style={{ gap: '1.5rem', display: 'flex' }}>
          <div className="card">
         <div className="card-title">Dasar Penilaian</div>
            <p className="text-xs text-muted mb-2">
               Temuan berikut berasal dari aturan dan pemeriksaan terukur. Ringkasan otomatis tidak mengubah nilai risiko.
            </p>
            {deterministicEvidence.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                {deterministicEvidence.map(item => (
                  <div key={item.evidence_id} style={{ padding: '0.65rem 0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, borderLeft: '3px solid var(--accent-green)' }}>
                    <div className="text-xs" style={{ fontWeight: 700 }}>
                      {RULE_LABELS[item.signal_type] || SIGNAL_LABELS[item.signal_type] || plainText(item.signal_type)}
                    </div>
                    <div className="text-sm" style={{ marginTop: 3 }}>{plainText(item.explanation)}</div>
                  </div>
                ))}
              </div>
            ) : (
               <div className="text-sm text-muted">Belum ada temuan yang mendukung tingkat prioritas.</div>
            )}
          </div>

          {/* Narasi Sistem */}
          <div className="card">
            <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
               Ringkasan Pemeriksaan
            </div>
            <div className="qa-answer mb-2" style={{ marginTop: 0 }}>
               {plainText(explanation?.narrative_id) || 'Ringkasan tidak tersedia.'}
            </div>
            <div className="text-xs text-muted mb-3" style={{ borderBottom: '1px solid var(--border)', paddingBottom: '1rem' }}>
              <span style={{ color: 'var(--accent-green)' }}>
                 Angka dalam ringkasan dicocokkan dengan data klaim. Ringkasan ini membantu menentukan prioritas, bukan menggantikan keputusan petugas.
              </span>
            </div>

            <div className="card-title" style={{ fontSize: '0.75rem', marginBottom: '0.5rem' }}>Pertanyaan Panduan Verifikasi</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {[
                { label: 'Kenapa klaim ini mendapat prioritas ini?', key: 'why_top_priority' },
                { label: 'Apa temuan terkuat dari analisis?', key: 'strongest_evidence' },
                { label: 'Apakah ada klaim serupa sebelumnya?', key: 'most_similar_claim' },
                 { label: 'Apakah temuan ini sudah dikonfirmasi?', key: 'is_this_fraud' }
              ].map(q => (
                <details key={q.key} style={{ background: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border)', overflow: 'hidden' }}>
                  <summary className="assessment-qa-summary" style={{ padding: '0.75rem 1rem', fontSize: '0.8rem', cursor: 'pointer', fontWeight: 500 }}>
                    {q.label}
                  </summary>
                  <div style={{ padding: '1rem', borderTop: '1px solid var(--border)', fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.6, background: 'var(--bg-card)' }}>
                     {plainText(explanation?.qa_panel?.[q.key]) || '—'}
                  </div>
                </details>
              ))}
            </div>
          </div>

          {/* Hanya relasi repeat billing atau cloning yang ditampilkan.
              Skor komposit mengurutkan kandidat yang sudah lolos aturan relasi. */}
           <div className="card">
             <div className="card-title">Riwayat Klaim Serupa</div>
             <p className="text-xs text-muted mb-2">
                Pengulangan klaim (pasien &amp; tindakan sama dalam 45 hari) dan kemiripan tidak wajar antar-klaim ditampilkan di sini.
                Klik baris untuk melihat alasan kemiripannya.
             </p>
             {fraud?.repeat_billing_matched_claim_id && (
               <div
                 className="text-sm mb-2"
                 style={{ padding: '0.65rem 0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, borderLeft: '3px solid var(--risk-high)' }}
               >
                 <strong>Klaim berulang terdeteksi: {fraud.repeat_billing_matched_claim_id}</strong>
                 <div className="text-xs text-muted" style={{ marginTop: '0.25rem' }}>
                   Pasien dan tindakan yang sama ditemukan dalam rentang 45 hari. Periksa dokumen sumber sebelum mengambil keputusan.
                 </div>
               </div>
             )}
             {similarClaims.length > 0 ? (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">ID Klaim</th>
                      <th scope="col">Diagnosis</th>
                        <th scope="col">Biaya yang diajukan</th>
                      <th scope="col">Kemiripan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {similarClaims.map(sc => (
                      <Fragment key={sc.claim_id}>
                        <tr
                        >
                          <td className="font-mono" style={{ fontSize: '0.75rem' }}>
                            <button
                              type="button"
                              className="similar-claim-toggle"
                              aria-label={`Buka rincian faktor kemiripan untuk klaim ${sc.claim_id}`}
                              aria-expanded={expandedSimilar === sc.claim_id}
                              aria-controls={`similar-claim-${sc.claim_id}`}
                              onClick={() => setExpandedSimilar(expandedSimilar === sc.claim_id ? null : sc.claim_id)}
                              title="Buka rincian faktor kemiripan"
                              style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', width: '100%', border: 0, background: 'transparent', color: 'inherit', textAlign: 'left', cursor: 'pointer' }}
                            >
                              {expandedSimilar === sc.claim_id ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
                              {sc.claim_id}
                            </button>
                            {sc.same_patient && (
                              <div style={{ fontSize: '0.6rem', color: 'var(--error-text)' }}>pasien sama</div>
                            )}
                          </td>
                          <td><span className="badge badge-blue" style={{ fontSize: '0.65rem' }}>{sc.diagnosis_primary || '—'}</span></td>
                          <td style={{ fontSize: '0.78rem' }}>{fmtRp(sc.cost_claimed)}</td>
                          <td>
                            <div className="flex items-center gap-1">
                              <div className="progress-bar" style={{ width: 40, height: 4 }}>
                                <div className="progress-fill" style={{ width: `${sc.similarity * 100}%`, background: sc.similarity > 0.85 ? 'var(--risk-high)' : 'var(--accent-green)' }} />
                              </div>
                              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{(sc.similarity * 100).toFixed(0)}%</span>
                            </div>
                          </td>
                        </tr>
                        {expandedSimilar === sc.claim_id && (
                          <tr>
                            <td id={`similar-claim-${sc.claim_id}`} colSpan={4} style={{ background: 'var(--bg-secondary)', padding: '0.75rem 1rem' }}>
                               <div style={{ fontSize: '0.68rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                                 Alasan kemiripan
                              </div>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                                 <span className="badge badge-blue" style={{ fontSize: '0.65rem' }} title="Kesesuaian kode diagnosis dan tindakan">
                                   Diagnosis dan tindakan: {((sc.code_similarity ?? 0) * 100).toFixed(0)}%
                                </span>
                                 <span className={`badge ${(sc.cost_proximity ?? 0) > 0.9 ? 'badge-high' : 'badge-blue'}`} style={{ fontSize: '0.65rem' }} title="Kedekatan jumlah biaya">
                                  Kedekatan biaya: {((sc.cost_proximity ?? 0) * 100).toFixed(0)}%
                                </span>
                                 <span className={`badge ${sc.same_provider ? 'badge-high' : 'badge-low'}`} style={{ fontSize: '0.65rem' }} title="Kesesuaian fasilitas kesehatan">
                                   Fasilitas kesehatan: {sc.same_provider ? `sama${sc.provider_id ? ` (${sc.provider_id})` : ''}` : 'berbeda'}
                                </span>
                                 <span className={`badge ${sc.days_apart != null && sc.days_apart <= 7 ? 'badge-high' : 'badge-low'}`} style={{ fontSize: '0.65rem' }} title="Jarak tanggal klaim">
                                  Jarak waktu: {sc.days_apart != null ? `${sc.days_apart} hari` : 'tidak diketahui'}
                                </span>
                                 <span className={`badge ${sc.same_patient ? 'badge-high' : 'badge-low'}`} style={{ fontSize: '0.65rem' }} title="Kesesuaian peserta">
                                   Peserta: {sc.same_patient ? `sama${sc.patient_id ? ` (${sc.patient_id})` : ''}` : 'berbeda'}
                                </span>
                              </div>
                              <div className="text-xs text-muted" style={{ marginTop: '0.5rem' }}>
                                Faktor berwarna merah menunjukkan konteks yang mendukung investigasi. Pola klinis lintas faskes tidak ditampilkan sebagai kandidat cloning.
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-sm text-muted text-center p-4">
                {fraud?.repeat_billing_matched_claim_id
                  ? 'Tidak ada kandidat vector tambahan; pasangan repeat billing ditampilkan di atas.'
                  : fraud?.similarity_matched_claim_id
                  ? `Klaim paling mirip: ${fraud.similarity_matched_claim_id} (${((fraud.similarity_max_score || 0) * 100).toFixed(0)}%)`
                   : 'Tidak ada kandidat pengulangan klaim atau kemiripan tidak wajar. Kemiripan pola penyakit semata dianggap wajar.'}
              </div>
            )}
          </div>
        </div>

        <div className="flex-col" style={{ gap: '1.5rem', display: 'flex' }}>
           {/* Grafik bagian yang memengaruhi nilai risiko */}
          <div className="card">
             <div className="card-title">Bagian yang Memengaruhi Nilai Risiko</div>
            <p className="text-xs text-muted mb-2">Bagian pemeriksaan yang paling memengaruhi tingkat prioritas klaim.</p>
            <div style={{ height: 250, width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={shapData} layout="vertical" margin={{ top: 5, right: 30, left: 120, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={true} vertical={false} />
                  <XAxis type="number" stroke="var(--text-muted)" fontSize={11} />
                  <YAxis dataKey="name" type="category" stroke="var(--text-muted)" fontSize={11} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={120} />
                  <Tooltip
                    contentStyle={{ backgroundColor: 'var(--bg-card)', borderColor: 'var(--border)', borderRadius: 8, fontSize: '0.8rem' }}
                    itemStyle={{ color: 'var(--text-primary)' }}
                    formatter={(value) => [`${Number(value).toFixed(1)} poin`, 'Kontribusi']}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                    {shapData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.value > 0 ? 'var(--risk-high)' : 'var(--success)'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

           {/* Faktor yang memengaruhi perkiraan biaya */}
          {shapFeatures.length > 0 && (
            <div className="card">
                <div className="card-title">Faktor yang Memengaruhi Perkiraan Biaya</div>
               <p className="text-xs text-muted mb-2">
                  Faktor yang paling memengaruhi perkiraan biaya untuk kasus ini.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                {shapFeatures.map((f, i) => (
                  <div key={i}>
                    <div className="flex justify-between text-xs mb-1">
                       <span>{plainText(f.feature_label || formatFeature(f.feature_name))}</span>
                       <span style={{ fontWeight: 600, color: f.direction === 'positive' ? 'var(--error-text)' : 'var(--success)' }}>
                          {f.direction === 'positive' ? '↑ perkiraan biaya lebih tinggi' : '↓ perkiraan biaya lebih rendah'}
                      </span>
                    </div>
                    <div className="progress-bar" style={{ height: 5 }}>
                      <div className="progress-fill" style={{
                        width: `${Math.min(100, (f.contribution / (shapFeatures[0]?.contribution || 1)) * 100)}%`,
                        background: f.direction === 'positive' ? 'var(--risk-high)' : 'var(--accent-green)',
                      }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Catatan Temuan */}
          <div className="card">
             <div className="card-title">Catatan Temuan</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, borderLeft: '3px solid var(--accent-green)' }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.25rem', textTransform: 'uppercase', display: 'flex', justifyContent: 'space-between' }}>
                   <span>Temuan Medis</span>
                    <span>{clinical?.evidence_source === 'llm_local' ? 'Catatan tambahan' : clinical?.evidence_source === 'fallback_no_data' ? 'Belum tersedia' : 'Aturan pemeriksaan'}</span>
                </div>
                  <div style={{ fontSize: '0.82rem' }}>{plainText(clinical?.evidence_text, 'clinical') || 'Tidak ada temuan medis yang signifikan.'}</div>
              </div>
               <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, borderLeft: '3px solid var(--warning-text)' }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.25rem', textTransform: 'uppercase', display: 'flex', justifyContent: 'space-between' }}>
                     <span>Temuan Perkiraan Biaya</span>
                     <span>{financial?.method === 'zscore_peer_fallback' ? 'Rata-rata sejenis' : (financial?.anomaly_score === 0 && financial?.deviation_pct === 0) ? 'Belum tersedia' : 'Perkiraan biaya'}</span>
                </div>
                  <div style={{ fontSize: '0.82rem' }}>{plainText(financial?.evidence_text, 'financial') || 'Biaya berada dalam kisaran yang wajar.'}</div>
              </div>
               <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, borderLeft: '3px solid var(--error-text)' }}>
                 <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.25rem', textTransform: 'uppercase' }}>Temuan Pola Klaim</div>
                  <div style={{ fontSize: '0.82rem' }}>{plainText(fraud?.evidence_text, 'fraud') || 'Tidak ditemukan pola pengulangan klaim yang perlu ditindaklanjuti.'}</div>
              </div>
              <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, borderLeft: '3px solid var(--border)' }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.25rem', textTransform: 'uppercase', display: 'flex', justifyContent: 'space-between' }}>
                   <span>Ringkasan Temuan</span>
                   <span>{review?.reasoning_source === 'rule_fallback' ? 'Aturan pemeriksaan' : 'Analisis tambahan'}</span>
                </div>
                  <div style={{ fontSize: '0.82rem' }}>{plainText(review?.reasoning_narrative, 'review') || '—'}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
