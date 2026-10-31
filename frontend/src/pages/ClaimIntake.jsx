import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FilePlus } from 'lucide-react'
import { claimsApi, safeErrorMessage } from '../api'
import { toast } from '../Toast'

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
  // Validasi baru ditampilkan setelah pengguna mencoba menyimpan, supaya form
  // kosong tidak langsung meneriakkan "6 data wajib belum lengkap".
  const [showValidation, setShowValidation] = useState(false)

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
      setShowValidation(true)
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const payload = buildClaimPayload()
      const res = await claimsApi.create(payload)
      if (res.data.status !== 'success') throw new Error(res.data.message || 'Klaim belum berhasil disimpan.')

      sessionStorage.setItem(`claim_${payload.claim_id}`, JSON.stringify(payload))
      toast(`Klaim ${payload.claim_id} berhasil disimpan dan masuk antrian.`)
      navigate('/claims')
    } catch (e) {
      setError(safeErrorMessage(e, 'dependency_unavailable'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleChange = (field, value) => setForm(f => ({ ...f, [field]: value }))

// Syntax highlight JSON — key hijau, string biru, angka amber, null abu miring.
// Teks di-escape dulu supaya nilai bebas user tetap aman dirender sebagai HTML.
const highlightJson = (json) => {
  const escaped = json.replace(/[&<>]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]))
  return escaped.replace(
    /("(?:\\u[0-9a-fA-F]{4}|\\[^u]|[^\\"])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
    (m, str, colon, word, num) => {
      if (colon !== undefined) return `<span class="int-json-key">${str}</span>${colon}`
      if (str) return `<span class="int-json-str">${str}</span>`
      if (word) return `<span class="int-json-null">${word}</span>`
      if (num) return `<span class="int-json-num">${num}</span>`
      return m
    }
  )
}

  const blockingErrors = clientErrors.filter(e => !e.startsWith('Peringatan'))
  const warnings = clientErrors.filter(e => e.startsWith('Peringatan'))

  return (
    <div className="int-page">
      {/* Topbar — pola sama dengan Dashboard & Daftar Klaim */}
      <header className="int-topbar">
        <div>
          <div className="dashboard-title-row">
            <div className="header-icon-badge">
              <FilePlus size={20} />
            </div>
            <h1>Input Klaim</h1>
          </div>
          <p className="int-page-sub">Masukkan data klaim untuk memulai pemeriksaan — setelah disimpan, klaim langsung masuk antrian.</p>
        </div>
        <div className="int-toggle" role="group" aria-label="Mode tampilan data">
          <button
            type="button"
            className={viewMode === 'form' ? 'active' : ''}
            aria-pressed={viewMode === 'form'}
            onClick={() => setViewMode('form')}
          >
            Isi data
          </button>
          <button
            type="button"
            className={viewMode === 'json' ? 'active' : ''}
            aria-pressed={viewMode === 'json'}
            onClick={() => setViewMode('json')}
          >
            Lihat data lengkap
          </button>
        </div>
      </header>

      <div className="int-grid">
        {/* Kolom utama: form + validasi + aksi */}
        <div className="int-main">
          <div className="int-view" key={viewMode}>
          {viewMode === 'form' ? (
            <div className="card int-form-card">
              {/* Seksi: Identitas */}
              <div className="int-section-label">Identitas</div>
              <div className="int-form-cols">
                <div className="form-group">
                  <label className="form-label" htmlFor="claim-id">ID Klaim *</label>
                  <input id="claim-id" className="form-input" value={form.claim_id} onChange={e => handleChange('claim_id', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="patient-id">ID Peserta *</label>
                  <input id="patient-id" className="form-input" value={form.patient_id} onChange={e => handleChange('patient_id', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="provider-id">Fasilitas Kesehatan *</label>
                  <input id="provider-id" className="form-input" value={form.provider_id} onChange={e => handleChange('provider_id', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="doctor-id">ID Dokter</label>
                  <input id="doctor-id" className="form-input" value={form.doctor_id} onChange={e => handleChange('doctor_id', e.target.value)} />
                </div>
              </div>

              {/* Seksi: Data klinis */}
              <div className="int-section-label">Data Klinis</div>
              <div className="int-form-cols">
                <div className="form-group int-col-full">
                  <label className="form-label" htmlFor="primary-diagnosis">Diagnosis Utama (Kode Penyakit) *</label>
                  <input id="primary-diagnosis" className="form-input" value={form.diagnosis_primary} onChange={e => handleChange('diagnosis_primary', e.target.value)} placeholder="Contoh: I21.9" />
                </div>
                <div className="form-group int-col-full">
                  <label className="form-label" htmlFor="secondary-diagnosis">Diagnosis Tambahan</label>
                  <input id="secondary-diagnosis" className="form-input" value={form.diagnosis_secondary} onChange={e => handleChange('diagnosis_secondary', e.target.value)} placeholder="Kode diagnosis tambahan" />
                  <p className="int-field-help">Pisahkan dengan koma. Contoh: I10, A41.9</p>
                </div>
                <div className="form-group int-col-full">
                  <label className="form-label" htmlFor="procedure-codes">Kode Tindakan</label>
                  <input id="procedure-codes" className="form-input" value={form.procedure_codes} onChange={e => handleChange('procedure_codes', e.target.value)} placeholder="Kode tindakan medis" />
                  <p className="int-field-help">Pisahkan dengan koma. Contoh: 36.10, 89.52</p>
                </div>
                <div className="form-group int-col-full">
                  <label className="form-label" htmlFor="medication">Obat dan Jumlah</label>
                  <input id="medication" className="form-input" value={form.medication} onChange={e => handleChange('medication', e.target.value)} placeholder="Nama obat dan jumlah" />
                  <p className="int-field-help">Pisahkan dengan koma. Contoh: Aspirin 30, Metformin 30</p>
                </div>
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

              {/* Seksi: Biaya & waktu */}
              <div className="int-section-label">Biaya &amp; Waktu</div>
              <div className="int-form-cols">
                <div className="form-group">
                  <label className="form-label" htmlFor="claimed-cost">Biaya Klaim (Rp) *</label>
                  <input id="claimed-cost" className="form-input int-input-mono" type="number" inputMode="decimal" value={form.cost_claimed} onChange={e => handleChange('cost_claimed', e.target.value)} />
                </div>
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
            <div className="card int-form-card">
              <div className="int-section-label">Data Klaim Lengkap</div>
              <pre
              className="int-json"
              dangerouslySetInnerHTML={{ __html: highlightJson(JSON.stringify(buildClaimPayload(), null, 2)) }}
            />
            </div>
          )}
          </div>

          {/* Validasi klien — muncul setelah percobaan simpan pertama. */}
          {showValidation && blockingErrors.length > 0 && (
            <div role="alert" className="int-alert int-alert-error">
              <div className="int-alert-title" style={{ color: 'var(--error-text)' }}>{blockingErrors.length} data wajib belum lengkap</div>
              <ul>
                {blockingErrors.map((err, i) => <li key={i}>{err}</li>)}
              </ul>
            </div>
          )}
          {warnings.length > 0 && (
            <div role="status" className="int-alert int-alert-warn">
              <div className="int-alert-title" style={{ color: 'var(--warning-text)' }}>Perlu diperiksa lagi</div>
              <ul>
                {warnings.map((w, i) => <li key={i}>{w.replace(/^Peringatan:\s*/, '')}</li>)}
              </ul>
            </div>
          )}
          {error && (
            <div role="alert" className="int-alert int-alert-error">
              <div className="int-alert-title">Klaim belum berhasil disimpan</div>
              <ul><li>{error}</li></ul>
            </div>
          )}

          <button
            className="btn btn-primary int-submit"
            onClick={handleAnalyze}
            disabled={submitting}
          >
            {submitting ? 'Menyimpan klaim…' : 'Simpan dan mulai pemeriksaan'}
          </button>
        </div>

        {/* Panel kanan: alur pemeriksaan */}
        <aside className="int-aside">
          <div className="card int-steps-card">
            <div className="card-title">Tahapan Pemeriksaan</div>
            <ol className="int-steps">
              {[
                { step: '0', agent: 'Pemeriksaan Data', desc: 'Memastikan data wajib, tanggal, dan duplikat sudah benar.' },
                { step: '1', agent: 'Pemeriksaan Medis', desc: 'Membandingkan diagnosis, tindakan, obat, dan tingkat keparahan.' },
                { step: '2', agent: 'Pemeriksaan Biaya', desc: 'Membandingkan biaya klaim dengan kasus yang sejenis.' },
                { step: '3', agent: 'Pemeriksaan Pola Klaim', desc: 'Mencari pengulangan dan pola fasilitas kesehatan yang tidak wajar.' },
                { step: '4', agent: 'Perangkuman Temuan', desc: 'Menggabungkan temuan dari seluruh pemeriksaan.' },
                { step: '5', agent: 'Penentuan Prioritas', desc: 'Menghitung tingkat kebutuhan tindak lanjut secara konsisten.' },
                { step: '6', agent: 'Penjelasan Hasil', desc: 'Menyusun ringkasan yang mudah dibaca verifier.' },
              ].map(item => (
                <li key={item.step} className="int-step">
                  <span className="int-step-num" aria-hidden="true">{item.step}</span>
                  <div className="int-step-body">
                    <div className="int-step-name">{item.agent}</div>
                    <div className="int-step-desc">{item.desc}</div>
                  </div>
                </li>
              ))}
            </ol>
            <p className="int-step-footnote">
              Pemeriksaan medis, biaya, dan pola klaim berjalan bersamaan — jika salah satu data belum tersedia, hasil tetap ditampilkan dan ditandai dengan jelas.
            </p>
          </div>
        </aside>
      </div>
    </div>
  )
}
