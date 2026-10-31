import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Search, AlertCircle, CheckCircle2, Clock, ChevronLeft, ChevronRight, X,
  ArrowRight, RotateCw, ListChecks, CircleX, ArrowUpDown, List, SearchX,
} from 'lucide-react'
import { claimsApi, analyticsApi, safeErrorMessage } from '../api'
import { STATUS_LABELS, TIER_LABELS, formatDecision } from '../humanLanguage'
import DataFreshness from '../DataFreshness'
import { formatDuration, formatQueueAge as formatQueueAgeValue } from '../queueSummaryData'
import { ClaimsListSkeleton } from '../Skeleton'
import { navigateWithTransition } from '../viewTransition'
import EmptyState from '../EmptyState'

const VALID_STATUSES = ['pending', 'scanning', 'processed', 'review_required', 'failed', 'verified']
const VALID_SORTS = ['priority', 'queue', 'risk_desc', 'risk_asc', 'cost_desc', 'cost_asc', 'id']
const FILTER_PARAMS = ['q', 'status', 'tier', 'received_from', 'received_to', 'admission_from', 'admission_to', 'sort']
const PAGE_SIZE = 25
// Antrian dianggap "menggantung" setelah 2 jam menunggu
const QUEUE_WARN_MS = 2 * 60 * 60 * 1000

const QUICK_FILTERS = [
  { key: '', label: 'Semua klaim', dot: '#128a61', countKey: 'total_claims' },
  { key: 'review_required', label: 'Perlu ditinjau petugas', dot: '#d97706', countKey: 'review_required_claims' },
  { key: 'pending', label: 'Menunggu', dot: '#94a3b8', countKey: 'pending_claims' },
  { key: 'scanning', label: 'Sedang diperiksa', dot: '#2563eb', countKey: 'scanning_claims' },
  { key: 'verified', label: 'Sudah diputuskan', dot: '#12b76a', countKey: 'verified_claims' },
  { key: 'failed', label: 'Gagal', dot: '#e11d48', countKey: 'failed_claims' },
]

/* ---------------------------------------------------------------------------
   Atoms sel tabel
--------------------------------------------------------------------------- */

function StatusBadge({ claim }) {
  const status = claim.status
  const icons = {
    pending: <Clock aria-hidden="true" />,
    scanning: <RotateCw aria-hidden="true" />,
    review_required: <AlertCircle aria-hidden="true" />,
    failed: <CircleX aria-hidden="true" />,
    processed: <CheckCircle2 aria-hidden="true" />,
    verified: <CheckCircle2 aria-hidden="true" />,
  }
  const cls = {
    pending: 'ckl-st-pending',
    scanning: 'ckl-st-scanning',
    review_required: 'ckl-st-review',
    failed: 'ckl-st-failed',
    processed: 'ckl-st-pending',
    verified: 'ckl-st-verified',
  }[status] || 'ckl-st-pending'

  let label = STATUS_LABELS[status] || status
  if (status === 'verified') label = `Diputuskan: ${formatDecision(claim.human_decision)}`

  // Warna badge memakai token kontras WCAG, bukan warna mentah.
  const isFailed = status === 'failed'
  const isReview = status === 'review_required'
  const pendingBadgeStyle = { background: 'var(--bg-card-hover)', color: 'var(--text-secondary)' }
  const badgeBackground = isFailed ? 'var(--error-text)' : isReview ? 'var(--risk-medium-bg)' : pendingBadgeStyle.background
  const badgeColor = isFailed ? 'white' : isReview ? 'var(--warning-text)' : 'var(--text-secondary)'

  return (
    <span className={`ckl-status-badge ${cls}`} style={{ background: badgeBackground, color: badgeColor }}>
      {icons[status]}{label}
    </span>
  )
}

