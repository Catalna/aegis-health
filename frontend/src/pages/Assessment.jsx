import { useState, useEffect, Fragment } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts'
import { RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'
import { claimsApi, formatRecommendedAction, formatFeature, ANALYSIS_VERSION } from '../api'

// Maps for technical terms -> human readable
const COMPONENT_LABELS = {
  similarity_fraud: 'Kemiripan Riwayat Klaim',
  clinical_rule_flags: 'Kewajaran Medis (Rule)',
  isolation_forest_anomaly: 'Anomali Pola Perilaku',
  synthesis_confidence: 'Keyakinan Sistem',
  financial_anomaly: 'Anomali Finansial',
}

const EVIDENCE_LEVEL_LABELS = {
  strong_multi_signal: 'Banyak Indikasi Kuat',
  single_signal: 'Satu Indikasi',
  weak: 'Tidak Ada Indikasi',
}

const fmtRp = (x) => `Rp ${Math.round(x || 0).toLocaleString('id-ID')}`

export default function Assessment() {
  const { claimId } = useParams()
  const navigate = useNavigate()

  const [data, setData] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const [stale, setStale] = useState(false)
  const [expandedSimilar, setExpandedSimilar] = useState(null)
  const [decision, setDecision] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [existingDecision, setExistingDecision] = useState(null)
  const [loadingDecision, setLoadingDecision] = useState(true)
  const [savingDecision, setSavingDecision] = useState(false)

  // Load analysis result: sessionStorage → fallback DB.
  // Guard versi: hasil dengan analysis_version berbeda = stale (dihitung
  // logika engine lama) → jangan ditampilkan, minta analisis ulang.
  useEffect(() => {
    const stored = sessionStorage.getItem(`result_${claimId}`)
    if (stored) {
      try {
        const parsed = JSON.parse(stored)
        if (parsed.analysis_version === ANALYSIS_VERSION) {
          setData(parsed)
          return
        }
        sessionStorage.removeItem(`result_${claimId}`)
      } catch { /* fallthrough */ }
    }
    claimsApi.getAnalysis(claimId).then(res => {
      const existing = res.data
      if (existing.status === 'analyzed' && existing.result?.risk && existing.result?.explanation) {
        if (existing.result.analysis_version !== ANALYSIS_VERSION) {
          setStale(true)
          setNotFound(true)
          return
        }
        const rebuilt = {
          analysis_version: existing.result.analysis_version,
          clinical: existing.result.clinical,
          financial: existing.result.financial,
          fraud: existing.result.fraud,
          review: existing.result.review,
          risk: existing.result.risk,
          explanation: existing.result.explanation,
        }
        sessionStorage.setItem(`result_${claimId}`, JSON.stringify(rebuilt))
        setData(rebuilt)
      } else {
        setNotFound(true)
      }
    }).catch(() => setNotFound(true))
  }, [claimId])

  // Keputusan verifier tersimpan di DB — persisten lintas reload
  useEffect(() => {
    const fetchDecision = async () => {
      try {
        const res = await claimsApi.getDecision(claimId)
        if (res.data.status === 'decided') {
          setExistingDecision(res.data)
          setSubmitted(true)
          setDecision(res.data.decision)
        }
      } catch (e) {
        console.warn('Could not fetch existing decision:', e.message)
      } finally {
        setLoadingDecision(false)
      }
    }
    fetchDecision()
  }, [claimId])

  const handleSubmitDecision = async () => {
    if (!decision) return
    setSavingDecision(true)
    try {
      await claimsApi.submitDecision(claimId, {
        claim_id: claimId,
        decision,
        reviewer: 'BPJS-VERIFIER-01',
      })
      setSubmitted(true)
      setExistingDecision({ decision, reviewer: 'BPJS-VERIFIER-01', timestamp: new Date().toISOString() })
    } catch (e) {
      alert('Gagal menyimpan keputusan. Pastikan backend aktif.')
    } finally {
      setSavingDecision(false)
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

  if (notFound) return (
    <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
      <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>⚠</div>
      {stale ? (
        <>
          <div>Hasil analisis tersimpan dibuat dengan <strong>versi engine yang lama</strong>.</div>
          <p style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>
            Skor kemiripan pada versi lama tidak dapat dipercaya. Jalankan analisis ulang untuk menghitung ulang dengan engine terbaru.
          </p>
        </>
      ) : (
        <p style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>Silakan jalankan investigasi terlebih dahulu dari Daftar Klaim.</p>
      )}
      <button className="btn btn-primary" style={{ marginTop: '1rem' }} onClick={handleRerun}>
        <RefreshCw size={14} /> Analisis Ulang
      </button>
    </div>
  )

  if (!data) return <div className="p-8 text-center text-muted">Memuat hasil analisis...</div>

  const { risk, explanation, clinical, financial, fraud, review } = data
  const tierColor = { high: 'var(--risk-high)', medium: 'var(--risk-medium)', low: 'var(--risk-low)' }

  // Breakdown skor untuk chart
  const shapData = Object.entries(risk.breakdown || {})
    .map(([key, val]) => ({ name: COMPONENT_LABELS[key] || key, value: val }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))

  // SHAP features asli dari model (bukan breakdown bobot)
  const shapFeatures = financial?.shap_top_features || []

  const similarClaims = fraud?.similar_claims || []

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
            <h2>Hasil Analisis Klaim</h2>
            <p className="font-mono text-sm" style={{ color: 'var(--text-muted)' }}>Klaim: {claimId}</p>
          </div>
          <div className="flex gap-1">
            <button className="btn btn-ghost" onClick={handleRerun} title="Reset dan jalankan analisis ulang">
              <RefreshCw size={14} /> Analisis Ulang
            </button>
            <button className="btn btn-ghost" onClick={() => navigate('/claims')}>
              ← Daftar Klaim
            </button>
          </div>
        </div>
      </div>

      {data.partial && (
        <div className="alert-disclaimer mb-3" style={{ borderLeft: '4px solid var(--warning)' }}>
          ⚠ Analisis ini <strong>partial</strong> — sebagian agent gagal dan memakai fallback, sehingga evidence tidak lengkap.
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
              <div className="mb-1">
                <span className={`badge badge-${risk.priority_tier}`}>
                  Prioritas {risk.priority_tier === 'high' ? 'Tinggi' : risk.priority_tier === 'medium' ? 'Sedang' : 'Rendah'}
                </span>
              </div>
              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.2rem' }}>
                {formatRecommendedAction(explanation.recommended_action)}
              </h3>
              <p className="text-muted text-sm">
                {clinical?.rule_flags?.length > 0
                  ? `Flag klinis: ${clinical.rule_flags.join(', ')}`
                  : 'Perlu tinjauan manual'}
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
                  {existingDecision.timestamp && (
                    <p className="text-xs text-muted" style={{ marginTop: '0.25rem' }}>
                      {new Date(existingDecision.timestamp).toLocaleString('id-ID')}
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
            </div>
          ) : (
            <div>
              {loadingDecision ? (
                <div className="text-sm text-muted text-center" style={{ padding: '1rem' }}>
                  Memeriksa riwayat keputusan...
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
                    {DECISION_OPTIONS.map(opt => (
                      <label key={opt.value} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', padding: '0.5rem 0.75rem', background: 'var(--bg-secondary)', borderRadius: '6px', border: decision === opt.value ? '1px solid var(--accent-green)' : '1px solid var(--border)' }}>
                        <input type="radio" name="decision" value={opt.value} checked={decision === opt.value} onChange={e => setDecision(e.target.value)} />
                        <span style={{ fontSize: '0.85rem' }}>{opt.label}</span>
                      </label>
                    ))}
                  </div>
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
          {/* Narasi Sistem */}
          <div className="card">
            <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              Narasi Analisis Sistem
              {explanation?.generated_by && (
                <span className="badge badge-blue" style={{ fontSize: '0.6rem', fontWeight: 400 }}>
                  {explanation.generated_by === 'template_fallback' ? 'template fallback' : `Generated by: ${explanation.generated_by} (local)`}
                </span>
              )}
            </div>
            <div className="qa-answer mb-2" style={{ marginTop: 0 }}>
              {explanation?.narrative_id || 'Narasi tidak tersedia.'}
            </div>
            <div className="text-xs text-muted mb-3" style={{ borderBottom: '1px solid var(--border)', paddingBottom: '1rem' }}>
              <span style={{ color: 'var(--accent-green)' }}>
                Dihasilkan dari bukti terverifikasi — angka divalidasi silang dengan skor sistem; tidak digunakan untuk menghitung skor akhir.
              </span>
            </div>

            <div className="card-title" style={{ fontSize: '0.75rem', marginBottom: '0.5rem' }}>Pertanyaan Panduan Verifikasi</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {[
                { label: 'Kenapa klaim ini mendapat prioritas ini?', key: 'why_top_priority' },
                { label: 'Apa temuan terkuat dari analisis?', key: 'strongest_evidence' },
                { label: 'Apakah ada klaim serupa sebelumnya?', key: 'most_similar_claim' },
                { label: 'Apakah ini sudah dikonfirmasi sebagai fraud?', key: 'is_this_fraud' }
              ].map(q => (
                <details key={q.key} style={{ background: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border)', overflow: 'hidden' }}>
                  <summary style={{ padding: '0.75rem 1rem', fontSize: '0.8rem', cursor: 'pointer', outline: 'none', fontWeight: 500 }}>
                    {q.label}
                  </summary>
                  <div style={{ padding: '1rem', borderTop: '1px solid var(--border)', fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.6, background: 'var(--bg-card)' }}>
                    {explanation?.qa_panel?.[q.key] || '—'}
                  </div>
                </details>
              ))}
            </div>
          </div>

          {/* Riwayat Klaim Mirip — side-by-side dari data nyata.
              Skor = komposit multi-faktor, BUKAN kemiripan penyakit saja:
              kode medis 40% + kedekatan biaya 30% + faskes sama 15%
              + jarak waktu 10% + pasien sama 5%. Klik baris → rincian faktor. */}
          <div className="card">
            <div className="card-title">Riwayat Klaim Serupa</div>
            <p className="text-xs text-muted mb-2">
              Skor komposit: kode medis 40% + kedekatan biaya 30% + faskes sama 15% + jarak waktu 10% + pasien sama 5%.
              Penyakit sama saja <strong>tidak</strong> dianggap mirip. Klik baris untuk melihat rincian faktor.
            </p>
            {similarClaims.length > 0 ? (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>ID Klaim</th>
                      <th>Diagnosis</th>
                      <th>Biaya</th>
                      <th>Kemiripan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {similarClaims.map(sc => (
                      <Fragment key={sc.claim_id}>
                        <tr
                          onClick={() => setExpandedSimilar(expandedSimilar === sc.claim_id ? null : sc.claim_id)}
                          style={{ cursor: 'pointer' }}
                          title="Klik untuk rincian faktor kemiripan"
                        >
                          <td className="font-mono" style={{ fontSize: '0.75rem' }}>
                            <div className="flex items-center gap-1">
                              {expandedSimilar === sc.claim_id ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                              {sc.claim_id}
                            </div>
                            {sc.same_patient && (
                              <div style={{ fontSize: '0.6rem', color: 'var(--risk-high)' }}>pasien sama</div>
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
                            <td colSpan={4} style={{ background: 'var(--bg-secondary)', padding: '0.75rem 1rem' }}>
                              <div style={{ fontSize: '0.68rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                                Mengapa dianggap mirip — rincian faktor
                              </div>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                                <span className="badge badge-blue" style={{ fontSize: '0.65rem' }} title="Jaccard diagnosis + prosedur (bobot 40%)">
                                  Kode medis: {((sc.code_similarity ?? 0) * 100).toFixed(0)}%
                                </span>
                                <span className={`badge ${(sc.cost_proximity ?? 0) > 0.9 ? 'badge-high' : 'badge-blue'}`} style={{ fontSize: '0.65rem' }} title="Kedekatan nominal biaya (bobot 30%)">
                                  Kedekatan biaya: {((sc.cost_proximity ?? 0) * 100).toFixed(0)}%
                                </span>
                                <span className={`badge ${sc.same_provider ? 'badge-high' : 'badge-low'}`} style={{ fontSize: '0.65rem' }} title="Cloning umumnya terjadi di faskes yang sama (bobot 15%)">
                                  Faskes: {sc.same_provider ? `sama${sc.provider_id ? ` (${sc.provider_id})` : ''}` : 'berbeda'}
                                </span>
                                <span className={`badge ${sc.days_apart != null && sc.days_apart <= 7 ? 'badge-high' : 'badge-low'}`} style={{ fontSize: '0.65rem' }} title="Klaim hasil cloning/repeat biasanya berdekatan (bobot 10%)">
                                  Jarak waktu: {sc.days_apart != null ? `${sc.days_apart} hari` : 'tidak diketahui'}
                                </span>
                                <span className={`badge ${sc.same_patient ? 'badge-high' : 'badge-low'}`} style={{ fontSize: '0.65rem' }} title="Pasien sama = indikasi repeat billing (bobot 5%)">
                                  Pasien: {sc.same_patient ? `sama${sc.patient_id ? ` (${sc.patient_id})` : ''}` : 'berbeda'}
                                </span>
                              </div>
                              <div className="text-xs text-muted" style={{ marginTop: '0.5rem' }}>
                                Faktor berwarna merah = konteks mencurigakan. Kemiripan tinggi dengan faskes &amp; pasien berbeda perlu perhatian (indikasi cloning antar-pasien).
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
                {fraud?.similarity_matched_claim_id
                  ? `Klaim paling mirip: ${fraud.similarity_matched_claim_id} (${((fraud.similarity_max_score || 0) * 100).toFixed(0)}%)`
                  : 'Tidak ada klaim historis yang cukup mirip (di bawah ambang komposit 60%) — kemiripan pola penyakit semata dianggap wajar'}
              </div>
            )}
          </div>
        </div>

        <div className="flex-col" style={{ gap: '1.5rem', display: 'flex' }}>
          {/* Grafik Kontribusi Skor */}
          <div className="card">
            <div className="card-title">Faktor Penentu Risiko Utama</div>
            <p className="text-xs text-muted mb-2">Kontribusi setiap komponen analisis terhadap total skor risiko</p>
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

          {/* SHAP attribution asli dari model */}
          {shapFeatures.length > 0 && (
            <div className="card">
              <div className="card-title">Model Attribution (SHAP)</div>
              <p className="text-xs text-muted mb-2">
                Atribusi fitur dari model XGBoost — seberapa besar tiap faktor mendorong prediksi biaya
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                {shapFeatures.map((f, i) => (
                  <div key={i}>
                    <div className="flex justify-between text-xs mb-1">
                      <span>{f.feature_label || formatFeature(f.feature_name)}</span>
                      <span style={{ fontWeight: 600, color: f.direction === 'positive' ? 'var(--risk-high)' : 'var(--success)' }}>
                        {f.direction === 'positive' ? '↑ mendorong biaya naik' : '↓ menahan biaya'}
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
            <div className="card-title">Catatan Temuan Sistem</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, borderLeft: '3px solid var(--accent-green)' }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.25rem', textTransform: 'uppercase', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Temuan Klinis</span>
                  <span>{clinical?.evidence_source === 'llm_local' ? `rule + ${clinical.model_used}` : clinical?.evidence_source === 'fallback_no_data' ? 'fallback' : 'rule engine'}</span>
                </div>
                <div style={{ fontSize: '0.82rem' }}>{clinical?.evidence_text || 'Tidak ada temuan klinis signifikan'}</div>
              </div>
              <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, borderLeft: '3px solid var(--risk-medium)' }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.25rem', textTransform: 'uppercase', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Temuan Keuangan</span>
                  <span>{financial?.method === 'zscore_peer_fallback' ? 'fallback z-score' : 'XGBoost + SHAP'}</span>
                </div>
                <div style={{ fontSize: '0.82rem' }}>{financial?.evidence_text || 'Biaya dalam batas wajar'}</div>
              </div>
              <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, borderLeft: '3px solid var(--risk-high)' }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.25rem', textTransform: 'uppercase' }}>Temuan Anomali Pola</div>
                <div style={{ fontSize: '0.82rem' }}>{fraud?.evidence_text || 'Tidak terdeteksi indikasi penipuan pola berulang'}</div>
              </div>
              <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 8, borderLeft: '3px solid var(--border)' }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.25rem', textTransform: 'uppercase', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Sintesis Review</span>
                  <span>{review?.reasoning_source === 'rule_fallback' ? 'fallback rule-count' : review?.model_used || review?.reasoning_source}</span>
                </div>
                <div style={{ fontSize: '0.82rem' }}>{review?.reasoning_narrative || '—'}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
