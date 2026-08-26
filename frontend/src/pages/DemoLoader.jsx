import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { demoApi, createDemoStream } from '../api'

export default function DemoLoader() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [logs, setLogs] = useState([])
  const [status, setStatus] = useState('idle') // idle, running, done, error
  const startedRef = useRef(false)

  const startDemo = async () => {
    try {
      setLoading(true)
      setStatus('running')
      setLogs([])
      setProgress(0)
      await demoApi.start()

      // Stream progress — tiap klien punya queue sendiri di backend (tanpa race)
      createDemoStream({
        onStatus: (data) => setLogs(prev => [...prev, `[STATUS] ${typeof data === 'string' ? data : JSON.stringify(data)}`]),
        onProgress: (data) => {
          const pct = Math.round((data.current / data.total) * 100)
          setProgress(pct)
          setLogs(prev => [...prev, `[PROGRESS] ${data.current}/${data.total} klaim...`])
        },
        onDone: (data) => {
          setLogs(prev => [...prev, `[DONE] ${data || 'Generasi selesai'}`])
          setStatus('done')
          setProgress(100)
          setLoading(false)
        },
        onError: (data) => {
          setLogs(prev => [...prev, `[ERROR] ${typeof data === 'string' ? data : data?.message || 'unknown'}`])
          setStatus('error')
          setLoading(false)
        },
      })
    } catch (err) {
      setLogs(prev => [...prev, `[ERROR] Gagal memulai generasi: ${err.message}`])
      setStatus('error')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto py-8">
      <div className="page-header mb-8">
        <h2 className="glow-text">Batch Demo Loader</h2>
        <p>Hasilkan klaim sintetis (normal + fraud) dan simpan ke database + index LanceDB.</p>
      </div>

      <div className="card mb-6">
        <h3 className="card-title">Synthetic Data Generator</h3>
        <p className="text-muted text-sm mb-6">
          Generator ini akan membuat klaim simulasi berdasarkan tarif INA-CBG, lalu menyisipkan
          7 jenis skenario fraud (Upcoding, Phantom Billing, Repeat Billing, Cloning, Unbundling,
          Prolonged LOS, Inflated Bills). Setelah tersimpan, klaim otomatis di-index ke LanceDB
          agar deteksi similarity mengenali data baru, dan graph metrics faskes di-refresh.
        </p>

        <div className="mb-6">
          <button
            className="btn btn-primary w-full justify-center text-lg py-3"
            onClick={startDemo}
            disabled={loading || status === 'running'}
          >
            {loading ? 'Sedang Men-generate...' : 'Generate Klaim Demo Sekarang'}
          </button>
        </div>

        {status !== 'idle' && (
          <div className="mt-6">
            <div className="flex justify-between text-sm mb-2 font-bold">
              <span>Progress</span>
              <span>{progress}%</span>
            </div>
            <div className="progress-bar mb-4" style={{ height: 12 }}>
              <div
                className="progress-fill"
                style={{
                  width: `${progress}%`,
                  background: status === 'error' ? 'var(--risk-high)' : 'var(--accent-green)',
                }}
              />
            </div>

            <div className="terminal-window h-64 overflow-y-auto">
              <div className="terminal-header">Generation Logs</div>
              {logs.map((log, i) => (
                <div key={i} className="mb-1">{log}</div>
              ))}
              {status === 'running' && <div className="text-muted animate-pulse mt-2">Menunggu proses database...</div>}
            </div>
          </div>
        )}
      </div>

      {status === 'done' && (
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-secondary w-full justify-center" onClick={() => navigate('/claims')}>
            Lihat Daftar Klaim
          </button>
          <button className="btn btn-ghost w-full justify-center" onClick={() => navigate('/')}>
            Kembali ke Dashboard
          </button>
        </div>
      )}
    </div>
  )
}