function StatusSub({ claim, errorMessage, color }) {
  const status = claim.status
  if (errorMessage) {
    return (
      <div className="ckl-status-sub err" title={errorMessage} style={{ color }}>{errorMessage}</div>
    )
  }
  let text = null
  if (status === 'processed') text = 'Menunggu keputusan petugas'
  else if (status === 'review_required') text = `Upaya pemeriksaan ke-${claim.analysis_attempts ?? 1}`
  else if (status === 'failed') text = 'Butuh pemeriksaan ulang'
  else if (status === 'verified' && claim.verified_at) text = `Diputus ${formatReceivedTime(claim.verified_at)}`
  else if (status === 'scanning' && claim.analysis_started_at) text = `Dimulai ${formatQueueAgeValue(claim.analysis_started_at, Date.now())} lalu`
  if (!text) return null
  return <div className="ckl-status-sub">{text}</div>
}

function RiskCell({ claim }) {
  const hasScore = !['pending', 'scanning'].includes(claim.status) && claim.risk_score != null
  if (!hasScore) {
    return (
      <span className="ckl-risk-pending">
        {claim.status === 'pending' ? 'Belum diperiksa' : 'Belum tersedia'}
      </span>
    )
  }
  const score = Math.round(claim.risk_score)
  const tier = claim.priority_tier || 'low'
  const fillColors = { high: 's-high', medium: 's-medium', low: 's-low' }
  return (
    <div className="ckl-risk-cell">
      <span className={`ckl-risk-num ${fillColors[tier]}`}>{score}</span>
      <div className="ckl-risk-bar" role="img" aria-label={`Skor risiko ${score} dari 100, tingkat ${TIER_LABELS[tier] || 'rendah'}`}>
        <i className={fillColors[tier]} style={{ width: `${score}%` }} />
      </div>
      <div className="ckl-risk-tier-wrap">
        <span className={`ckl-risk-tier ${fillColors[tier]}`}>{TIER_LABELS[tier] || 'Rendah'}</span>
      </div>
    </div>
  )
}

function formatReceivedTime(value) {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  const d = parsed.toLocaleString('id-ID', { day: '2-digit', month: '2-digit' })
  const t = parsed.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })
  return `${d}, ${t.replace(':', '.')}`
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
    return formatQueueAgeValue(claim.received_at, now)
  }
  return formatQueueAgeValue(claim.received_at, now)
}

function QueueCell({ claim, now }) {
  const age = formatClaimQueueTime(claim, now)
  let isDone = false
  let warnRaw = null
  if (claim.status === 'verified') {
    isDone = age !== '—'
  } else {
    const completedAt = ['failed', 'processed', 'review_required'].includes(claim.status)
      ? (claim.analyzed_at || claim.analysis_started_at)
      : null
    warnRaw = completedAt
      ? Math.max(0, new Date(completedAt).getTime() - new Date(claim.received_at).getTime())
      : Math.max(0, now - new Date(claim.received_at).getTime())
  }
  const ageText = isDone ? `Selesai ${age}` : `${age} di antrean`
  return (
    <div>
      <div className="ckl-queue-date">{formatReceivedTime(claim.received_at)}</div>
      <div className={`ckl-queue-age${!isDone && warnRaw > QUEUE_WARN_MS ? ' warn' : ''}`}>
        {isDone && age === '—' ? '—' : ageText}
      </div>
    </div>
  )
}

/* daftar nomor halaman ringkas: 1 … (p-1) p (p+1) … last */
function pageNumbers(page, totalPages) {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i)
  const pages = new Set([0, 1, page - 1, page, page + 1, totalPages - 2, totalPages - 1])
  const sorted = [...pages].filter(p => p >= 0 && p < totalPages).sort((a, b) => a - b)
  const out = []
  let prev = -1
  for (const p of sorted) {
    if (prev >= 0 && p - prev > 1) out.push('gap')
    out.push(p)
    prev = p
  }
  return out
}

/* ---------------------------------------------------------------------------
   Halaman
--------------------------------------------------------------------------- */

