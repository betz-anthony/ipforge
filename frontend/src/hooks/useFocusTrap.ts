import { useEffect, useRef } from 'react'

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/**
 * Keyboard focus trap for modal dialogs / drawers.
 *
 * Attach the returned ref to the dialog container. On mount it moves focus into
 * the dialog (first autofocus target, else first focusable, else the container)
 * and remembers what was focused before; while mounted, Tab / Shift+Tab wrap
 * within the dialog so keyboard users cannot escape it behind the backdrop; on
 * unmount focus is restored to the previously-focused element.
 */
export function useFocusTrap<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    const previouslyFocused = document.activeElement as HTMLElement | null

    const focusables = () =>
      Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        el => el.offsetParent !== null || el === document.activeElement,
      )

    // Move focus into the dialog. Respect an existing autofocus target.
    const autofocus = node.querySelector<HTMLElement>('[autofocus]')
    const initial = autofocus ?? focusables()[0] ?? node
    if (initial === node && !node.hasAttribute('tabindex')) node.setAttribute('tabindex', '-1')
    initial.focus()

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const items = focusables()
      if (items.length === 0) {
        e.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (e.shiftKey && (active === first || !node.contains(active))) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && (active === last || !node.contains(active))) {
        e.preventDefault()
        first.focus()
      }
    }

    node.addEventListener('keydown', onKeyDown)
    return () => {
      node.removeEventListener('keydown', onKeyDown)
      previouslyFocused?.focus?.()
    }
  }, [])

  return ref
}
