/**
 * background.js — Manifest V3 service worker
 *
 * Handles analysis requests: injects the content script into the active tab,
 * extracts page text via extractText(), and POSTs it to the API server.
 *
 * Because the extension uses a popup (default_popup in manifest.json),
 * chrome.action.onClicked does NOT fire — the popup sends an "ANALYZE_TAB"
 * message instead. The onClicked listener is kept as a fallback for builds
 * that remove the popup.
 */

const DEFAULT_API_HOST = 'http://localhost:8000';
const storage = chrome.storage.session ?? chrome.storage.local;

/**
 * Retrieve the configured API host from extension storage, falling back to
 * the compile-time default.
 * @returns {Promise<string>}
 */
async function getApiHost() {
  return new Promise((resolve) => {
    chrome.storage.sync.get({ apiHost: DEFAULT_API_HOST }, ({ apiHost }) => {
      resolve(apiHost);
    });
  });
}

/**
 * Core analysis routine:
 * 1. Injects content.js (or uses the already-injected copy) into the tab.
 * 2. Calls extractText() in the tab's context.
 * 3. POSTs the text to the API server over HTTPS.
 * 4. Stores the result (or error) in chrome.storage.session for the popup.
 *
 * @param {number} tabId
 */
async function setPredictionState(state) {
  return new Promise((resolve) => storage.set({ predictionState: state }, resolve));
}

async function analyzeTab(tabId) {
  // Reset state so the popup shows a fresh loading indicator.
  await setPredictionState({ loading: true });

  try {
    // Inject content script and call extractText() in the page context.
    // If content.js was already injected (declarative content_scripts), the
    // function will already be present on window; the inline fallback handles
    // the rare case where it isn't.
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        if (typeof window.extractText === 'function') {
          return window.extractText();
        }
        // Inline fallback — mirrors content.js logic exactly.
        if (!document.body) return '';
        const text = document.body.innerText;
        return text.trim().length > 0 ? text : '';
      },
    });

    const text = results?.[0]?.result ?? '';

    if (!text) {
      // Requirement 11.4: no extractable text — notify popup.
      await setPredictionState({ error: 'NO_TEXT' });
      return;
    }

    // Requirement 11.5: prefer HTTPS in production, but allow localhost over
    // HTTP during local development for `http://localhost:8000`.
    const apiHost = await getApiHost();
    const allowLocalHttp = apiHost.startsWith('http://localhost') || apiHost.startsWith('http://127.0.0.1')
    if (!apiHost.startsWith('https://') && !allowLocalHttp) {
      throw new Error('API_HOST must use HTTPS in production (Requirement 11.5)');
    }

    // Requirement 11.6: transmit only the active tab's text; truncate to the
    // API's 10,000-character limit.
    const response = await fetch(`${apiHost}/api/v1/submissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.slice(0, 10000) }),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const prediction = await response.json();
    await setPredictionState({ prediction });
  } catch (err) {
    await setPredictionState({
      error: err instanceof Error ? err.message : 'UNKNOWN_ERROR',
    });
  }
}

// ---------------------------------------------------------------------------
// Message listener — primary trigger when a popup is configured.
// The popup sends { action: "ANALYZE_TAB" } on open to kick off analysis.
// ---------------------------------------------------------------------------
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.action === 'ANALYZE_TAB') {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tabId = tabs?.[0]?.id;
      if (tabId != null) {
        analyzeTab(tabId);
      } else {
        chrome.storage.session.set({ predictionState: { error: 'NO_TAB' } });
      }
    });
    // Respond immediately; result is communicated via storage.
    sendResponse({ started: true });
  }
  // Return false — we do not keep the message channel open.
  return false;
});

// ---------------------------------------------------------------------------
// Toolbar button click listener — fires only when NO default_popup is set.
// Kept here so the background works correctly in popup-less builds.
// ---------------------------------------------------------------------------
chrome.action.onClicked.addListener((tab) => {
  if (tab.id != null) {
    analyzeTab(tab.id);
  }
});
