/**
 * popup.js — Renders the prediction result received from the background worker.
 *
 * On open, sends an ANALYZE_TAB message to background.js to kick off
 * text extraction and API submission. Then polls chrome.storage.session
 * for up to 8 seconds (Requirement 11.2) until a result or error arrives.
 *
 * Storage states written by background.js:
 *   { loading: true }           — analysis in progress
 *   { prediction: {...} }       — success; prediction has label, confidence, explanation
 *   { error: 'NO_TEXT' }        — no extractable text (Requirement 11.4)
 *   { error: '<message>' }      — other error
 */

'use strict';

// ── DOM references ────────────────────────────────────────────────────────────
const loadingEl      = document.getElementById('loading');
const resultEl       = document.getElementById('result');
const labelEl        = document.getElementById('label');
const confidenceBarEl = document.getElementById('confidence-bar');
const confidenceBarContainerEl = document.getElementById('confidence-bar-container');
const confidencePctEl = document.getElementById('confidence-pct');
const explanationEl  = document.getElementById('explanation');
const errorEl        = document.getElementById('error');
const errorMessageEl = document.getElementById('error-message');

// ── Polling configuration ─────────────────────────────────────────────────────
const POLL_INTERVAL_MS = 500;
const MAX_WAIT_MS      = 8000;   // Requirement 11.2: result within 8 seconds
let elapsed = 0;
// Use session storage when available, otherwise fall back to local storage.
const storage = chrome.storage.session ?? chrome.storage.local;
// ── Render helpers ────────────────────────────────────────────────────────────

/**
 * Show the loading spinner and hide result / error panels.
 */
function showLoading() {
  loadingEl.style.display = 'flex';
  resultEl.style.display  = 'none';
  errorEl.style.display   = 'none';
}

/**
 * Render a successful prediction.
 * @param {{ label: string, confidence: number, explanation?: string }} prediction
 */
function renderPrediction(prediction) {
  loadingEl.style.display = 'none';
  errorEl.style.display   = 'none';
  resultEl.style.display  = 'block';

  const isReal = prediction.label === 'Real';
  const typeClass = isReal ? 'real' : 'fake';

  // Label — "Real News ✅" or "Fake News ❌" (Requirement 11.2 / 3.1)
  labelEl.textContent = isReal ? 'Real News ✅' : 'Fake News ❌';
  labelEl.className   = `label ${typeClass}`;

  // Confidence percentage to 1 decimal place (Requirement 3.2)
  const pct = (prediction.confidence * 100).toFixed(1);
  confidencePctEl.textContent = `${pct}%`;
  confidenceBarEl.style.width = `${pct}%`;
  confidenceBarEl.className   = `confidence-bar-fill ${typeClass}`;
  confidenceBarContainerEl.setAttribute('aria-valuenow', pct);

  // Explanation (Requirement 11.2)
  explanationEl.textContent = prediction.explanation ?? '';
}

/**
 * Render an error message.
 * @param {string} message  Raw error code or message from storage.
 */
function renderError(message) {
  loadingEl.style.display = 'none';
  resultEl.style.display  = 'none';
  errorEl.style.display   = 'flex';

  if (message === 'NO_TEXT') {
    // Requirement 11.4: page has no extractable text
    errorMessageEl.textContent = 'Page content could not be analyzed.';
  } else if (message === 'TIMEOUT') {
    errorMessageEl.textContent =
      'Analysis timed out after 8 seconds. Please try again.';
  } else {
    errorMessageEl.textContent = `Could not complete analysis: ${message}`;
  }
}

// ── Polling loop ──────────────────────────────────────────────────────────────

/**
 * Poll chrome.storage.session every POLL_INTERVAL_MS until a result or error
 * is available, or until MAX_WAIT_MS has elapsed.
 */
function poll() {
  storage.get('predictionState', ({ predictionState }) => {
    // Still loading (or state not yet written by background worker)
    if (!predictionState || predictionState.loading) {
      elapsed += POLL_INTERVAL_MS;
      if (elapsed >= MAX_WAIT_MS) {
        // Requirement 11.2: must display result within 8 seconds
        renderError('TIMEOUT');
        return;
      }
      setTimeout(poll, POLL_INTERVAL_MS);
      return;
    }

    // Error state
    if (predictionState.error) {
      renderError(predictionState.error);
      return;
    }

    // Success state
    if (predictionState.prediction) {
      renderPrediction(predictionState.prediction);
      return;
    }

    // Unexpected state — treat as an error
    renderError('Unexpected response from background worker.');
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────

// Show loading immediately so the user sees feedback right away.
showLoading();

// Clear any stale state from a previous analysis, then ask the background
// worker to analyze the current tab. Polling starts immediately after.
storage.remove('predictionState', () => {
  chrome.runtime.sendMessage({ action: 'ANALYZE_TAB' }, () => {
    if (chrome.runtime.lastError) {
      renderError(chrome.runtime.lastError.message);
      return;
    }
    poll();
  });
});
