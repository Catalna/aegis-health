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
import MLEvaluation from './pages/MLEvaluation'
import { LayoutDashboard, List, Activity, Brain, FilePlus } from 'lucide-react'

function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const active = location.pathname

  const navItems = [
    { label: 'Dashboard Utama', path: '/', icon: <LayoutDashboard size={18} /> },
    { label: 'Daftar Klaim', path: '/claims', icon: <List size={18} /> },
    { label: 'Pemantauan Sistem', path: '/monitoring', icon: <Activity size={18} /> },
    { label: 'Evaluasi Ketepatan', path: '/ml-eval', icon: <Brain size={18} /> },
  ]

  const toolItems = [
    { label: 'Input Klaim', path: '/intake', icon: <FilePlus size={18} /> },
  ]

  return (
    <aside className="sidebar" aria-label="Navigasi utama">
      <div className="sidebar-logo">
        <Logo width={34} height={34} />
        <div className="sidebar-brand-copy">
          <h1>J-ARI</h1>
          <p>Pusat Pemeriksaan Klaim</p>
        </div>
      </div>
      <nav className="sidebar-nav" aria-label="Menu utama">
        {navItems.map(item => (
          <button
            key={item.path}
            className={`nav-item ${active === item.path ? 'active' : ''}`}
            onClick={() => navigate(item.path)}
          >
            <span aria-hidden="true">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>
      
      <div className="sidebar-section-label" style={{ marginTop: '2rem', padding: '0 1rem', fontSize: '0.75rem', fontWeight: 'bold', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
         Alat Bantu
      </div>
      <nav className="sidebar-nav" aria-label="Menu alat bantu" style={{ marginTop: '0.5rem' }}>
        {toolItems.map(item => (
          <button
            key={item.path}
            className={`nav-item ${active === item.path ? 'active' : ''}`}
            onClick={() => navigate(item.path)}
          >
            <span aria-hidden="true">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>
      
      <div className="sidebar-status" style={{ padding: '1rem 1.5rem', borderTop: '1px solid var(--border)', marginTop: 'auto' }}>
        <div className="flex items-center gap-1 text-xs text-muted">
          <span className="status-dot online" aria-hidden="true" />
          <span>Sistem aktif</span>
        </div>
        <div className="text-xs text-muted" style={{ marginTop: '4px' }}>
          Layanan pemeriksaan aktif
          <br />
          Data klaim tersimpan aman
        </div>
      </div>
    </aside>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <a className="skip-link" href="#main-content">Lewati ke isi utama</a>
        <Sidebar />
        <main id="main-content" className="main-content" tabIndex="-1">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/claims" element={<ClaimsList />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/ml-eval" element={<MLEvaluation />} />
            <Route path="/intake" element={<ClaimIntake />} />
            <Route path="/investigate/:claimId" element={<Investigation />} />
            <Route path="/assessment/:claimId" element={<Assessment />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
