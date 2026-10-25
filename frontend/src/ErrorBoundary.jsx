import { Component } from 'react'
import { AlertTriangle, RotateCcw } from 'lucide-react'

/**
 * Error boundary area konten: menangkap error render/lifecycle agar tidak
 * blank putih, serta menampilkan fallback UI dengan tombol pemulihan.
 */
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Stack komponen membantu menunjuk file/komponen penyebab di console.
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  handleRetry = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="error-wrapper">
        <div className="status-message error" role="alert">
          <AlertTriangle size={24} className="mb-1 text-error" aria-hidden="true" />
          <strong>Halaman ini gagal dimuat</strong>
          <p>
            Terjadi kesalahan saat menampilkan halaman. Sidebar dan menu lain tetap
            bisa dipakai — coba muat ulang halaman ini.
          </p>
          {import.meta.env.DEV && (
            <pre className="error-boundary-detail">{error.message}</pre>
          )}
          <div className="error-boundary-actions">
            <button type="button" className="btn btn-primary" onClick={this.handleRetry}>
              <RotateCcw size={14} aria-hidden="true" />
              Coba lagi
            </button>
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => window.location.reload()}
            >
              Muat ulang halaman
            </button>
          </div>
        </div>
      </div>
    )
  }
}
