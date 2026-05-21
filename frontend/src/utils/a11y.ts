import type React from 'react'

/**
 * Props that make a non-interactive element (e.g. a clickable table row)
 * operable by keyboard: focusable, button-semantic, and activated by
 * Enter or Space in addition to click.
 */
export function rowActivation(onActivate: () => void) {
  return {
    tabIndex: 0,
    role: 'button' as const,
    onClick: onActivate,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        onActivate()
      }
    },
  }
}
