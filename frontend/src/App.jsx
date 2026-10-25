import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import './index.css'
import Logo from './Logo'
import ErrorBoundary from './ErrorBoundary'
import ToastHost from './Toast'
import Dashboard from './pages/Dashboard'
import ClaimsList from './pages/ClaimsList'
import ClaimIntake from './pages/ClaimIntake'
import Investigation from './pages/Investigation'
import Assessment from './pages/Assessment'
import Monitoring from './pages/Monitoring'
import MLEvaluation from './pages/MLEvaluation'
import { LayoutDashboard, List, Activity, Brain, FilePlus } from 'lucide-react'

function Sidebar() {
  const location = useLocation()
  const sidebarRef = useRef(null)
  const [pill, setPill] = useState({ y: 0, h: 44, show: false })
  const [pillAnimated, setPillAnimated] = useState(false)

  // Pill aktif "meluncur" ke menu tujuan: ukur posisi link aktif,
  // gerakkan satu elemen indikator (bukan background per-link).
  useLayoutEffect(() => {
    const bar = sidebarRef.current
    const active = bar?.querySelector('.nav-item.active')
    if (!bar || !active) {
      setPill(p => ({ ...p, show: false }))
      return
    }
    const barRect = bar.getBoundingClientRect()
    const activeRect = active.getBoundingClientRect()
    setPill({ y: activeRect.top - barRect.top, h: activeRect.height, show: true })
  }, [location.pathname])

  // Jangan animasikan posisi awal saat halaman pertama kali dibuka.
  useEffect(() => {
    if (!pill.show || pillAnimated) return undefined
    const raf = requestAnimationFrame(() => setPillAnimated(true))
    return () => cancelAnimationFrame(raf)
  }, [pill.show, pillAnimated])

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
    <aside ref={sidebarRef} className="sidebar" aria-label="Navigasi utama">
      <span
        className={`nav-pill${pillAnimated ? ' is-animated' : ''}`}
        style={{ transform: `translateY(${pill.y}px)`, height: pill.h, opacity: pill.show ? 1 : 0 }}
        aria-hidden="true"
      />
      <div className="sidebar-logo">
        <Logo width={34} height={34} />
        <div className="sidebar-brand-copy">
          <div className="sidebar-brand-title">AEGIS</div>
          <p>Pusat Pemeriksaan Klaim</p>
        </div>
      </div>
      <nav className="sidebar-nav" aria-label="Menu utama">
        {navItems.map(item => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <span aria-hidden="true">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
      
      <div className="sidebar-section-label">Alat Bantu</div>
      <nav className="sidebar-nav" aria-label="Menu alat bantu">
        {toolItems.map(item => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <span aria-hidden="true">{item.icon}</span>
            {item.label}
          </NavLink>
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

function RoutedMain() {
  const location = useLocation()
  const mainRef = useRef(null)

  useEffect(() => {
    mainRef.current?.focus()
  }, [location.pathname])

  return (
    <main ref={mainRef} id="main-content" className="main-content" tabIndex="-1">
      {/* Keyed by pathname so the arrival animation replays on every nav.
          ErrorBoundary di dalam sini ikut ter-reset saat pindah halaman. */}
      <div className="route-reveal" key={location.pathname}>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/claims" element={<ClaimsList />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/ml-eval" element={<MLEvaluation />} />
            <Route path="/intake" element={<ClaimIntake />} />
            <Route path="/investigate/:claimId" element={<Investigation />} />
            <Route path="/assessment/:claimId" element={<Assessment />} />
          </Routes>
        </ErrorBoundary>
      </div>
    </main>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <a className="skip-link" href="#main-content">Lewati ke isi utama</a>
        <Sidebar />
        <RoutedMain />
        <ToastHost />
      </div>
    </BrowserRouter>
  )
}

export default App
