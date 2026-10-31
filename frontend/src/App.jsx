import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
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
import { LayoutDashboard, List, Activity, Brain, FilePlus, Menu, X } from 'lucide-react'

const MOBILE_NAV_ITEMS = [
  { label: 'Dashboard', path: '/', icon: <LayoutDashboard size={18} /> },
  { label: 'Klaim', path: '/claims', icon: <List size={18} /> },
  { label: 'Monitoring', path: '/monitoring', icon: <Activity size={18} /> },
  { label: 'Evaluasi', path: '/ml-eval', icon: <Brain size={18} /> },
  { label: 'Input', path: '/intake', icon: <FilePlus size={18} /> },
]

function Sidebar() {
  const location = useLocation()
  const sidebarRef = useRef(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [pill, setPill] = useState({ y: 0, h: 44, show: false })
  const [pillAnimated, setPillAnimated] = useState(false)

  // Pill aktif "meluncur" ke menu tujuan: ukur posisi link aktif,
  // gerakkan satu elemen indikator (bukan background per-link).
  const measurePill = useCallback(() => {
    const bar = sidebarRef.current
    const active = bar?.querySelector('.nav-item.active')
    if (!bar || !active) {
      setPill(p => ({ ...p, show: false }))
      return
    }
    const barRect = bar.getBoundingClientRect()
    const activeRect = active.getBoundingClientRect()
    setPill({ y: activeRect.top - barRect.top, h: activeRect.height, show: true })
  }, [])

  useLayoutEffect(() => {
    measurePill()
  }, [location.pathname, measurePill])

  // Ukuran sidebar berubah saat resize/rotasi: ukur ulang supaya pill tidak nyangkut.
  useEffect(() => {
    window.addEventListener('resize', measurePill)
    return () => window.removeEventListener('resize', measurePill)
  }, [measurePill])

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

  const closeMenu = useCallback(() => setMenuOpen(false), [])

  useEffect(() => {
    closeMenu()
  }, [location.pathname, closeMenu])

  useEffect(() => {
    if (!menuOpen) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') closeMenu()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [menuOpen, closeMenu])

  return (
    <>
    <div className="compact-header">
      <div className="compact-header-brand"><Logo width={32} height={32} /><strong>AEGIS</strong></div>
      <span className="compact-header-title">Pusat Pemeriksaan Klaim</span>
      <button
        className="mobile-menu-toggle"
        type="button"
        aria-label={menuOpen ? 'Tutup navigasi' : 'Buka navigasi'}
        aria-expanded={menuOpen}
        aria-controls="primary-navigation"
        onClick={() => setMenuOpen(value => !value)}
      >
        {menuOpen ? <X size={21} aria-hidden="true" /> : <Menu size={21} aria-hidden="true" />}
      </button>
    </div>
    {menuOpen && <button className="sidebar-backdrop" type="button" aria-label="Tutup navigasi" onClick={closeMenu} />}
    <aside ref={sidebarRef} id="primary-navigation" className={`sidebar${menuOpen ? ' is-open' : ''}`} aria-label="Navigasi utama">
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
            onClick={closeMenu}
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
            onClick={closeMenu}
          >
            <span aria-hidden="true">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
      
      <div className="sidebar-status">
        <div className="sidebar-status-line">
          <span className="status-dot online" aria-hidden="true" />
          <span>Sistem aktif</span>
        </div>
        <div className="sidebar-status-note">
          Layanan pemeriksaan aktif
          <br />
          Data klaim tersimpan aman
        </div>
      </div>
    </aside>
    <nav className="mobile-nav" aria-label="Navigasi utama">
      {MOBILE_NAV_ITEMS.map(item => (
        <NavLink
          key={item.path}
          to={item.path}
          end={item.path === '/'}
          className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}
        >
          {item.icon}
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
    </>
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
