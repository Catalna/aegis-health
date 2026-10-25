import { flushSync } from 'react-dom'

/**
 * Wrapper navigasi dengan View Transitions API (sinkron via flushSync),
 * dengan fallback ke navigasi standar jika tidak didukung atau reduce-motion aktif.
 */
export function navigateWithTransition(navigate, to, before) {
  if (before) before()

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (typeof document.startViewTransition !== 'function' || reduceMotion) {
    navigate(to)
    return
  }

  document.startViewTransition(() => {
    flushSync(() => navigate(to))
  })
}
