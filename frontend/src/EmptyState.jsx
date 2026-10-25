import { SearchX } from 'lucide-react'

/**
 * Komponen empty state saat data kosong atau hasil filter nihil.
 */
export default function EmptyState({ icon: Icon = SearchX, title, hint, action }) {
  return (
    <div className="empty-state">
      <span className="empty-state-icon" aria-hidden="true">
        <Icon size={22} />
      </span>
      <strong className="empty-state-title">{title}</strong>
      {hint && <p className="empty-state-hint">{hint}</p>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  )
}
