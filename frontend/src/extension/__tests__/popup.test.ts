/**
 * Unit tests for extension popup rendering (Task 15.4)
 *
 * Tests the three render functions exposed by popup.js:
 *   - renderPrediction(prediction) — renders label, confidence bar, explanation
 *   - renderError(message)         — renders error; 'NO_TEXT' → specific message
 *   - showLoading()                — shows loading spinner, hides result/error
 *
 * Strategy: set up the popup HTML DOM structure in jsdom, mock the chrome
 * extension APIs, then load popup.js via readFileSync + Function so the
 * module-level getElementById calls bind to the correct jsdom elements.
 *
 * _Requirements: 11.2, 11.4_
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Minimal popup HTML structure mirroring popup.html */
function buildPopupHTML(): string {
  return `
    <div id="loading" style="display: flex;"></div>
    <div id="result" style="display: none;">
      <div id="label" class="label"></div>
      <div class="confidence-row">
        <div class="confidence-bar-track"
             role="progressbar"
             aria-valuemin="0"
             aria-valuemax="100"
             id="confidence-bar-container">
          <div id="confidence-bar" class="confidence-bar-fill"></div>
        </div>
        <span id="confidence-pct" class="confidence-pct"></span>
      </div>
      <div id="explanation" class="explanation"></div>
    </div>
    <div id="error" style="display: none;">
      <span id="error-message"></span>
    </div>
  `
}

/** Load and execute popup.js inside the current jsdom window context. */
function loadPopupScript(): {
  showLoading: () => void
  renderPrediction: (p: { label: string; confidence: number; explanation?: string }) => void
  renderError: (msg: string) => void
} {
  const scriptPath = resolve(__dirname, '../../../../extension/popup.js')
  const source = readFileSync(scriptPath, 'utf-8')

  // Wrap the script so we can extract the functions without running the
  // entry-point code (the chrome.storage.session calls at the bottom).
  // We replace the entry-point block with a no-op so the module-level
  // getElementById calls still run (they are at the top of the file).
  const safeSource = source
    // Suppress the entry-point: showLoading() call and chrome.storage block
    .replace(/\/\/ ── Entry point[\s\S]*$/, '')

  // Execute in the current window scope so getElementById resolves correctly.
  // eslint-disable-next-line no-new-func
  const factory = new Function(
    'document',
    'window',
    `
    ${safeSource}
    return { showLoading, renderPrediction, renderError };
    `,
  )

  return factory(document, window)
}

// ── Test suite ────────────────────────────────────────────────────────────────

describe('Extension popup rendering', () => {
  let showLoading: ReturnType<typeof loadPopupScript>['showLoading']
  let renderPrediction: ReturnType<typeof loadPopupScript>['renderPrediction']
  let renderError: ReturnType<typeof loadPopupScript>['renderError']

  beforeEach(() => {
    // Reset DOM to a clean popup structure before each test
    document.body.innerHTML = buildPopupHTML()

    // Mock chrome APIs so the script doesn't throw at parse time
    ;(globalThis as Record<string, unknown>).chrome = {
      storage: {
        session: {
          get: vi.fn(),
          remove: vi.fn((_key: string, cb: () => void) => cb()),
        },
      },
      runtime: {
        sendMessage: vi.fn(),
      },
    }

    // Load the script fresh for each test so DOM refs are re-bound
    const fns = loadPopupScript()
    showLoading = fns.showLoading
    renderPrediction = fns.renderPrediction
    renderError = fns.renderError
  })

  // ── 1. Renders "Real News ✅" label ─────────────────────────────────────────
  it('renders "Real News ✅" label for a Real prediction', () => {
    renderPrediction({ label: 'Real', confidence: 0.92, explanation: 'Looks credible.' })

    const labelEl = document.getElementById('label')!
    expect(labelEl.textContent).toBe('Real News ✅')
    expect(labelEl.classList.contains('real')).toBe(true)
  })

  // ── 2. Renders "Fake News ❌" label ─────────────────────────────────────────
  it('renders "Fake News ❌" label for a Fake prediction', () => {
    renderPrediction({ label: 'Fake', confidence: 0.78, explanation: 'Suspicious content.' })

    const labelEl = document.getElementById('label')!
    expect(labelEl.textContent).toBe('Fake News ❌')
    expect(labelEl.classList.contains('fake')).toBe(true)
  })

  // ── 3. Renders confidence percentage ────────────────────────────────────────
  it('renders confidence percentage rounded to one decimal place', () => {
    renderPrediction({ label: 'Real', confidence: 0.873, explanation: '' })

    const pctEl = document.getElementById('confidence-pct')!
    expect(pctEl.textContent).toBe('87.3%')
  })

  it('sets the confidence bar width to match the percentage', () => {
    renderPrediction({ label: 'Fake', confidence: 0.873, explanation: '' })

    const barEl = document.getElementById('confidence-bar') as HTMLElement
    // jsdom normalises trailing zeros in CSS values, so "87.3%" stays "87.3%"
    expect(barEl.style.width).toBe('87.3%')
  })

  // ── 4. Renders "Page content could not be analyzed" for NO_TEXT ─────────────
  it('renders "Page content could not be analyzed." when error is NO_TEXT', () => {
    renderError('NO_TEXT')

    const errorMsgEl = document.getElementById('error-message')!
    expect(errorMsgEl.textContent).toBe('Page content could not be analyzed.')
  })

  it('shows the error panel and hides result/loading for NO_TEXT', () => {
    renderError('NO_TEXT')

    const errorEl = document.getElementById('error') as HTMLElement
    const resultEl = document.getElementById('result') as HTMLElement
    const loadingEl = document.getElementById('loading') as HTMLElement

    expect(errorEl.style.display).toBe('flex')
    expect(resultEl.style.display).toBe('none')
    expect(loadingEl.style.display).toBe('none')
  })

  // ── 5. Shows loading state ───────────────────────────────────────────────────
  it('shows loading spinner and hides result and error panels', () => {
    // First render a result so we have a non-default state to revert from
    renderPrediction({ label: 'Real', confidence: 0.9, explanation: '' })

    // Now switch to loading
    showLoading()

    const loadingEl = document.getElementById('loading') as HTMLElement
    const resultEl = document.getElementById('result') as HTMLElement
    const errorEl = document.getElementById('error') as HTMLElement

    expect(loadingEl.style.display).toBe('flex')
    expect(resultEl.style.display).toBe('none')
    expect(errorEl.style.display).toBe('none')
  })

  it('shows loading state from the initial DOM state', () => {
    showLoading()

    const loadingEl = document.getElementById('loading') as HTMLElement
    expect(loadingEl.style.display).toBe('flex')
  })
})
