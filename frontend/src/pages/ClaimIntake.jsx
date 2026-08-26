import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { claimsApi } from '../api'

const INITIAL_FORM = {
  claim_id: 'CLM-TEST-0001',
  patient_id: 'PAT-99001',
  provider_id: 'FAC-A12',
  doctor_id: 'DR-A12-101',
  diagnosis_primary: 'I21.9',
  diagnosis_secondary: 'I10, A41.9',
  procedure_codes: '36.10, 89.52',
  medication: 'Aspirin 30, Clopidogrel 30',
  severity_level: 4,
  cost_claimed: 52000000,
  length_of_stay: 9,
  admission_date: '2026-07-10',
  discharge_date: '2026-07-19',
}

const SAMPLE_CLAIMS = {
  normal: {
    claim_id: 'CLM-NORMAL-01',
    patient_id: 'PAT-10023',
    provider_id: 'FAC-B22',
    doctor_id: 'DR-B22-404',
    diagnosis_primary: 'J18.9',
    diagnosis_secondary: '',
    procedure_codes: '89.52',
    medication: 'Amoxicillin 14',
    severity_level: 1,
    cost_claimed: 3500000,
    length_of_stay: 4,
    admission_date: '2026-08-01',
    discharge_date: '2026-08-05',
  },
  upcoding: {
    claim_id: 'CLM-UPC-099',
    patient_id: 'PAT-44012',
    provider_id: 'FAC-C19',
    doctor_id: 'DR-C19-112',
    diagnosis_primary: 'J18.9',
    diagnosis_secondary: 'A41.9',
    procedure_codes: '',
    medication: 'Paracetamol 10',
    severity_level: 4,
    cost_claimed: 12500000,
    length_of_stay: 7,
    admission_date: '2026-08-01',
    discharge_date: '2026-08-08',
  },
  cloning: {
    ...INITIAL_FORM,
    claim_id: 'CLM-FRAUD-002',
    patient_id: 'PAT-99002', // beda pasien, sisanya identik dengan INITIAL_FORM
  },
}