export default function ClaimsList() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
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
  const [counts, setCounts] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filter state
  const [searchInput, setSearchInput] = useState(search)
  const [page, setPage] = useState(0)
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null)
  const [currentTime, setCurrentTime] = useState(Date.now())
  const [refreshing, setRefreshing] = useState(false)
  const hasAdvancedParams = Boolean(receivedFrom || receivedTo || admissionFrom || admissionTo)
  const [showAdvanced, setShowAdvanced] = useState(hasAdvancedParams)
  const searchInputRef = useRef(null)
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

  const fetchCounts = useCallback(async () => {
    try {
      const res = await analyticsApi.dashboard()
      setCounts(res.data)
    } catch {
      /* jumlah chip tetap tampil tanpa angka jika statistik gagal dimuat */
    }
  }, [])

  useEffect(() => {
    fetchClaims()
    fetchCounts()
    const interval = setInterval(() => { fetchClaims(); fetchCounts() }, 15000)
    const clock = setInterval(() => setCurrentTime(Date.now()), 5000)
     return () => {
       clearInterval(interval)
       clearInterval(clock)
       abortControllerRef.current?.abort()
       requestGenerationRef.current += 1
     }
  }, [fetchClaims, fetchCounts])

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

  // Shortcut Ctrl+K / Cmd+K → fokus ke pencarian
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        searchInputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const handleClaimOpen = (claim) => {
    sessionStorage.setItem(`claim_${claim.claim_id}`, JSON.stringify(claim))
  }

  // Buka detail klaim dengan View Transition (fallback: navigasi biasa)
  const openClaim = (claim) => (e) => {
    e.preventDefault()
    handleClaimOpen(claim)
    navigateWithTransition(navigate, `/investigate/${claim.claim_id}`)
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
    setShowAdvanced(false)
    const nextParams = new URLSearchParams(searchParams)
    FILTER_PARAMS.forEach(name => nextParams.delete(name))
    setSearchParams(nextParams, { replace: true })
  }

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
  const activeFilters = search || status || tier || receivedFrom || receivedTo || admissionFrom || admissionTo
  const activeTags = useMemo(() => {
    const tags = []
    if (status) tags.push({ label: `Status: ${STATUS_LABELS[status]}`, param: 'status' })
    if (tier) tags.push({ label: `Prioritas: ${TIER_LABELS[tier]}`, param: 'tier' })
    if (receivedFrom || receivedTo) tags.push({
      label: `Diterima: ${receivedFrom || 'awal'} – ${receivedTo || 'now'}`,
      param: null, // dihapus bersama: kedua ujung rentang
      reset: { received_from: '', received_to: '' },
    })
    if (admissionFrom || admissionTo) tags.push({
      label: `Masuk: ${admissionFrom || 'awal'} – ${admissionTo || 'now'}`,
      param: null,
      reset: { admission_from: '', admission_to: '' },
    })
    return tags
  }, [status, tier, receivedFrom, receivedTo, admissionFrom, admissionTo])

  const removeTag = (tag) => {
    setPage(0)
    const nextParams = new URLSearchParams(searchParams)
    if (tag.reset) {
      Object.keys(tag.reset).forEach(name => nextParams.delete(name))
    } else if (tag.param) {
      nextParams.delete(tag.param)
    }
    setSearchParams(nextParams, { replace: true })
  }

  const initialLoading = loading && !data.items.length

  if (initialLoading) return (
    <div>
      <div className="claims-list-live-status" role="status" aria-live="polite" aria-atomic="true">Memuat data klaim...</div>
      <ClaimsListSkeleton />
    </div>
  )

  const firstVisible = data.total === 0 ? 0 : page * PAGE_SIZE + 1
  const lastVisible = page * PAGE_SIZE + data.items.length

  return (
    <div className="ckl-page">
      <div className="claims-list-live-status" role="status" aria-live="polite" aria-atomic="true">
        {error ? error : refreshing ? 'Memperbarui daftar klaim...' : `${data.total} klaim tersedia.`}
      </div>

      {/* Topbar */}
      <div className="ckl-topbar">
        <div>
          <div className="dashboard-title-row">
            <div className="header-icon-badge">
              <List size={20} />
            </div>
            <h1>Daftar Klaim</h1>
          </div>
          <p className="ckl-page-sub">Antrian klaim yang perlu diperiksa, diurutkan dari kebutuhan tindak lanjut tertinggi.</p>
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
      </div>

      {/* Filter */}
      <div className="ckl-filter-card">
        <div className="ckl-filter-top">
          <div className="ckl-search-box" style={{ position: 'relative' }}>
            <Search size={17} aria-hidden="true" />
            <input
              ref={searchInputRef}
              aria-label="Cari ID klaim, peserta, fasilitas, atau diagnosis"
              placeholder="Cari ID klaim, peserta, fasilitas, atau diagnosis…"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Escape') setSearchInput('') }}
            />
            {searchInput ? (
              <button type="button" className="ckl-clear-btn" aria-label="Hapus pencarian" onClick={() => setSearchInput('')}>
                <X size={14} aria-hidden="true" />
              </button>
            ) : (
              <span className="ckl-kbd" aria-hidden="true">Ctrl K</span>
            )}
          </div>
        </div>

        <div className="ckl-quick-chips">
          {QUICK_FILTERS.map(f => {
            const active = status === f.key
            const count = counts ? counts[f.countKey] : null
            return (
              <button
                type="button"
                key={f.key || 'all'}
                className="ckl-qchip"
                aria-pressed={active}
                onClick={() => updateFilter('status', f.key)}
              >
                {f.dot && <span className="ckl-qchip-dot" style={{ background: f.dot }} aria-hidden="true" />}
                {f.label}
                <span className="ckl-chip-count">{count == null ? '—' : count.toLocaleString('id-ID')}</span>
              </button>
            )
          })}
          <span className="ckl-quick-sep" aria-hidden="true" />
          <button
            type="button"
            className="ckl-adv-toggle"
            aria-expanded={showAdvanced}
            aria-controls="ckl-advanced"
            onClick={() => setShowAdvanced(v => !v)}
          >
            Filter lanjutan
            <svg className="caret" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
          </button>
        </div>

        <div className={`ckl-adv-wrap${showAdvanced ? ' open' : ''}`} inert={!showAdvanced}>
          <div className="ckl-adv-clip">
            <div className="ckl-adv-row" id="ckl-advanced">
          <div className="ckl-fld">
            <label className="ckl-fld-label" htmlFor="ckl-tier">Prioritas</label>
            <select id="ckl-tier" className="claims-filter-control" value={tier} onChange={e => updateFilter('tier', e.target.value)}>
              <option value="">Semua tingkat</option>
              <option value="high">Risiko Tinggi</option>
              <option value="medium">Risiko Sedang</option>
              <option value="low">Risiko Rendah</option>
            </select>
          </div>
          <div className="ckl-fld">
            <label className="ckl-fld-label" htmlFor="ckl-recd-from">Diterima dari</label>
            <input id="ckl-recd-from" className="claims-filter-control" type="date" value={receivedFrom} onChange={e => updateFilter('received_from', e.target.value)} />
          </div>
          <div className="ckl-fld">
            <label className="ckl-fld-label" htmlFor="ckl-recd-to">s/d</label>
            <input id="ckl-recd-to" className="claims-filter-control" type="date" value={receivedTo} onChange={e => updateFilter('received_to', e.target.value)} />
          </div>
          <div className="ckl-fld">
            <label className="ckl-fld-label" htmlFor="ckl-adm-from">Masuk dari</label>
            <input id="ckl-adm-from" className="claims-filter-control" type="date" value={admissionFrom} onChange={e => updateFilter('admission_from', e.target.value)} />
          </div>
          <div className="ckl-fld">
            <label className="ckl-fld-label" htmlFor="ckl-adm-to">s/d</label>
            <input id="ckl-adm-to" className="claims-filter-control" type="date" value={admissionTo} onChange={e => updateFilter('admission_to', e.target.value)} />
          </div>
          <div style={{ flex: 1 }} />
          <div className="ckl-adv-foot">
            {activeTags.map(tag => (
              <span className="ckl-tagx" key={tag.label}>
                {tag.label}
                <button type="button" className="ckl-tagx-btn" aria-label={`Hapus filter ${tag.label}`} onClick={() => removeTag(tag)}>
                  <X size={10} strokeWidth={2.6} aria-hidden="true" />
                </button>
              </span>
            ))}
            {activeFilters && (
              <button type="button" className="ckl-adv-reset" onClick={resetFilters}>
                <RotateCw size={12} strokeWidth={2.4} aria-hidden="true" /> Reset
              </button>
            )}
          </div>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="alert-disclaimer" role="alert" style={{ color: 'var(--error-text)', marginBottom: '0.9rem' }}>⚠ {error}</div>
      )}

      {/* Tabel */}
      <div className="ckl-table-card">
        <div className="ckl-table-head">
          <div className="ckl-th-title">
            <span className="ckl-th-icon"><ListChecks size={16} aria-hidden="true" /></span>
            Antrian Masuk
          </div>
          <div className="ckl-hcounts">
            <span className="ckl-hcount high">
              <span className="ckl-qchip-dot" style={{ background: 'var(--risk-high)' }} aria-hidden="true" />
              Prioritas tinggi
              <span className="num">{counts ? (counts.high_risk_claims ?? '—').toLocaleString('id-ID') : '—'}</span>
            </span>
            <span className="ckl-hcount review">
              <span className="ckl-qchip-dot" style={{ background: 'var(--risk-medium)' }} aria-hidden="true" />
              Perlu ditinjau
              <span className="num">{counts ? (counts.review_required_claims ?? '—').toLocaleString('id-ID') : '—'}</span>
            </span>
            <span className="ckl-hcount done">
              <span className="ckl-qchip-dot" style={{ background: 'var(--risk-low)' }} aria-hidden="true" />
              Diputuskan
              <span className="num">{counts ? (counts.verified_claims ?? '—').toLocaleString('id-ID') : '—'}</span>
            </span>
          </div>
          <div className="ckl-head-spacer" />
          <div className="ckl-sort-wrap">
            <ArrowUpDown size={13} aria-hidden="true" />
            <select
              className="ckl-sort-select"
              aria-label="Urutkan daftar klaim"
              value={sort}
              onChange={e => updateFilter('sort', e.target.value)}
            >
              <option value="priority">Urut: Prioritas</option>
              <option value="queue">Urut: antrean masuk</option>
              <option value="risk_desc">Nilai risiko ↓</option>
              <option value="risk_asc">Nilai risiko ↑</option>
              <option value="cost_desc">Biaya ↓</option>
              <option value="cost_asc">Biaya ↑</option>
              <option value="id">ID Klaim</option>
            </select>
          </div>
        </div>

        {data.items.length === 0 ? (
          <div className="ckl-empty-state">
            <EmptyState
              icon={SearchX}
              title="Tidak ada klaim yang cocok"
              hint={activeFilters
                ? 'Coba longgarkan kata kunci atau hapus sebagian filter yang aktif.'
                : 'Belum ada klaim yang masuk ke antrian saat ini.'}
              action={activeFilters
                ? (
                  <button type="button" className="ckl-adv-reset" onClick={resetFilters}>
                    <RotateCw size={12} strokeWidth={2.4} aria-hidden="true" /> Reset filter
                  </button>
                )
                : null}
            />
          </div>
        ) : (
        <div className="table-scroll-x">
          <table className="ckl-table">
            <thead>
              <tr>
                <th scope="col" className="ckl-rail" aria-hidden="true" style={{ width: 3, padding: 0, background: 'var(--accent-green-glow)', borderBottom: '1px solid rgba(16, 185, 129, 0.25)' }} />
                <th scope="col" style={{ minWidth: 210 }}>Klaim</th>
                <th scope="col" style={{ minWidth: 120 }}>Biaya</th>
                <th scope="col" style={{ minWidth: 180 }}>Skor Risiko</th>
                <th scope="col" style={{ minWidth: 170 }}>Status Pemeriksaan</th>
                <th scope="col" style={{ minWidth: 110 }}>Antrean</th>
                <th scope="col">Aksi</th>
              </tr>
            </thead>
            <tbody key={`${search}|${status}|${tier}|${sort}|${page}|${receivedFrom}|${receivedTo}|${admissionFrom}|${admissionTo}`}>
              {data.items.map((c, idx) => {
                const tierClass = ['pending', 'scanning'].includes(c.status) || c.risk_score == null
                  ? 'ckl-t-unknown'
                  : `ckl-t-${c.priority_tier === 'medium' ? 'medium' : c.priority_tier || 'low'}`
                const noteError = c.last_analysis_error
                  ? safeErrorMessage({ code: c.last_analysis_error_code, message: c.last_analysis_error })
                  : null
                const noteErrorColor = c.last_analysis_error ? 'var(--risk-high-text)' : 'var(--text-muted)'
                return (
                  <tr key={c.claim_id} className={`${tierClass} ckl-row-in`} style={{ '--i': idx }}>
                    <td className="ckl-rail" aria-hidden="true" />
                    <td>
                      <div className="ckl-claim-col">
                        <Link
                          className="claim-link"
                          to={`/investigate/${c.claim_id}`}
                          onClick={openClaim(c)}
                          aria-label={`Buka klaim ${c.claim_id}`}
                        >
                          {c.claim_id}
                        </Link>
                        <div className="ckl-cell-sub">{c.provider_id || 'Sumber klaim'}</div>
                        {c.diagnosis_primary && (
                          <span className="ckl-dx-chip" title={c.diagnosis_primary}>{c.diagnosis_primary}</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="ckl-cost">Rp {c.cost_claimed?.toLocaleString('id-ID')}</div>
                      <div className="ckl-los">
                        <Clock strokeWidth={2.2} aria-hidden="true" />
                        {c.length_of_stay} hari rawat
                      </div>
                    </td>
                    <td><RiskCell claim={c} /></td>
                    <td>
                      <StatusBadge claim={c} />
                      <StatusSub claim={c} errorMessage={noteError} color={noteErrorColor} />
                    </td>
                    <td><QueueCell claim={c} now={currentTime} /></td>
                    <td>
                      <Link
                        className="ckl-row-action"
                        to={`/investigate/${c.claim_id}`}
                        onClick={openClaim(c)}
                        aria-label={`Periksa klaim ${c.claim_id}`}
                      >
                        Periksa <ArrowRight strokeWidth={2.2} aria-hidden="true" />
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        )}

        {data.items.length > 0 && <p className="table-scroll-hint">Geser tabel ke samping untuk melihat status dan aksi →</p>}

        {/* Pagination */}
        <div className="ckl-table-foot">
          <span className="ckl-foot-info">
            Menampilkan <b>{firstVisible}–{lastVisible}</b> dari <b>{data.total.toLocaleString('id-ID')}</b> klaim
            &nbsp;·&nbsp; halaman {page + 1} dari {totalPages}
          </span>
          <div className="ckl-pager">
            <button
              type="button"
              className="ckl-pg-btn nav"
              disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
              aria-label="Halaman sebelumnya"
            >
              <ChevronLeft size={14} aria-hidden="true" />
            </button>
            {pageNumbers(page, totalPages).map((p, i) =>
              p === 'gap'
                ? <span className="ckl-pg-dots" key={`gap-${i}`} aria-hidden="true">…</span>
                : (
                  <button
                    type="button"
                    key={p}
                    className={`ckl-pg-btn${p === page ? ' active' : ''}`}
                    {...(p === page ? { 'aria-current': 'page' } : {})}
                    onClick={() => p !== page && setPage(p)}
                    aria-label={`Halaman ${p + 1}`}
                  >
                    {p + 1}
                  </button>
                )
            )}
            <button
              type="button"
              className="ckl-pg-btn nav"
              disabled={page + 1 >= totalPages}
              onClick={() => setPage(p => p + 1)}
              aria-label="Halaman berikutnya"
            >
              <ChevronRight size={14} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
