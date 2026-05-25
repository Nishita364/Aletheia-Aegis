/**
 * content.js — Content script injected into every page.
 *
 * Exposes extractText() so the background service worker can
 * retrieve the visible text of the current page.
 */

/**
 * Returns the visible text content of the page body.
 * Returns an empty string if the body is absent or contains only whitespace.
 * @returns {string}
 */
function extractText() {
  if (!document.body) return '';
  const text = document.body.innerText;
  // Return empty string for whitespace-only content so callers can
  // detect the "no extractable text" case with a simple falsy check.
  return text.trim().length > 0 ? text : '';
}

// Make available to executeScript calls from background.js
// (content scripts share the page's global scope when injected)
window.extractText = extractText;
