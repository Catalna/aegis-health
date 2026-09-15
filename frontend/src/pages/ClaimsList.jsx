import { useState, useEffect, useCallback, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Search, AlertCircle, CheckCircle2, Clock, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { claimsApi, safeErrorMessage } from '../api'
import { STATUS_LABELS, TIER_LABELS, formatDecision } from '../humanLanguage'
import DataFreshness from '../DataFreshness'
import { formatDuration, formatQueueAge as formatQueueAgeValue } from '../queueSummaryData'

const VALID_STATUSES = ['pending', 'scanning', 'processed', 'review_required', 'failed', 'verified']
const VALID_SORTS = ['priority', 'queue', 'risk_desc', 'risk_asc', 'cost_desc', 'cost_asc', 'id']
const FILTER_PARAMS = ['q', 'status', 'tier', 'received_from', 'received_to', 'admission_from', 'admission_to', 'sort']

function RiskBadge({ tier }) {
  if (!tier) return <span className="text-muted" style={{ fontSize: '0.8rem' }}>—</span>
  if (tier === 'high') return <span className="badge badge-high"><AlertCircle size={12} /> {TIER_LABELS.high}</span>
  if (tier === 'medium') return <span className="badge badge-medium"><AlertCircle size={12} /> {TIER_LABELS.medium}</span>
  return <span className="badge badge-low"><CheckCircle2 size={12} /> {TIER_LABELS.low}</span>
}

function ScoreBar({ score, tier }) {
  const fillColors = { high: 'var(--risk-high)', medium: 'var(--risk-medium)', low: 'var(--risk-low)' }
  const textColors = { high: 'var(--error-text)', medium: 'var(--warning-text)', low: 'var(--risk-low)' }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <div className="progress-bar" style={{ width: 80, height: 5 }}>
        <div className="progress-fill" style={{ width: `${score}%`, background: fillColors[tier] || 'var(--text-muted)' }} />
      </div>
      <span style={{ fontSize: '0.8rem', fontWeight: 700, color: textColors[tier] || 'var(--text-muted)', minWidth: 28 }}>{score ?? '—'}</span>
    </div>
  )
}

function StatusBadge({ claim }) {
  if (claim.status === 'verified') {
    return <div>
      <span className="badge" style={{ background: 'var(--success)', color: 'white', fontSize: '0.65rem' }}>✓ {STATUS_LABELS.verified}</span>
       <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 2 }}>{formatDecision(claim.human_decision)}</div>
    </div>
  }
  const isFailed = claim.status === 'failed'
  const isReview = claim.status === 'review_required'
  const isHumanVerificationPending = claim.status === 'processed'
  const color = isFailed ? 'var(--error-text)' : isReview ? 'var(--risk-medium-bg)' : 'var(--bg-card-hover)'
  const textColor = isFailed ? 'white' : isReview ? 'var(--warning-text)' : 'var(--text-secondary)'
  return <div>
    <span className="badge" style={{ background: color, color: textColor, fontSize: '0.65rem' }}>
      {claim.status === 'scanning' || claim.status === 'pending' ? <Clock size={12} /> : isFailed || isReview ? <AlertCircle size={12} /> : <CheckCircle2 size={12} />}
      {STATUS_LABELS[claim.status] || claim.status}
    </span>
    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 2 }}>
       {isHumanVerificationPending ? 'Menunggu keputusan petugas' : `Upaya pemeriksaan: ${claim.analysis_attempts ?? 0}`}
    </div>
  </div>
}

function formatReceivedAt(value) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' })
}

function formatQueueAge(value, now = Date.now()) {
  return formatQueueAgeValue(value, now)
}

function formatClaimQueueTime(claim, now) {
  const received = new Date(claim.received_at).getTime()
  if (claim.status === 'verified') {
    const verified = new Date(claim.verified_at).getTime()
    if (!Number.isNaN(received) && !Number.isNaN(verified) && verified >= received) {
      return formatDuration(verified - received)
    }
    return '—'
  }
  if (['failed', 'processed', 'review_required'].includes(claim.status)) {
    const completedAt = claim.analyzed_at || claim.analysis_started_at
    const completedTimestamp = new Date(completedAt).getTime()
    if (!Number.isNaN(received) && !Number.isNaN(completedTimestamp) && completedTimestamp >= received) {
      return formatDuration(completedTimestamp - received)
    }
    return '—'
  }
  return formatQueueAge(claim.received_at, now)
}

