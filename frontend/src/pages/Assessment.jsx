import { useState, useEffect, useRef, Fragment } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { RefreshCw, ChevronDown, ChevronRight, Check } from 'lucide-react'
import { claimsApi, formatRecommendedAction, formatFeature, ANALYSIS_VERSION, safeErrorMessage, publicAnalysisProjection } from '../api'
import { COMPONENT_LABELS as PLAIN_COMPONENT_LABELS, RULE_LABELS, SIGNAL_LABELS, humanizeText } from '../humanLanguage'

// Maps for technical terms -> human readable
const COMPONENT_LABELS = PLAIN_COMPONENT_LABELS

// Warna komponen skor — satu jengkal hijau AEGIS (ramp monokrom, bukan pelangi)
const COMPONENT_COLORS = {
  financial_anomaly: '#065f46',
  similarity_fraud: '#047857',
  evidence_support: '#10b981',
  clinical_rule_flags: '#34d399',
  isolation_forest_anomaly: '#6ee7b7',
}

const EVIDENCE_LEVEL_LABELS = {
  strong_multi_signal: 'Banyak Indikasi Kuat',
  single_signal: 'Satu Indikasi',
  weak: 'Bukti Belum Menguat',
}

const fmtRp = (x) => `Rp ${Math.round(x || 0).toLocaleString('id-ID')}`
const fmtScore = (x) => Number(x || 0).toLocaleString('id-ID', { maximumFractionDigits: 1 })

// Rp ringkas utk label grafik: 1.499.706 -> Rp1,5 jt
const fmtRpShort = (x) => {
  const v = Math.abs(x || 0)
  const s = v >= 1e9
    ? `${(v / 1e9).toLocaleString('id-ID', { maximumFractionDigits: 2 })} M`
    : v >= 1e6
      ? `${(v / 1e6).toLocaleString('id-ID', { maximumFractionDigits: 2 })} jt`
      : v >= 1e3
        ? `${Math.round(v / 1e3).toLocaleString('id-ID')} rb`
        : `${Math.round(v)}`
  return `Rp${s}`
}