export default function ClaimIntake() {
  const navigate = useNavigate()
  const [form, setForm] = useState(INITIAL_FORM)
  const [viewMode, setViewMode] = useState('form')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const buildClaimPayload = () => ({
    claim_id: form.claim_id,
    patient_id: form.patient_id,
    provider_id: form.provider_id,
    doctor_id: form.doctor_id,
    diagnosis_primary: form.diagnosis_primary,
    diagnosis_secondary: form.diagnosis_secondary.split(',').map(s => s.trim()).filter(Boolean),
    procedure_codes: form.procedure_codes.split(',').map(s => s.trim()).filter(Boolean),
    medication: form.medication.split(',').map(s => {
      const parts = s.trim().split(' ')
      const qty = parseInt(parts[parts.length - 1]) || 1
      const name = parts.slice(0, -1).join(' ') || s.trim()
      return { name, quantity: qty }
    }).filter(m => m.name),
    severity_level: parseInt(form.severity_level),
    cost_claimed: parseFloat(form.cost_claimed),
    length_of_stay: parseInt(form.length_of_stay),
    admission_date: form.admission_date || null,
    discharge_date: form.discharge_date || null,
    referral_info: null,
  })

  // Validasi klien — mirror dari validate_deterministic backend (feedback instan)
  const clientErrors = useMemo(() => {
    const errors = []
    if (!form.claim_id?.trim()) errors.push('Claim ID wajib diisi.')
    if (!form.patient_id?.trim()) errors.push('Patient ID wajib diisi.')
    if (!form.provider_id?.trim()) errors.push('Provider/Faskes wajib diisi.')
    if (!form.diagnosis_primary?.trim()) errors.push('Diagnosis primer wajib diisi.')
    if (form.admission_date && form.discharge_date && form.discharge_date < form.admission_date) {
      errors.push('Tanggal keluar tidak boleh lebih awal dari tanggal masuk.')
    }
    if (parseFloat(form.cost_claimed) <= 0) errors.push('Biaya klaim harus positif.')
    if (parseInt(form.length_of_stay) < 0) errors.push('Lama rawat tidak boleh negatif.')
    if (form.admission_date && form.discharge_date && parseInt(form.length_of_stay) >= 0) {
      const span = (new Date(form.discharge_date) - new Date(form.admission_date)) / 86400000
      if (Math.abs(span - parseInt(form.length_of_stay)) > 1) {
        errors.push(`Peringatan: lama rawat (${form.length_of_stay} hr) tidak konsisten dengan rentang tanggal (${Math.round(span)} hr) — sistem akan mencatat peringatan validasi.`)
      }
    }
    return errors
  }, [form])

  const handleAnalyze = async () => {
    if (clientErrors.some(e => !e.startsWith('Peringatan'))) {
      setError('Perbaiki error pada form terlebih dahulu.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const payload = buildClaimPayload()
      const res = await claimsApi.create(payload)
      if (res.data.status !== 'success') throw new Error(res.data.message || 'Gagal menyimpan klaim.')

      sessionStorage.setItem(`claim_${payload.claim_id}`, JSON.stringify(payload))
      navigate('/claims')
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleChange = (field, value) => setForm(f => ({ ...f, [field]: value }))

  const blockingErrors = clientErrors.filter(e => !e.startsWith('Peringatan'))
  const warnings = clientErrors.filter(e => e.startsWith('Peringatan'))

  return (
    <div>
      <div className="page-header">
        <div className="flex items-center justify-between">
          <div>
            <h2>Input Klaim Baru</h2>
            <p>Masukkan data klaim secara manual untuk dianalisis oleh sistem.</p>
          </div>
          <div className="flex gap-1">
            <button className={`btn btn-ghost ${viewMode === 'form' ? 'active' : ''}`} onClick={() => setViewMode('form')}>Form</button>
            <button className={`btn btn-ghost ${viewMode === 'json' ? 'active' : ''}`} onClick={() => setViewMode('json')}>Raw JSON</button>
          </div>
        </div>

        {/* Fitur Auto-Fill untuk Demo */}
        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Isi otomatis untuk testing:</span>
          <button className="btn btn-ghost" style={{ fontSize: '0.75rem', padding: '0.25rem 0.75rem', border: '1px solid var(--border)' }} onClick={() => setForm(SAMPLE_CLAIMS.normal)}>Klaim Normal (Wajar)</button>
          <button className="btn btn-ghost" style={{ fontSize: '0.75rem', padding: '0.25rem 0.75rem', border: '1px solid var(--risk-high)', color: 'var(--risk-high)' }} onClick={() => setForm(SAMPLE_CLAIMS.upcoding)}>Indikasi Upcoding</button>
          <button className="btn btn-ghost" style={{ fontSize: '0.75rem', padding: '0.25rem 0.75rem', border: '1px solid var(--risk-high)', color: 'var(--risk-high)' }} onClick={() => setForm(SAMPLE_CLAIMS.cloning)}>Indikasi Cloning</button>
        </div>
      </div>

      <div className="alert-disclaimer mb-4">
        ⓘ <strong>PENTING:</strong> Ini adalah tool simulasi untuk keperluan hackathon yang merepresentasikan integrasi data klaim otomatis dari faskes. Di dunia nyata, form manual ini <strong>TIDAK ADA</strong> di sisi Verifier BPJS. Klaim seharusnya sudah masuk secara otomatis ke antrean "Incoming Claims".
      </div>

      <div className="grid-2" style={{ gap: '1.5rem' }}>
        <div>
          {viewMode === 'form' ? (
            <div className="card">
              <div className="card-title">Data Klaim</div>

              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label">Claim ID *</label>
                  <input className="form-input" value={form.claim_id} onChange={e => handleChange('claim_id', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Patient ID *</label>
                  <input className="form-input" value={form.patient_id} onChange={e => handleChange('patient_id', e.target.value)} />
                </div>
              </div>

              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label">Provider / Faskes *</label>
                  <input className="form-input" value={form.provider_id} onChange={e => handleChange('provider_id', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Dokter ID</label>
                  <input className="form-input" value={form.doctor_id} onChange={e => handleChange('doctor_id', e.target.value)} />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Diagnosis Primer (ICD-10) *</label>
                <input className="form-input" value={form.diagnosis_primary} onChange={e => handleChange('diagnosis_primary', e.target.value)} placeholder="contoh: I21.9" />
              </div>

              <div className="form-group">
                <label className="form-label">Diagnosis Sekunder (koma-pisah)</label>
                <input className="form-input" value={form.diagnosis_secondary} onChange={e => handleChange('diagnosis_secondary', e.target.value)} placeholder="contoh: I10, A41.9" />
              </div>

              <div className="form-group">
                <label className="form-label">Kode Prosedur ICD-9-CM (koma-pisah)</label>
                <input className="form-input" value={form.procedure_codes} onChange={e => handleChange('procedure_codes', e.target.value)} placeholder="contoh: 36.10, 89.52" />
              </div>

              <div className="form-group">
                <label className="form-label">Obat (format: NamaObat Qty, ...)</label>
                <input className="form-input" value={form.medication} onChange={e => handleChange('medication', e.target.value)} placeholder="contoh: Aspirin 30, Metformin 30" />
              </div>

              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label">Level Severity (1-4)</label>
                  <select className="form-select" value={form.severity_level} onChange={e => handleChange('severity_level', e.target.value)}>
                    <option value={1}>1 - Ringan</option>
                    <option value={2}>2 - Sedang</option>
                    <option value={3}>3 - Berat</option>
                    <option value={4}>4 - Sangat Berat</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Lama Rawat (hari)</label>
                  <input className="form-input" type="number" value={form.length_of_stay} onChange={e => handleChange('length_of_stay', e.target.value)} />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Biaya Diklaim (Rp) *</label>
                <input className="form-input" type="number" value={form.cost_claimed} onChange={e => handleChange('cost_claimed', e.target.value)} />
              </div>

              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label">Tanggal Masuk</label>
                  <input className="form-input" type="date" value={form.admission_date} onChange={e => handleChange('admission_date', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Tanggal Keluar</label>
                  <input className="form-input" type="date" value={form.discharge_date} onChange={e => handleChange('discharge_date', e.target.value)} />
                </div>
              </div>
            </div>
          ) : (
            <div className="card">
              <div className="card-title">Raw JSON — ClaimInput</div>
              <pre className="form-textarea" style={{ display: 'block', overflow: 'auto', fontSize: '0.72rem', lineHeight: 1.7, padding: '1rem' }}>
                {JSON.stringify(buildClaimPayload(), null, 2)}
              </pre>
            </div>
          )}

          {/* Validasi klien real-time */}
          {blockingErrors.length > 0 && (
            <div style={{ marginTop: '1rem', padding: '0.75rem 1rem', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, color: 'var(--risk-high)', fontSize: '0.8rem' }}>
              {blockingErrors.map((err, i) => <div key={i}>⚠ {err}</div>)}
            </div>
          )}
          {warnings.length > 0 && (
            <div style={{ marginTop: '1rem', padding: '0.75rem 1rem', background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 8, color: 'var(--warning)', fontSize: '0.8rem' }}>
              {warnings.map((w, i) => <div key={i}>ⓘ {w}</div>)}
            </div>
          )}
          {error && (
            <div style={{ marginTop: '1rem', padding: '0.75rem 1rem', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, color: 'var(--risk-high)', fontSize: '0.8rem' }}>
              ⚠ {error}
            </div>
          )}

          <div style={{ marginTop: '1rem' }}>
            <button
              className="btn btn-primary"
              style={{ width: '100%', padding: '0.8rem', fontSize: '0.9rem', opacity: blockingErrors.length ? 0.5 : 1 }}
              onClick={handleAnalyze}
              disabled={submitting || blockingErrors.length > 0}
            >
              {submitting ? '⟳ Menyimpan klaim...' : 'Simpan & Masukkan ke Antrian'}
            </button>
          </div>
        </div>

        {/* Right panel: hint about architecture */}
        <div>
          <div className="card mb-2">
            <div className="card-title">Arsitektur Analisis</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {[
                { step: '0', agent: 'Validasi Deterministik', desc: 'Field wajib, duplikat eksak, konsistensi tanggal — tanpa LLM' },
                { step: '1', agent: 'Clinical Agent', desc: 'INA-CBG grouper (rule dulu) + LLM hanya untuk kasus ambigu' },
                { step: '2', agent: 'Financial Engine', desc: 'Prediksi biaya XGBoost + atribusi SHAP' },
                { step: '3', agent: 'Fraud Agent', desc: 'Similarity LanceDB + repeat billing SQL + metrik jaringan faskes' },
                { step: '4', agent: 'Review Agent', desc: 'Sintesis evidence multi-sinyal via LLM + fallback rule-count' },
                { step: '5', agent: 'Risk Engine', desc: 'Kalkulasi skor 0-100 — bobot terdokumentasi, tanpa LLM' },
                { step: '6', agent: 'Explanation Agent', desc: 'Narasi Bahasa Indonesia + validasi angka anti-halusinasi' },
              ].map(item => (
                <div key={item.step} className="flex items-center gap-2" style={{ padding: '0.5rem', background: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border)' }}>
                  <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--accent-green-glow)', border: '1px solid var(--accent-green)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', color: 'var(--accent-green)', fontWeight: 700, flexShrink: 0 }}>
                    {item.step}
                  </div>
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600 }}>{item.agent}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{item.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="alert-disclaimer">
            ⓘ Agents berjalan secara <strong>paralel nyata</strong> menggunakan <code>asyncio.gather</code> — kegagalan satu agent tidak menjatuhkan pipeline (fallback per-agent).
          </div>
        </div>
      </div>
    </div>
  )
}
