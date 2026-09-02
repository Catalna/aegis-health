import { useState } from 'react'
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import './index.css'
import Logo from './Logo'
import Dashboard from './pages/Dashboard'
import ClaimsList from './pages/ClaimsList'
import ClaimIntake from './pages/ClaimIntake'
import Investigation from './pages/Investigation'
import Assessment from './pages/Assessment'
import Monitoring from './pages/Monitoring'
import DemoLoader from './pages/DemoLoader'
import MLEvaluation from './pages/MLEvaluation'
import { LayoutDashboard, List, Activity, Brain, FilePlus, Zap, Sun, Moon } from 'lucide-react'

function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const active = location.pathname

  // Theme Toggle state
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('j-ari-theme') || 'light'
    document.documentElement.setAttribute('data-theme', saved)
    return saved
  })

  const toggleTheme = () => {
    const nextTheme = theme === 'light' ? 'dark' : 'light'
    setTheme(nextTheme)
    document.documentElement.setAttribute('data-theme', nextTheme)
    localStorage.setItem('j-ari-theme', nextTheme)
  }

  const navItems = [
    { label: 'Dashboard Utama', path: '/', icon: <LayoutDashboard size={18} /> },
    { label: 'Daftar Klaim', path: '/claims', icon: <List size={18} /> },
    { label: 'Monitoring Center', path: '/monitoring', icon: <Activity size={18} /> },
    { label: 'Evaluasi Model ML', path: '/ml-eval', icon: <Brain size={18} /> },
  ]

  const toolItems = [
    { label: 'Single Intake', path: '/intake', icon: <FilePlus size={18} /> },
    { label: 'Batch Demo Loader', path: '/demo-loader', icon: <Zap size={18} /> },
  ]

  return (
    <aside className="sidebar">
      <div className="sidebar-logo" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <Logo width={34} height={34} />
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <h1 style={{ lineHeight: 1.1 }}>J-ARI</h1>
          <p style={{ margin: 0 }}>Agentic Risk Intelligence</p>
        </div>
      </div>
      <nav className="sidebar-nav">
        {navItems.map(item => (
          <button
            key={item.path}
            className={`nav-item ${active === item.path ? 'active' : ''}`}
            onClick={() => navigate(item.path)}
          >
            <span>{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>
      
      <div style={{ marginTop: '2rem', padding: '0 1rem', fontSize: '0.75rem', fontWeight: 'bold', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
        Tools & Simulasi
      </div>
      <nav className="sidebar-nav" style={{ marginTop: '0.5rem' }}>
        {toolItems.map(item => (
          <button
            key={item.path}
            className={`nav-item ${active === item.path ? 'active' : ''}`}
            onClick={() => navigate(item.path)}
          >
            <span>{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>
      
      <div style={{ padding: '1rem 1.5rem', borderTop: '1px solid var(--border)', marginTop: 'auto' }}>
        <div className="flex items-center justify-between" style={{ marginBottom: '0.75rem' }}>
          <div className="flex items-center gap-1 text-xs text-muted">
            <span className="status-dot online" />
            <span>System Online</span>
          </div>
          <button
            onClick={toggleTheme}
            className="btn btn-ghost"
            style={{
              padding: '0.35rem',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px solid var(--border)',
              cursor: 'pointer'
            }}
            title={theme === 'light' ? 'Ganti ke Mode Gelap' : 'Ganti ke Mode Terang'}
          >
            {theme === 'light' ? <Moon size={14} color="var(--text-secondary)" /> : <Sun size={14} color="var(--text-secondary)" />}
          </button>
        </div>
        <div className="text-xs text-muted">
          Backend: FastAPI + LanceDB
          <br/>
          Models: Mistral, XGBoost, IF
        </div>
      </div>
    </aside>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/claims" element={<ClaimsList />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/ml-eval" element={<MLEvaluation />} />
            <Route path="/intake" element={<ClaimIntake />} />
            <Route path="/demo-loader" element={<DemoLoader />} />
            <Route path="/investigate/:claimId" element={<Investigation />} />
            <Route path="/assessment/:claimId" element={<Assessment />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
