import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, AlertTriangle, X } from 'lucide-react'

/**
 * Sistem notifikasi toast ringan untuk feedback aksi user.
 */

const listeners = new Set()
let nextId = 0

export function toast(message, { type = 'success', duration = 3600 } = {}) {
  const item = { id: ++nextId, message, type, duration }
  listeners.forEach(fn => fn(item))
}

const ICONS = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: CheckCircle2,
}

function ToastItem({ item, onDismiss }) {
  const [leaving, setLeaving] = useState(false)
  const timerRef = useRef(null)
  const remainingRef = useRef(item.duration)
  const startedRef = useRef(0)

  const schedule = (ms) => {
    clearTimeout(timerRef.current)
    startedRef.current = Date.now()
    timerRef.current = setTimeout(() => setLeaving(true), ms)
  }

  useEffect(() => {
    schedule(remainingRef.current)
    return () => clearTimeout(timerRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Setelah animasi keluar selesai, kabari host untuk hapus dari stack
  useEffect(() => {
    if (!leaving) return undefined
    const t = setTimeout(() => onDismiss(item.id), 180)
    return () => clearTimeout(t)
  }, [leaving, item.id, onDismiss])

  const pause = () => {
    clearTimeout(timerRef.current)
    remainingRef.current = Math.max(400, remainingRef.current - (Date.now() - startedRef.current))
  }
  const resume = () => schedule(remainingRef.current)

  const Icon = ICONS[item.type] || ICONS.info

  return (
    <div
      className={`toast toast-${item.type}${leaving ? ' is-leaving' : ''}`}
      onMouseEnter={pause}
      onMouseLeave={resume}
      onFocus={pause}
      onBlur={(e) => {
        // focusout juga terpicu saat pindah antar anak; resume hanya kalau fokus keluar toast
        if (!e.currentTarget.contains(e.relatedTarget)) resume()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setLeaving(true)
      }}
    >
      <Icon size={17} aria-hidden="true" className="toast-icon" />
      <p className="toast-msg">{item.message}</p>
      <button
        type="button"
        className="toast-close"
        aria-label="Tutup notifikasi"
        onClick={() => setLeaving(true)}
      >
        <X size={13} aria-hidden="true" />
      </button>
    </div>
  )
}

export default function ToastHost() {
  const [items, setItems] = useState([])

  useEffect(() => {
    const add = (item) => setItems(prev => [...prev.slice(-2), item])
    listeners.add(add)
    return () => listeners.delete(add)
  }, [])

  const dismiss = (id) => setItems(prev => prev.filter(t => t.id !== id))

  return (
    <div className="toast-viewport" aria-live="polite" aria-atomic="false">
      {items.map(item => (
        <ToastItem key={item.id} item={item} onDismiss={dismiss} />
      ))}
    </div>
  )
}