// Temuan sering mengulang judulnya ("Temuan berdasarkan aturan pemeriksaan: X" di bawah judul X) — buang gema tersebut
const stripEchoPrefix = (t) => String(t || '')
  .replace(/^(?:Sinyal deterministik|Temuan berdasarkan aturan pemeriksaan|Temuan pola klaim)\s*[:.]\s*/i, '')

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

  if (!data) {
    return (
      <div className="status-message loading-state" role="status" aria-live="polite">
        <span className="loading-spinner" aria-hidden="true" />
        <p>Memuat hasil analisis…</p>
      </div>
    )
  }

  const { risk, explanation, clinical, financial, fraud, review } = data
  const tierColor = { high: 'var(--risk-high)', medium: 'var(--risk-medium)', low: 'var(--risk-low)' }
  const tierLabel = { high: 'Prioritas Tinggi', medium: 'Prioritas Sedang', low: 'Prioritas Rendah' }

  // Komposisi skor — komponen bernilai 0 tetap tampil di legenda
  const composition = Object.entries(risk.breakdown || {})
    .map(([key, val]) => ({
      key,
      name: COMPONENT_LABELS[key] || key,
      value: Math.max(0, Number(val) || 0),
      color: COMPONENT_COLORS[key] || '#a7f3d0',
    }))
    .sort((a, b) => b.value - a.value)

  // Faktor biaya (SHAP) — nilai Rp asli dari model
  const shapFeatures = financial?.shap_top_features || []
  const shapMax = Math.max(1, ...shapFeatures.map(f => Math.abs(Number(f.contribution) || 0)))

  const similarClaims = fraud?.similar_claims || []
  const deterministicEvidence = (risk?.evidence || [])
    .filter(item => item.source_family !== 'behavioral_context')
  const ruleFlagCount = clinical?.rule_flags?.length || 0

  const DECISION_OPTIONS = [
    { value: 'Verified Valid', label: 'Klaim valid — setujui' },
    { value: 'Needs Further Review', label: 'Perlu peninjauan lebih lanjut' },
    { value: 'Escalate', label: 'Eskalasi ke supervisor' },
    { value: 'Request Clarification', label: 'Minta klarifikasi ke faskes' },
  ]
  const DECISION_LABELS = Object.fromEntries(DECISION_OPTIONS.map(o => [o.value, o.label]))

  return (
    <div className="asm-page">
      <div className="page-header asm-topbar">
        <div>
          <h1>Hasil Pemeriksaan Klaim</h1>
          <p className="font-mono text-sm" style={{ color: 'var(--text-muted)' }}>Klaim: {claimId}</p>
        </div>
        <div className="page-actions">
          <button className="btn btn-ghost" onClick={handleRerun} title="Hapus hasil lama dan periksa kembali">
            <RefreshCw size={14} aria-hidden="true" /> Periksa Ulang
          </button>
          <button className="btn btn-ghost" onClick={() => navigate('/claims')}>
            ← Daftar Klaim
          </button>
        </div>
      </div>

      {analysisError && (
        <div className="alert-disclaimer mb-3" role="alert">
          <strong>Hasil pemeriksaan terbaru belum dapat dimuat.</strong> {analysisError}
          <button className="btn btn-ghost" style={{ marginLeft: '0.75rem' }} onClick={handleAnalysisRetry}>Coba muat lagi</button>
        </div>
      )}

      {data.partial && (
        <div className="alert-disclaimer mb-3" role="alert">
          <strong style={{ color: 'var(--warning-text)' }}>Pemeriksaan belum lengkap</strong> — sebagian data tidak tersedia.
        </div>
      )}

      {/* ---------- Baris 1: skor + keputusan ---------- */}
      <div className="asm-head-grid">
        {/* Skor Risiko */}
        <section className="card asm-score-card" style={{ '--rail': tierColor[risk.priority_tier] }}>
          <div className="asm-score-hero">
            <div>
              <div className="asm-kicker">Skor Risiko</div>
              <div className="asm-hero-num" style={{ color: tierColor[risk.priority_tier] }}>{fmtScore(risk.total_score)}</div>
              <div className="asm-score-of">dari {risk.max_score ?? 85} poin maksimum</div>
            </div>
            <div className="asm-hero-side">
              <span className={`badge badge-${risk.priority_tier}`}>{tierLabel[risk.priority_tier]}</span>
              <div className="asm-hero-action">{formatRecommendedAction(explanation.recommended_action)}</div>
              <div className="asm-hero-sub">
                {ruleFlagCount > 0 ? `${ruleFlagCount} temuan medis perlu diperhatikan` : 'Tanpa temuan medis'}
              </div>
            </div>
          </div>

          {/* Penggaris zona risiko 0-100 (high ≥60, medium ≥25) */}
          <div
            className="asm-ruler"
            role="img"
            aria-label={`Skor ${fmtScore(risk.total_score)} dari 100, ${tierLabel[risk.priority_tier]}`}
          >
            <div className="asm-ruler-track">
              <i className="asm-zone asm-zone-low" style={{ width: '25%' }} />
              <i className="asm-zone asm-zone-med" style={{ width: '35%' }} />
              <i className="asm-zone asm-zone-high" style={{ width: '40%' }} />
              <b className="asm-needle" style={{ left: `${Math.min(100, Math.max(0, risk.total_score))}%` }} />
            </div>
            <div className="asm-ruler-ticks" aria-hidden="true">
              <span>0</span><span>25</span><span>60</span><span>100</span>
            </div>
            <div className="asm-ruler-zones" aria-hidden="true">
              <span style={{ width: '25%' }}>Rendah</span>
              <span style={{ width: '35%' }}>Sedang</span>
              <span style={{ width: '40%' }}>Tinggi</span>
            </div>
          </div>

          {/* Fakta ringkas klaim */}
          <div className="asm-quickstats">
            <div className="asm-quick-stat">
              <span>Pengaruh terbesar</span>
              <b>{composition[0]?.name || '—'}</b>
            </div>
            <div className="asm-quick-stat">
              <span>Selisih biaya</span>
              <b>{financial?.deviation_pct != null ? `+${fmtScore(financial.deviation_pct)}%` : '—'}</b>
            </div>
            <div className="asm-quick-stat">
              <span>Klaim serupa</span>
              <b>{similarClaims.length > 0 ? `${similarClaims.length} kandidat` : '—'}</b>
            </div>
          </div>
        </section>

        {/* Keputusan Verifier */}
        <section className="card asm-decision-card">
          <div className="card-title">Keputusan Verifier</div>
          {submitted ? (
            <div className="asm-confirmed">
              <div className="asm-confirmed-icon" aria-hidden="true"><Check size={18} /></div>
              <div>
                <div className="asm-confirmed-title">{DECISION_LABELS[existingDecision?.decision] || existingDecision?.decision}</div>
                <div className="asm-confirmed-sub">
                  {existingDecision?.verified_at && (
                    <>Diputuskan {new Date(existingDecision.verified_at).toLocaleString('id-ID')} · {existingDecision.reviewer}</>
                  )}
                </div>
                {decisionLoadError && (
                  <div className="status-message error" role="alert" style={{ marginTop: '0.5rem', textAlign: 'left' }}>
                    <strong>Riwayat keputusan belum dapat diperbarui</strong>
                    <p>{decisionLoadError}</p>
                    <button className="btn btn-outline" style={{ marginTop: '0.5rem' }} onClick={handleDecisionRetry}>Muat lagi</button>
                  </div>
                )}
              </div>
              <button className="btn btn-ghost asm-confirm-change" onClick={() => { setSubmitted(false); setExistingDecision(null) }}>
                Ubah
              </button>
            </div>
          ) : decisionLoadError ? (
            <div className="status-message error" role="alert" style={{ padding: '1rem' }}>
              <strong>Riwayat keputusan belum dapat dimuat</strong>
              <p>{decisionLoadError}</p>
              <button className="btn btn-outline" style={{ marginTop: '0.75rem' }} onClick={handleDecisionRetry}>Muat lagi</button>
            </div>
          ) : (
            <fieldset className="assessment-decision-fieldset">
              <legend className="sr-only">Keputusan Petugas Verifier</legend>
              {decisionError && (
                <div className="status-message error" role="alert" style={{ padding: '0.75rem', marginBottom: '0.75rem' }}>
                  <strong>Keputusan belum tersimpan</strong>
                  <p>{decisionError}</p>
                  <button className="btn btn-outline" style={{ marginTop: '0.5rem' }} onClick={handleSubmitDecision} disabled={savingDecision}>Coba simpan lagi</button>
                </div>
              )}
              <div className="asm-options" aria-busy={loadingDecision}>
                {DECISION_OPTIONS.map(opt => (
                  <label key={opt.value} className="assessment-decision-option" data-checked={decision === opt.value || undefined}>
                    <input
                      type="radio"
                      name="decision"
                      value={opt.value}
                      checked={decision === opt.value}
                      disabled={loadingDecision}
                      onChange={e => setDecision(e.target.value)}
                    />
                    <span>{opt.label}</span>
                  </label>
                ))}
              </div>
              <button className="btn btn-primary asm-save" onClick={handleSubmitDecision} disabled={!decision || savingDecision || loadingDecision}>
                {savingDecision ? 'Menyimpan…' : 'Simpan Keputusan'}
              </button>
            </fieldset>
          )}
        </section>
      </div>

      {/* ---------- Baris 2: dokumen kiri / grafik kanan ---------- */}
      <div className="asm-body-grid">
        <div className="asm-col">
          {/* Temuan Utama */}
          <section className="card">
            <div className="asm-title-row">
              <div className="card-title" style={{ marginBottom: 0 }}>Temuan Utama</div>
              {deterministicEvidence.length > 0 && <span className="asm-count">{deterministicEvidence.length} temuan</span>}
            </div>
            {deterministicEvidence.length > 0 ? (
              <ol className="asm-findings">
                {deterministicEvidence.map((item, i) => {
                  const label = RULE_LABELS[item.signal_type] || SIGNAL_LABELS[item.signal_type] || plainText(item.signal_type)
                  return (
                  <li key={item.evidence_id}>
                    <span className="asm-findex" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
                    <div>
                      <div className="asm-ftitle">{label}</div>
                      {(() => {
                        const body = plainText(stripEchoPrefix(item.explanation))
                        const norm = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '')
                        // Sembunyikan isi yang cuma segema judul ("lama rawat jauh…" di bawah "Lama rawat jauh…")
                        if (!body || norm(body) === norm(label)) return null
                        return <p className="asm-ftext">{body}</p>
                      })()}
                    </div>
                  </li>
                  )
                })}
              </ol>
            ) : (
              <p className="asm-empty">Belum ada temuan yang mendukung tingkat prioritas.</p>
            )}
          </section>

          {/* Ringkasan + QA */}
          <section className="card">
            <div className="card-title">Ringkasan Pemeriksaan</div>
            <div className="asm-narrative">
              {plainText(explanation?.narrative_id) || 'Ringkasan tidak tersedia.'}
            </div>
            <p className="asm-footnote asm-footnote-line">
              Angka sesuai data klaim · bukan pengganti keputusan petugas.
            </p>

            <div className="asm-qa-title">Panduan Verifikasi</div>
            <div className="asm-qa">
              {[
                { label: 'Kenapa klaim ini mendapat prioritas ini?', key: 'why_top_priority' },
                { label: 'Apa temuan terkuat dari analisis?', key: 'strongest_evidence' },
                { label: 'Apakah ada klaim serupa sebelumnya?', key: 'most_similar_claim' },
                { label: 'Apakah temuan ini sudah dikonfirmasi?', key: 'is_this_fraud' },
              ].map(q => (
                <details key={q.key} className="asm-qa-item">
                  <summary className="assessment-qa-summary">
                    <ChevronRight className="asm-qa-caret" size={13} aria-hidden="true" />
                    {q.label}
                  </summary>
                  <div className="asm-qa-body">{plainText(explanation?.qa_panel?.[q.key]) || '—'}</div>
                </details>
              ))}
            </div>
          </section>

          {/* Klaim Serupa */}
          <section className="card">
            <div className="asm-title-row">
              <div className="card-title" style={{ marginBottom: 0 }}>Klaim Serupa</div>
              {similarClaims.length > 0 && <span className="asm-count">{similarClaims.length} kandidat</span>}
            </div>
            {fraud?.repeat_billing_matched_claim_id && (
              <div className="asm-repeat">
                <strong>Klaim berulang: {fraud.repeat_billing_matched_claim_id}</strong>
                <span>Pasien &amp; tindakan sama dalam 45 hari — periksa dokumen sumber.</span>
              </div>
            )}
            <p className="asm-footnote">Klik baris untuk melihat faktor kemiripan.</p>
            {similarClaims.length > 0 ? (
              <div className="asm-table-wrap">
                <table className="asm-table">
                  <thead>
                    <tr>
                      <th scope="col">ID Klaim</th>
                      <th scope="col">Diagnosis</th>
                      <th scope="col">Biaya</th>
                      <th scope="col">Kemiripan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {similarClaims.map(sc => (
                      <Fragment key={sc.claim_id}>
                        <tr>
                          <td>
                            <button
                              type="button"
                              className="similar-claim-toggle"
                              aria-label={`Buka rincian faktor kemiripan untuk klaim ${sc.claim_id}`}
                              aria-expanded={expandedSimilar === sc.claim_id}
                              aria-controls={`similar-claim-${sc.claim_id}`}
                              onClick={() => setExpandedSimilar(expandedSimilar === sc.claim_id ? null : sc.claim_id)}
                            >
                              {expandedSimilar === sc.claim_id ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
                              <span className="font-mono">{sc.claim_id}</span>
                              {sc.same_patient && <em className="asm-sim-flag">pasien sama</em>}
                            </button>
                          </td>
                          <td><span className="asm-dx">{sc.diagnosis_primary || '—'}</span></td>
                          <td className="asm-num">{fmtRp(sc.cost_claimed)}</td>
                          <td>
                            <div className="asm-sim-cell">
                              <div className="asm-sim-bar" aria-hidden="true">
                                <i style={{
                                  width: `${Math.round((sc.similarity || 0) * 100)}%`,
                                  background: sc.similarity > 0.85 ? 'var(--risk-high)' : 'var(--accent-green)',
                                }} />
                              </div>
                              <span className="asm-num asm-sim-pct">{(sc.similarity * 100).toFixed(0)}%</span>
                            </div>
                          </td>
                        </tr>
                        {expandedSimilar === sc.claim_id && (
                          <tr>
                            <td id={`similar-claim-${sc.claim_id}`} colSpan={4} className="asm-sim-detail">
                              <div className="asm-sim-reason-title">Faktor kemiripan</div>
                              <div className="asm-sim-chips">
                                <span className="asm-chip" title="Kesesuaian kode diagnosis dan tindakan">
                                  Kode: {((sc.code_similarity ?? 0) * 100).toFixed(0)}%
                                </span>
                                <span className={`asm-chip ${((sc.cost_proximity ?? 0) > 0.9 ? 'asm-chip-warn' : '')}`} title="Kedekatan jumlah biaya">
                                  Biaya: {((sc.cost_proximity ?? 0) * 100).toFixed(0)}%
                                </span>
                                <span className={`asm-chip ${sc.same_provider ? 'asm-chip-warn' : ''}`} title="Kesesuaian fasilitas kesehatan">
                                  Faskes: {sc.same_provider ? 'sama' : 'berbeda'}
                                </span>
                                <span className={`asm-chip ${sc.days_apart != null && sc.days_apart <= 7 ? 'asm-chip-warn' : ''}`} title="Jarak tanggal klaim">
                                  Jarak: {sc.days_apart != null ? `${sc.days_apart} hari` : '?'}
                                </span>
                                <span className={`asm-chip ${sc.same_patient ? 'asm-chip-warn' : ''}`} title="Kesesuaian peserta">
                                  Peserta: {sc.same_patient ? 'sama' : 'berbeda'}
                                </span>
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
              <p className="asm-empty">
                {fraud?.repeat_billing_matched_claim_id
                  ? 'Pasangan repeat billing ditampilkan di atas.'
                  : fraud?.similarity_matched_claim_id
                    ? `Klaim paling mirip: ${fraud.similarity_matched_claim_id} (${((fraud.similarity_max_score || 0) * 100).toFixed(0)}%)`
                    : 'Tidak ada pengulangan atau kemiripan yang tidak wajar.'}
              </p>
            )}
          </section>
        </div>

        <div className="asm-col">
          {/* Komposisi Skor */}
          <section className="card">
            <div className="card-title">Komposisi Skor Risiko</div>
            <div
              className="asm-stack"
              role="img"
              aria-label={`Skor ${fmtScore(risk.total_score)} dari 100 tersusun dari ${composition.map(c => `${c.name} ${fmtScore(c.value)}`).join(', ')}`}
            >
              {composition.filter(c => c.value > 0).map(c => (
                <i
                  key={c.key}
                  style={{ width: `${c.value}%`, background: c.color }}
                  title={`${c.name}: ${fmtScore(c.value)}`}
                />
              ))}
            </div>
            <ul className="asm-legend">
              {composition.map(c => (
                <li key={c.key}>
                  <i style={{ background: c.color }} aria-hidden="true" />
                  <span>{c.name}</span>
                  <b className="asm-num">{c.value > 0 ? `${fmtScore(c.value)} poin` : '—'}</b>
                </li>
              ))}
              <li className="asm-legend-total">
                <i aria-hidden="true" />
                <span>Tersusun dari 100</span>
                <b className="asm-num">{fmtScore(risk.total_score)}</b>
              </li>
            </ul>
          </section>

          {/* Faktor Perkiraan Biaya — diverging Rp */}
          {shapFeatures.length > 0 && (
            <section className="card">
              <div className="asm-title-row">
                <div className="card-title" style={{ marginBottom: 0 }}>Faktor Perkiraan Biaya</div>
                <div className="asm-div-legend" aria-hidden="true">
                  <span className="up">↑ menaikkan</span>
                  <span className="down">↓ menurunkan</span>
                </div>
              </div>
              <div className="asm-div">
                {shapFeatures.map((f, i) => {
                  const contribution = Number(f.contribution) || 0
                  const positive = f.direction === 'positive'
                  // % dari track penuh; bar pendek tetap mencapai 8% supaya terlihat
                  const width = Math.min(100, Math.max(8, (Math.abs(contribution) / shapMax) * 100))
                  return (
                    <div
                      key={i}
                      className="asm-div-row"
                      style={positive ? { '--w': `${width}%`, '--bar': 'var(--risk-high)' } : { '--w': `${width}%`, '--bar': 'var(--accent-green)' }}
                      data-dir={positive ? 'up' : 'down'}
                    >
                      <span className="asm-div-name">{plainText(f.feature_label || formatFeature(f.feature_name))}</span>
                      <div className="asm-div-track" aria-hidden="true"><i className="asm-div-bar" /></div>
                      <span className={`asm-div-val ${positive ? 'up' : 'down'}`}>
                        {positive ? '↑' : '↓'} {fmtRpShort(contribution)}
                      </span>
                    </div>
                  )
                })}
              </div>
              <p className="asm-footnote asm-footnote-line">Pengaruh tiap faktor terhadap perkiraan biaya penggantian.</p>
            </section>
          )}

          {/* Catatan Temuan */}
          <section className="card">
            <div className="card-title">Catatan Temuan</div>
            <ul className="asm-notes">
              <li>
                <div className="asm-note-head">
                  <span className="asm-note-title">Temuan Medis</span>
                  <span className="asm-note-src">{clinical?.evidence_source === 'llm_local' ? 'Catatan tambahan' : clinical?.evidence_source === 'fallback_no_data' ? 'Belum tersedia' : 'Aturan pemeriksaan'}</span>
                </div>
                <p>{plainText(clinical?.evidence_text, 'clinical') || 'Tidak ada temuan yang signifikan.'}</p>
              </li>
              <li>
                <div className="asm-note-head">
                  <span className="asm-note-title">Perkiraan Biaya</span>
                  <span className="asm-note-src">{financial?.method === 'zscore_peer_fallback' ? 'Rata-rata sejenis' : (financial?.anomaly_score === 0 && financial?.deviation_pct === 0) ? 'Belum tersedia' : 'Perkiraan biaya'}</span>
                </div>
                <p>{plainText(financial?.evidence_text, 'financial') || 'Biaya berada dalam kisaran wajar.'}</p>
              </li>
              <li>
                <div className="asm-note-head">
                  <span className="asm-note-title">Pola Klaim</span>
                </div>
                <p>{plainText(fraud?.evidence_text, 'fraud') || 'Tidak ada pola pengulangan yang perlu ditindaklanjuti.'}</p>
              </li>
              <li>
                <div className="asm-note-head">
                  <span className="asm-note-title">Ringkasan</span>
                  <span className="asm-note-src">{review?.reasoning_source === 'rule_fallback' ? 'Aturan pemeriksaan' : 'Analisis tambahan'}</span>
                </div>
                <p>{plainText(review?.reasoning_narrative, 'review') || '—'}</p>
              </li>
            </ul>
          </section>
        </div>
      </div>

      <p className="asm-disclaimer">Sistem hanya membantu menentukan prioritas — keputusan akhir tetap di petugas verifier BPJS.</p>
    </div>
  )
}
