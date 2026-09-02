import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, AlertCircle, CheckCircle2, Clock, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { claimsApi } from '../api'

const TIER_LABELS = { high: 'Tinggi', medium: 'Sedang', low: 'Rendah' }

function RiskBadge({ tier }) {
  if (!tier) return <span className="text-muted" style={{ fontSize: '0.8rem' }}>—</span>
  if (tier === 'high') return <span className="badge badge-high"><AlertCircle size={12} /> Tinggi</span>
  if (tier === 'medium') return <span className="badge badge-medium"><AlertCircle size={12} /> Sedang</span>
  return <span className="badge badge-low"><CheckCircle2 size={12} /> Rendah</span>
}

function ScoreBar({ score, tier }) {
  const colors = { high: 'var(--risk-high)', medium: 'var(--risk-medium)', low: 'var(--risk-low)' }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
      <div className="progress-bar" style={{ width: 80, height: 6, background: 'var(--bg-primary)', overflow: 'hidden', borderRadius: '4px', border: '1px solid var(--border)' }}>
        <div className="progress-fill" style={{ width: `${score}%`, background: colors[tier] || 'var(--text-muted)', height: '100%', borderRadius: '4px' }} />
      </div>
      <span style={{ fontSize: '0.8rem', fontWeight: 700, color: colors[tier] || 'var(--text-muted)', minWidth: 28, fontFamily: 'JetBrains Mono, monospace' }}>{score ?? '—'}</span>
    </div>
  )
}

const PAGE_SIZE = 25

export default function ClaimsList() {
  const navigate = useNavigate()
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filter state
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [status, setStatus] = useState('')
  const [tier, setTier] = useState('')
  const [sort, setSort] = useState('priority')
  const [page, setPage] = useState(0)

  const fetchClaims = useCallback(async () => {
    try {
      setError(null)
      const res = await claimsApi.list({
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: search || undefined,
        status: status || undefined,
        tier: tier || undefined,
        sort,
      })
      setData(res.data)
    } catch (err) {
      setError('Gagal memuat daftar klaim. Pastikan backend aktif.')
    } finally {
      setLoading(false)
    }
  }, [page, search, status, tier, sort])

  useEffect(() => {
    fetchClaims()
    const interval = setInterval(fetchClaims, 15000)
    return () => clearInterval(interval)
  }, [fetchClaims])

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => { setSearch(searchInput); setPage(0) }, 350)
    return () => clearTimeout(t)
  }, [searchInput])

  const handleRowClick = (claim) => {
    sessionStorage.setItem(`claim_${claim.claim_id}`, JSON.stringify(claim))
    navigate(`/investigate/${claim.claim_id}`)
  }

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
  const activeFilters = search || status || tier

  if (loading && !data.items.length) return <div className="p-8 text-center text-muted">Memuat data klaim...</div>

  return (
    <div>
      <div className="page-header">
        <h2 className="glow-text" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Search size={24} color="var(--accent-green)" />
          Daftar Klaim
        </h2>
        <p>Antrian prioritas klaim — diurutkan dari risiko tertinggi yang belum diverifikasi.</p>
      </div>

      {/* Toolbar filter */}
      <div className="card mb-3" style={{ padding: '0.75rem 1rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: '1 1 220px', minWidth: 180 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              className="form-input"
              placeholder="Cari ID klaim / pasien / faskes / diagnosis..."
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              style={{ paddingLeft: 30, fontSize: '0.82rem' }}
            />
            {searchInput && (
              <button onClick={() => setSearchInput('')} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                <X size={14} />
              </button>
            )}
          </div>

          <select className="form-select" value={status} onChange={e => { setStatus(e.target.value); setPage(0) }} style={{ width: 'auto', fontSize: '0.82rem' }}>
            <option value="">Semua Status</option>
            <option value="pending">Menunggu</option>
            <option value="processed">Terproses AI</option>
            <option value="verified">Diverifikasi</option>
          </select>

          <select className="form-select" value={tier} onChange={e => { setTier(e.target.value); setPage(0) }} style={{ width: 'auto', fontSize: '0.82rem' }}>
            <option value="">Semua Prioritas</option>
            <option value="high">Risiko Tinggi</option>
            <option value="medium">Risiko Sedang</option>
            <option value="low">Risiko Rendah</option>
          </select>

          <select className="form-select" value={sort} onChange={e => { setSort(e.target.value); setPage(0) }} style={{ width: 'auto', fontSize: '0.82rem' }}>
            <option value="priority">Urut: Prioritas</option>
            <option value="risk_desc">Skor Risiko ↓</option>
            <option value="risk_asc">Skor Risiko ↑</option>
            <option value="cost_desc">Biaya ↓</option>
            <option value="cost_asc">Biaya ↑</option>
            <option value="id">ID Klaim</option>
          </select>

          {activeFilters && (
            <button className="btn btn-ghost" style={{ fontSize: '0.75rem' }} onClick={() => { setSearchInput(''); setStatus(''); setTier(''); setSort('priority'); setPage(0) }}>
              Reset Filter
            </button>
          )}

          <span className="text-xs text-muted" style={{ marginLeft: 'auto' }}>
            {data.total.toLocaleString('id-ID')} klaim
          </span>
        </div>
      </div>

      {error && <div className="alert-disclaimer mb-3" style={{ color: 'var(--risk-high)' }}>⚠ {error}</div>}

      <div className="card" style={{ padding: 0 }}>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Claim ID</th>
                <th>Faskes</th>
                <th>Diagnosis</th>
                <th>Biaya Klaim</th>
                <th>LOS</th>
                <th>Risk Score</th>
                <th>Prioritas</th>
                <th>Status Verifikasi</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map(c => (
                <tr key={c.claim_id} onClick={() => handleRowClick(c)} style={{ cursor: 'pointer', opacity: c.status === 'verified' ? 0.75 : 1 }}>
                  <td><span className="font-mono" style={{ fontSize: '0.78rem' }}>{c.claim_id}</span></td>
                  <td>
                    <div style={{ fontWeight: 500 }}>{c.provider_id}</div>
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>via Integrasi Faskes</div>
                  </td>
                  <td><span className="badge badge-blue">{c.diagnosis_primary}</span></td>
                  <td>Rp {c.cost_claimed?.toLocaleString('id-ID')}</td>
                  <td>{c.length_of_stay} hr</td>
                  <td>
                    {c.status === 'pending' || !c.risk_score
                      ? <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>N/A</span>
                      : <ScoreBar score={Math.round(c.risk_score)} tier={c.priority_tier || 'low'} />}
                  </td>
                  <td>
                    {c.status === 'pending'
                      ? <span className="badge" style={{ background: 'var(--bg-card-hover)', color: 'var(--text-muted)' }}><Clock size={12}/> Menunggu</span>
                      : <RiskBadge tier={c.priority_tier} />}
                  </td>
                  <td>
                    {c.status === 'verified'
                      ? <div>
                          <span className="badge" style={{ background: 'var(--risk-low-bg)', color: 'var(--risk-low)', border: '1px solid rgba(16, 185, 129, 0.15)', fontSize: '0.68rem' }}>✓ Selesai</span>
                          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 2 }}>{c.human_decision}</div>
                        </div>
                      : c.status === 'processed'
                        ? <span className="badge" style={{ background: 'var(--risk-medium-bg)', color: 'var(--warning)', border: '1px solid rgba(245, 158, 11, 0.15)', fontSize: '0.68rem' }}>Menunggu Verifikasi</span>
                        : <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>—</span>
                    }
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center text-muted" style={{ padding: '2rem' }}>
                    Tidak ada klaim yang cocok dengan filter.
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
