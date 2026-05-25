/**
 * Property 10: Dark/Light Mode Preference Persists Across Page Loads
 *
 * For any theme preference ("dark" or "light") set by the user, reloading the
 * Frontend SHALL apply that same theme before rendering visible content, with
 * no flash of the opposite theme.
 *
 * **Validates: Requirements 6.2, 6.3, 6.4**
 */

import { cleanup, render, act } from '@testing-library/react'
import * as fc from 'fast-check'
import { afterEach, describe, it, vi, beforeEach } from 'vitest'
import { ThemeToggle } from '../ThemeToggle'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Theme = 'dark' | 'light'

// ---------------------------------------------------------------------------
// In-memory localStorage mock
// ---------------------------------------------------------------------------

function createLocalStorageMock() {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
    get length() { return Object.keys(store).length },
    key: (index: number) => Object.keys(store)[index] ?? null,
  }
}

// ---------------------------------------------------------------------------
// matchMedia mock factory
// ---------------------------------------------------------------------------

function mockMatchMedia(prefersDark: boolean) {
  return vi.fn().mockImplementation((query: string) => ({
    matches: query === '(prefers-color-scheme: dark)' ? prefersDark : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Simulate the inline FOUC-prevention script from index.html */
function simulateFoucScript(storedTheme: Theme | null, prefersDark: boolean) {
  if (storedTheme === 'dark' || (!storedTheme && prefersDark)) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

let localStorageMock: ReturnType<typeof createLocalStorageMock>

beforeEach(() => {
  // Create a fresh localStorage mock for each test
  localStorageMock = createLocalStorageMock()
  vi.stubGlobal('localStorage', localStorageMock)

  // Default matchMedia stub (no system dark preference)
  vi.stubGlobal('matchMedia', mockMatchMedia(false))

  // Reset DOM
  document.documentElement.classList.remove('dark')
})

afterEach(() => {
  cleanup()
  document.documentElement.classList.remove('dark')
  vi.unstubAllGlobals()
})

// ---------------------------------------------------------------------------
// Property tests
// ---------------------------------------------------------------------------

describe('Property 10: Dark/Light Mode Preference Persists Across Page Loads', () => {
  /**
   * Sub-property A: After mount, the CSS class on <html> matches the stored
   * theme (simulating a page reload where the FOUC script ran first).
   */
  it('applies the stored theme class to <html> on mount (no FOUC)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<Theme>('dark', 'light'),
        (storedTheme) => {
          // Reset between iterations
          localStorageMock.clear()
          document.documentElement.classList.remove('dark')

          // 1. Write the preference to localStorage (user set it on a previous visit)
          localStorageMock.setItem('theme', storedTheme)

          // 2. Simulate the inline FOUC-prevention script that runs before React
          simulateFoucScript(storedTheme, false)

          // 3. Render the component (simulates React hydration)
          act(() => {
            render(<ThemeToggle />)
          })

          // 4. Assert the correct class is present on <html>
          const hasDark = document.documentElement.classList.contains('dark')
          const result = storedTheme === 'dark' ? hasDark === true : hasDark === false

          cleanup()
          document.documentElement.classList.remove('dark')

          return result
        },
      ),
      { numRuns: 20 },
    )
  })

  /**
   * Sub-property B: After toggling, localStorage.theme is updated to the
   * opposite theme value.
   */
  it('persists the new theme to localStorage after toggling', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<Theme>('dark', 'light'),
        (initialTheme) => {
          // Reset between iterations
          localStorageMock.clear()
          document.documentElement.classList.remove('dark')

          // Set up initial state
          localStorageMock.setItem('theme', initialTheme)
          simulateFoucScript(initialTheme, false)

          // Render the component
          const { getByRole } = render(<ThemeToggle />)

          const expectedAfterToggle: Theme = initialTheme === 'dark' ? 'light' : 'dark'

          // Click the toggle button
          act(() => {
            getByRole('button').click()
          })

          // Assert localStorage was updated to the new theme
          const storedAfterToggle = localStorageMock.getItem('theme')
          const classAfterToggle = document.documentElement.classList.contains('dark')

          const storageCorrect = storedAfterToggle === expectedAfterToggle
          const classCorrect =
            expectedAfterToggle === 'dark' ? classAfterToggle === true : classAfterToggle === false

          cleanup()
          document.documentElement.classList.remove('dark')

          return storageCorrect && classCorrect
        },
      ),
      { numRuns: 20 },
    )
  })

  /**
   * Sub-property C: When no localStorage preference exists, the component
   * falls back to the system prefers-color-scheme and persists that choice.
   */
  it('falls back to prefers-color-scheme when no stored preference exists', () => {
    fc.assert(
      fc.property(
        fc.boolean(), // true = system prefers dark
        (prefersDark) => {
          // Reset between iterations
          localStorageMock.clear()
          document.documentElement.classList.remove('dark')

          // Override matchMedia for this iteration
          vi.stubGlobal('matchMedia', mockMatchMedia(prefersDark))

          // No stored theme â€” simulate fresh visit
          simulateFoucScript(null, prefersDark)

          act(() => {
            render(<ThemeToggle />)
          })

          // After mount + reconciliation effect, the class should match system pref
          const hasDark = document.documentElement.classList.contains('dark')
          const result = prefersDark ? hasDark === true : hasDark === false

          cleanup()
          document.documentElement.classList.remove('dark')

          return result
        },
      ),
      { numRuns: 20 },
    )
  })
})
