import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

// Two-key "g + X" navigation shortcuts. Standard pattern from GitHub / Linear.
const NAV_TARGETS: Record<string, string> = {
  d: '/',
  s: '/subnets',
  v: '/vlans',
  a: '/addresses',
  h: '/dhcp',
  n: '/dns',
  q: '/requests',
  l: '/alerts',
  u: '/audit',
}

export const SHORTCUT_LIST: Array<[string, string]> = [
  ['g d', 'Dashboard'],
  ['g s', 'Subnets'],
  ['g v', 'VLANs'],
  ['g a', 'Addresses'],
  ['g h', 'DHCP'],
  ['g n', 'DNS'],
  ['g q', 'Requests'],
  ['g l', 'Alerts'],
  ['g u', 'Audit log'],
  ['?',   'Show this cheatsheet'],
  ['Esc', 'Close cheatsheet / dialogs'],
]

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

export function useGlobalShortcuts() {
  const navigate = useNavigate()
  const [cheatsheetOpen, setCheatsheetOpen] = useState(false)
  const [pendingG, setPendingG] = useState(false)

  useEffect(() => {
    let gResetTimer: ReturnType<typeof setTimeout> | null = null

    const handler = (e: KeyboardEvent) => {
      // Never intercept while user is typing into a field.
      if (isTypingTarget(e.target)) return
      if (e.ctrlKey || e.metaKey || e.altKey) return

      // Cheatsheet toggles
      if (e.key === '?') {
        e.preventDefault()
        setCheatsheetOpen(true)
        return
      }
      if (e.key === 'Escape' && cheatsheetOpen) {
        setCheatsheetOpen(false)
        return
      }

      // "g" leader
      if (e.key === 'g' && !pendingG) {
        setPendingG(true)
        if (gResetTimer) clearTimeout(gResetTimer)
        gResetTimer = setTimeout(() => setPendingG(false), 1200)
        return
      }
      if (pendingG) {
        if (gResetTimer) clearTimeout(gResetTimer)
        setPendingG(false)
        const target = NAV_TARGETS[e.key.toLowerCase()]
        if (target) {
          e.preventDefault()
          navigate(target)
        }
      }
    }

    window.addEventListener('keydown', handler)
    return () => {
      window.removeEventListener('keydown', handler)
      if (gResetTimer) clearTimeout(gResetTimer)
    }
  }, [navigate, pendingG, cheatsheetOpen])

  return { cheatsheetOpen, closeCheatsheet: () => setCheatsheetOpen(false), pendingG }
}
