import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { claimsApi } from '../api'

const EMPTY_FORM = {
  claim_id: '',
  patient_id: '',
  provider_id: '',
  doctor_id: '',
  diagnosis_primary: '',
  diagnosis_secondary: '',
  procedure_codes: '',
  medication: '',
  severity_level: '',
  cost_claimed: '',
  length_of_stay: '',
  admission_date: '',
  discharge_date: '',
}

export default function ClaimIntake() {
  const navigate = useNavigate()
  const [form, setForm] = useState(EMPTY_FORM)
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
    if (!form.claim_id?.trim()) errors.push('ID klaim wajib diisi.')
    if (!form.patient_id?.trim()) errors.push('ID peserta wajib diisi.')
    if (!form.provider_id?.trim()) errors.push('Fasilitas kesehatan wajib diisi.')
    if (!form.diagnosis_primary?.trim()) errors.push('Diagnosis primer wajib diisi.')
    if (form.admission_date && form.discharge_date && form.discharge_date < form.admission_date) {
      errors.push('Tanggal keluar tidak boleh lebih awal dari tanggal masuk.')
    }
    if (!Number.isInteger(Number(form.severity_level)) || Number(form.severity_level) < 1 || Number(form.severity_level) > 4) {
      errors.push('Tingkat keparahan wajib dipilih.')
    }
    if (!Number.isFinite(Number(form.cost_claimed)) || Number(form.cost_claimed) <= 0) {
      errors.push('Biaya klaim harus diisi dengan angka positif.')
    }
    if (!Number.isInteger(Number(form.length_of_stay)) || Number(form.length_of_stay) < 0) {
      errors.push('Lama rawat wajib diisi dengan angka nol atau lebih.')
    }
    if (form.admission_date && form.discharge_date && parseInt(form.length_of_stay) >= 0) {
      const span = (new Date(form.discharge_date) - new Date(form.admission_date)) / 86400000
       if (Math.abs(span - parseInt(form.length_of_stay)) > 1) {
       errors.push(`Peringatan: lama rawat (${form.length_of_stay} hari) berbeda dengan rentang tanggal (${Math.round(span)} hari).`)
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
            <button className={`btn btn-ghost ${viewMode === 'json' ? 'active' : ''}`} onClick={() => setViewMode('json')}>Data Terstruktur</button>
          </div>
        </div>

      </div>

      <div className="alert-disclaimer mb-4">
         ⓘ <strong>Catatan:</strong> Data yang dikirim dari halaman ini langsung disimpan ke backend dan masuk ke antrian pemeriksaan.
      </div>

      <div className="grid-2" style={{ gap: '1.5rem' }}>
        <div>
          {viewMode === 'form' ? (
            <div className="card">
              <div className="card-title">Data Klaim</div>

              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label" htmlFor="claim-id">ID Klaim *</label>
                  <input id="claim-id" className="form-input" value={form.claim_id} onChange={e => handleChange('claim_id', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="patient-id">ID Peserta *</label>
                  <input id="patient-id" className="form-input" value={form.patient_id} onChange={e => handleChange('patient_id', e.target.value)} />
                </div>
              </div>

              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label" htmlFor="provider-id">Fasilitas Kesehatan *</label>
                  <input id="provider-id" className="form-input" value={form.provider_id} onChange={e => handleChange('provider_id', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="doctor-id">ID Dokter</label>
                  <input id="doctor-id" className="form-input" value={form.doctor_id} onChange={e => handleChange('doctor_id', e.target.value)} />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="primary-diagnosis">Diagnosis Utama (Kode Penyakit) *</label>
                <input id="primary-diagnosis" className="form-input" value={form.diagnosis_primary} onChange={e => handleChange('diagnosis_primary', e.target.value)} placeholder="Contoh: I21.9" />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="secondary-diagnosis">Diagnosis Tambahan</label>
                <input id="secondary-diagnosis" className="form-input" value={form.diagnosis_secondary} onChange={e => handleChange('diagnosis_secondary', e.target.value)} placeholder="Pisahkan dengan koma, contoh: I10, A41.9" />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="procedure-codes">Kode Tindakan</label>
                <input id="procedure-codes" className="form-input" value={form.procedure_codes} onChange={e => handleChange('procedure_codes', e.target.value)} placeholder="Pisahkan dengan koma, contoh: 36.10, 89.52" />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="medication">Obat dan Jumlah</label>
                <input id="medication" className="form-input" value={form.medication} onChange={e => handleChange('medication', e.target.value)} placeholder="Contoh: Aspirin 30, Metformin 30" />
              </div>

              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label" htmlFor="severity">Tingkat Keparahan (1-4)</label>
                  <select id="severity" className="form-select" value={form.severity_level} onChange={e => handleChange('severity_level', e.target.value)}>
                    <option value="">Pilih tingkat keparahan</option>
                    <option value={1}>1 - Ringan</option>
                    <option value={2}>2 - Sedang</option>
                    <option value={3}>3 - Berat</option>
                    <option value={4}>4 - Sangat Berat</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="length-of-stay">Lama Rawat (hari)</label>
                  <input id="length-of-stay" className="form-input" type="number" value={form.length_of_stay} onChange={e => handleChange('length_of_stay', e.target.value)} />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="claimed-cost">Biaya Klaim (Rp) *</label>
                <input id="claimed-cost" className="form-input" type="number" inputMode="decimal" value={form.cost_claimed} onChange={e => handleChange('cost_claimed', e.target.value)} />
              </div>

              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label" htmlFor="admission-date">Tanggal Masuk</label>
                  <input id="admission-date" className="form-input" type="date" value={form.admission_date} onChange={e => handleChange('admission_date', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="discharge-date">Tanggal Keluar</label>
                  <input id="discharge-date" className="form-input" type="date" value={form.discharge_date} onChange={e => handleChange('discharge_date', e.target.value)} />
                </div>
              </div>
            </div>
          ) : (
            <div className="card">
              <div className="card-title">Data Klaim Terstruktur</div>
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
             <div className="card-title">Tahapan Pemeriksaan</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {[
                { step: '0', agent: 'Pemeriksaan Data', desc: 'Memastikan data wajib, tanggal, dan duplikat sudah benar.' },
                { step: '1', agent: 'Pemeriksaan Medis', desc: 'Membandingkan diagnosis, tindakan, obat, dan tingkat keparahan.' },
                { step: '2', agent: 'Pemeriksaan Biaya', desc: 'Membandingkan biaya klaim dengan kasus yang sejenis.' },
                { step: '3', agent: 'Pemeriksaan Pola Klaim', desc: 'Mencari pengulangan dan pola fasilitas kesehatan yang tidak wajar.' },
                { step: '4', agent: 'Perangkuman Temuan', desc: 'Menggabungkan temuan dari seluruh pemeriksaan.' },
                { step: '5', agent: 'Penentuan Prioritas', desc: 'Menghitung tingkat kebutuhan tindak lanjut secara konsisten.' },
                { step: '6', agent: 'Penjelasan Hasil', desc: 'Menyusun ringkasan yang mudah dibaca verifier.' },
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
             ⓘ Pemeriksaan medis, biaya, dan pola klaim berjalan bersamaan. Jika salah satu data belum tersedia, hasil tetap ditampilkan dan ditandai dengan jelas.
          </div>
        </div>
      </div>
    </div>
  )
}