const PAGE_SIZE = 25

export default function ClaimsList() {
  const [searchParams, setSearchParams] = useSearchParams()
  const queryTier = searchParams.get('tier')
  const tier = ['high', 'medium', 'low'].includes(queryTier) ? queryTier : ''
  const queryStatus = searchParams.get('status')
  const status = VALID_STATUSES.includes(queryStatus) ? queryStatus : ''
  const querySort = searchParams.get('sort')
  const sort = VALID_SORTS.includes(querySort) ? querySort : 'priority'
  const search = searchParams.get('q') || ''
  const receivedFrom = searchParams.get('received_from') || ''
  const receivedTo = searchParams.get('received_to') || ''
  const admissionFrom = searchParams.get('admission_from') || ''
  const admissionTo = searchParams.get('admission_to') || ''
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filter state
  const [searchInput, setSearchInput] = useState(search)
  const [page, setPage] = useState(0)
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null)
  const [currentTime, setCurrentTime] = useState(Date.now())
  const [refreshing, setRefreshing] = useState(false)
  const requestGenerationRef = useRef(0)
  const abortControllerRef = useRef(null)

  const fetchClaims = useCallback(async () => {
    const generation = ++requestGenerationRef.current
    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller
    setRefreshing(true)
    try {
      setError(null)
      const res = await claimsApi.list({
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: search || undefined,
        status: status || undefined,
        tier: tier || undefined,
        received_from: receivedFrom || undefined,
        received_to: receivedTo || undefined,
        admission_from: admissionFrom || undefined,
        admission_to: admissionTo || undefined,
        sort,
       }, { signal: controller.signal })
       if (generation !== requestGenerationRef.current) return
       setData(res.data)
       setLastUpdatedAt(Date.now())
     } catch (err) {
       if (generation !== requestGenerationRef.current) return
       setError(safeErrorMessage(err, 'dependency_unavailable'))
    } finally {
       if (generation === requestGenerationRef.current) {
         setLoading(false)
         setRefreshing(false)
       }
    }
  }, [page, search, status, tier, receivedFrom, receivedTo, admissionFrom, admissionTo, sort])

  useEffect(() => {
    fetchClaims()
    const interval = setInterval(fetchClaims, 15000)
    const clock = setInterval(() => setCurrentTime(Date.now()), 5000)
     return () => {
       clearInterval(interval)
       clearInterval(clock)
       abortControllerRef.current?.abort()
       requestGenerationRef.current += 1
     }
  }, [fetchClaims])

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => {
      setSearchParams(previous => {
        const nextParams = new URLSearchParams(previous)
        if ((previous.get('q') || '') === searchInput) return previous
        if (searchInput) nextParams.set('q', searchInput)
        else nextParams.delete('q')
        return nextParams
      }, { replace: true })
      setPage(0)
    }, 350)
    return () => clearTimeout(t)
  }, [searchInput, setSearchParams])

  useEffect(() => {
    setSearchInput(search)
  }, [search])

  const handleClaimOpen = (claim) => {
    sessionStorage.setItem(`claim_${claim.claim_id}`, JSON.stringify(claim))
  }

  const updateFilter = (name, value) => {
    setPage(0)
    const nextParams = new URLSearchParams(searchParams)
    if (value) nextParams.set(name, value)
    else nextParams.delete(name)
    setSearchParams(nextParams, { replace: true })
  }

  const resetFilters = () => {
    setSearchInput('')
    setPage(0)
    const nextParams = new URLSearchParams(searchParams)
    FILTER_PARAMS.forEach(name => nextParams.delete(name))
    setSearchParams(nextParams, { replace: true })
  }

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
  const activeFilters = search || status || tier || receivedFrom || receivedTo || admissionFrom || admissionTo
  const initialLoading = loading && !data.items.length
  const liveStatus = initialLoading
    ? 'Memuat data klaim...'
    : loading
      ? 'Memperbarui daftar klaim...'
      : error
        ? error
        : `${data.total} klaim tersedia.`

  if (initialLoading) return (
    <div>
      <div className="claims-list-live-status" role="status" aria-live="polite" aria-atomic="true">{liveStatus}</div>
      <div className="p-8 text-center text-muted">Memuat data klaim...</div>
    </div>
  )

  return (
    <div>
      <div className="claims-list-live-status" role="status" aria-live="polite" aria-atomic="true">{liveStatus}</div>
      <div className="page-header">
        <div className="page-kicker">Antrian masuk</div>
         <h1 className="glow-text" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
           <Search size={22} color="var(--accent-green)" aria-hidden="true" />
           Daftar Klaim
         </h1>
         <p>Antrian klaim yang perlu diperiksa, diurutkan dari kebutuhan tindak lanjut tertinggi.</p>
       </div>

       <DataFreshness
         label="Data klaim"
         lastUpdatedAt={lastUpdatedAt}
         now={currentTime}
         onRefresh={fetchClaims}
          refreshing={refreshing}
          error={Boolean(error)}
          errorMessage={error}
          partial={Boolean(error)}
         />

      {/* Toolbar filter */}
      <div className="card mb-3" style={{ padding: '0.75rem 1rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: '1 1 220px', minWidth: 180 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              className="form-input claims-filter-control"
              aria-label="Cari klaim"
              placeholder="Cari ID klaim, peserta, fasilitas, atau diagnosis..."
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              style={{ paddingLeft: 30, fontSize: '0.82rem' }}
            />
            {searchInput && (
             <button className="claims-filter-clear" aria-label="Hapus pencarian" onClick={() => setSearchInput('')} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                <X size={14} aria-hidden="true" />
              </button>
            )}
          </div>

           <select aria-label="Saring berdasarkan status" className="form-select claims-filter-control" value={status} onChange={e => updateFilter('status', e.target.value)} style={{ width: 'auto', fontSize: '0.82rem' }}>
             <option value="">Semua status</option>
              <option value="pending">Menunggu pemeriksaan</option>
              <option value="scanning">Sedang diperiksa</option>
              <option value="processed">Pemeriksaan selesai</option>
              <option value="review_required">Perlu ditinjau petugas</option>
              <option value="failed">Pemeriksaan belum berhasil</option>
              <option value="verified">Sudah diputuskan petugas</option>
          </select>

              <select aria-label="Saring berdasarkan prioritas" className="form-select claims-filter-control" value={tier} onChange={e => updateFilter('tier', e.target.value)} style={{ width: 'auto', fontSize: '0.82rem' }}>
             <option value="">Semua tingkat prioritas</option>
            <option value="high">Risiko Tinggi</option>
            <option value="medium">Risiko Sedang</option>
            <option value="low">Risiko Rendah</option>
           </select>

           <label className="text-xs text-muted">
             Dari
             <input aria-label="Tanggal klaim mulai" className="form-input claims-filter-control" type="date" value={receivedFrom} onChange={e => updateFilter('received_from', e.target.value)} style={{ width: 'auto', fontSize: '0.78rem', marginLeft: 4 }} />
           </label>
           <label className="text-xs text-muted">
             Sampai
             <input aria-label="Tanggal klaim sampai" className="form-input claims-filter-control" type="date" value={receivedTo} onChange={e => updateFilter('received_to', e.target.value)} style={{ width: 'auto', fontSize: '0.78rem', marginLeft: 4 }} />
           </label>
           <label className="text-xs text-muted">
             Masuk dari
             <input aria-label="Tanggal masuk mulai" className="form-input claims-filter-control" type="date" value={admissionFrom} onChange={e => updateFilter('admission_from', e.target.value)} style={{ width: 'auto', fontSize: '0.78rem', marginLeft: 4 }} />
           </label>
           <label className="text-xs text-muted">
             Masuk sampai
             <input aria-label="Tanggal masuk sampai" className="form-input claims-filter-control" type="date" value={admissionTo} onChange={e => updateFilter('admission_to', e.target.value)} style={{ width: 'auto', fontSize: '0.78rem', marginLeft: 4 }} />
           </label>

             <select aria-label="Urutkan daftar klaim" className="form-select claims-filter-control" value={sort} onChange={e => updateFilter('sort', e.target.value)} style={{ width: 'auto', fontSize: '0.82rem' }}>
              <option value="priority">Urut: Prioritas</option>
               <option value="queue">Urut: antrean masuk</option>
             <option value="risk_desc">Nilai risiko ↓</option>
             <option value="risk_asc">Nilai risiko ↑</option>
            <option value="cost_desc">Biaya ↓</option>
            <option value="cost_asc">Biaya ↑</option>
            <option value="id">ID Klaim</option>
          </select>

          {activeFilters && (
             <button className="btn btn-ghost claims-filter-action" style={{ fontSize: '0.75rem' }} onClick={resetFilters}>
              Reset Filter
            </button>
          )}

          <span className="text-xs text-muted" style={{ marginLeft: 'auto' }}>
            {data.total.toLocaleString('id-ID')} klaim
          </span>
        </div>
      </div>

      {error && <div className="alert-disclaimer mb-3" role="alert" style={{ color: 'var(--error-text)' }}>⚠ {error}</div>}

      <div className="card" style={{ padding: 0 }}>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                 <th scope="col">ID Klaim</th>
                 <th scope="col">Fasilitas Kesehatan</th>
                 <th scope="col">Diagnosis</th>
                 <th scope="col">Biaya Klaim</th>
                  <th scope="col">Lama Rawat</th>
                  <th scope="col">Diterima</th>
                  <th scope="col">Usia / Durasi</th>
                  <th scope="col">Skor Risiko</th>
                  <th scope="col">Prioritas</th>
                  <th scope="col">Status pemeriksaan</th>
                   <th scope="col">Catatan terakhir</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map(c => (
                 <tr key={c.claim_id}>
                   <td><Link className="claim-link" to={`/investigate/${c.claim_id}`} onClick={() => handleClaimOpen(c)} aria-label={`Buka klaim ${c.claim_id}`}><span className="font-mono" style={{ fontSize: '0.78rem' }}>{c.claim_id}</span></Link></td>
                  <td>
                    <div style={{ fontWeight: 500 }}>{c.provider_id}</div>
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Sumber klaim</div>
                  </td>
                  <td><span className="badge badge-blue">{c.diagnosis_primary}</span></td>
                  <td>Rp {c.cost_claimed?.toLocaleString('id-ID')}</td>
                   <td>{c.length_of_stay} hari</td>
                   <td className="text-xs">{formatReceivedAt(c.received_at)}</td>
                    <td className="text-xs">{formatClaimQueueTime(c, currentTime)}</td>
                   <td>
                     {c.status === 'pending' || c.status === 'scanning' || c.risk_score == null
                       ? <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Belum tersedia</span>
                      : <ScoreBar score={Math.round(c.risk_score)} tier={c.priority_tier || 'low'} />}
                  </td>
                  <td>
                    {c.status === 'pending'
                       ? <span className="badge" style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)' }}><Clock size={12}/> Menunggu pemeriksaan</span>
                      : <RiskBadge tier={c.priority_tier} />}
                   </td>
                    <td>
                      <StatusBadge claim={c} />
                    </td>
                     <td className="text-xs" style={{ maxWidth: 220, color: c.last_analysis_error ? 'var(--risk-high-text)' : 'var(--text-muted)' }} title={c.last_analysis_error ? safeErrorMessage({ code: c.last_analysis_error_code }) : ''}>
                       {c.last_analysis_error ? safeErrorMessage({ code: c.last_analysis_error_code }) : '—'}
                    </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                   <td colSpan={11} className="text-center text-muted" style={{ padding: '2rem' }}>
                     Tidak ada klaim yang sesuai dengan pilihan pencarian.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.75rem 1rem', borderTop: '1px solid var(--border)' }}>
          <span className="text-xs text-muted">
            Halaman {page + 1} dari {totalPages} — menampilkan {data.items.length} dari {data.total.toLocaleString('id-ID')} klaim
          </span>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn btn-ghost" disabled={page === 0} onClick={() => setPage(p => p - 1)} style={{ opacity: page === 0 ? 0.4 : 1 }}>
              <ChevronLeft size={14} /> Sebelumnya
            </button>
            <button className="btn btn-ghost" disabled={page + 1 >= totalPages} onClick={() => setPage(p => p + 1)} style={{ opacity: page + 1 >= totalPages ? 0.4 : 1 }}>
              Berikutnya <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
