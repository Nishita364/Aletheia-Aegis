import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const MAX_TEXT_LENGTH = 10_000

export function SubmissionForm() {
  const navigate = useNavigate()

  const [articleText, setArticleText] = useState('')
  const [articleUrl, setArticleUrl] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const bothFilled = articleText.trim().length > 0 && articleUrl.trim().length > 0
  const textDisabled = articleUrl.trim().length > 0
  const urlDisabled = articleText.trim().length > 0

  const validate = useCallback((): string | null => {
    const hasText = articleText.trim().length > 0
    const hasUrl = articleUrl.trim().length > 0

    if (hasText && hasUrl) {
      return 'Please provide either article text or a URL — not both.'
    }
    if (!hasText && !hasUrl) {
      return 'Please paste article text or enter a URL before submitting.'
    }
    if (hasText && articleText.length > MAX_TEXT_LENGTH) {
      return `Article text must be ${MAX_TEXT_LENGTH.toLocaleString()} characters or fewer.`
    }
    if (hasText) {
      const wordCount = articleText.trim().split(/\s+/).length
      if (wordCount < 10) {
        return `Text is too short (${wordCount} words). Please provide at least a few sentences for accurate analysis.`
      }
    }
    return null
  }, [articleText, articleUrl])

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      setApiError(null)

      const error = validate()
      if (error) {
        setValidationError(error)
        return
      }
      setValidationError(null)

      const body =
        articleText.trim().length > 0
          ? { text: articleText.trim(), url: null }
          : { text: null, url: articleUrl.trim() }

      setLoading(true)
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/submissions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })

        if (!response.ok) {
          let message = `Server error: ${response.status}`
          try {
            const data = await response.json()
            const detail = data?.detail
            if (typeof detail === 'object' && detail?.error) {
              // Map backend error codes to user-friendly messages
              switch (detail.error) {
                case 'URL_FETCH_ERROR':
                  if (detail.message?.includes('403') || detail.message?.includes('401')) {
                    message = 'This website blocks automated access. Try copying and pasting the article text directly instead.'
                  } else if (detail.message?.includes('404')) {
                    message = 'Article not found at that URL. Please check the link and try again.'
                  } else if (detail.message?.includes('enough article text')) {
                    message = 'Could not extract article text from this URL. The page may be behind a paywall or require JavaScript. Try copying and pasting the article text directly.'
                  } else {
                    message = `Could not fetch the article: ${detail.message}`
                  }
                  break
                case 'URL_FETCH_TIMEOUT':
                  message = 'The article URL took too long to respond. Try again or paste the text directly.'
                  break
                case 'UNSUPPORTED_LANGUAGE':
                  message = 'The article language is not supported. Only English, Telugu, and Hindi are supported.'
                  break
                default:
                  message = detail.message || String(detail)
              }
            } else if (typeof detail === 'string') {
              message = detail
            } else if (data?.message) {
              message = String(data.message)
            }
          } catch {
            // ignore JSON parse errors
          }
          throw new Error(message)
        }

        const result = await response.json()
        // Pass the full result via navigation state so ResultPage
        // doesn't need to re-fetch from history (avoids MongoDB dependency)
        navigate(`/result/${result.id}`, { state: { result } })
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'An unexpected error occurred.'
        setApiError(msg)
      } finally {
        setLoading(false)
      }
    },
    [articleText, articleUrl, validate, navigate],
  )

  const handleRetry = useCallback(() => {
    setApiError(null)
  }, [])

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="w-full max-w-2xl flex flex-col gap-5"
      aria-label="News article submission form"
    >
      {/* Article text area */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="article-text"
          className="text-sm font-medium text-gray-700 dark:text-gray-300"
        >
          Paste article text
        </label>
        <textarea
          id="article-text"
          name="article-text"
          rows={8}
          maxLength={MAX_TEXT_LENGTH}
          disabled={textDisabled || loading}
          value={articleText}
          onChange={(e) => {
            setArticleText(e.target.value)
            setValidationError(null)
          }}
          placeholder="Paste the full article text here…"
          aria-describedby={validationError ? 'form-error' : undefined}
          className={[
            'w-full rounded-lg border px-3 py-2 text-sm resize-y',
            'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100',
            'placeholder-gray-400 dark:placeholder-gray-500',
            'focus:outline-none focus:ring-2 focus:ring-blue-500',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            bothFilled || (validationError && !articleText.trim() && !articleUrl.trim())
              ? 'border-red-400 dark:border-red-500'
              : 'border-gray-300 dark:border-gray-600',
          ].join(' ')}
        />
        <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400">
          <span>
            {textDisabled ? (
              'Disabled while URL is filled'
            ) : articleText.trim().length > 0 ? (
              (() => {
                const words = articleText.trim().split(/\s+/).length
                return words < 10 ? (
                  <span className="text-amber-600 dark:text-amber-400">
                    ⚠ {words} words — add more text for accurate analysis
                  </span>
                ) : (
                  <span className="text-green-600 dark:text-green-400">✓ {words} words</span>
                )
              })()
            ) : (
              'Supports English, Telugu, and Hindi'
            )}
          </span>
          <span>
            {articleText.length.toLocaleString()} / {MAX_TEXT_LENGTH.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Divider */}
      <div className="flex items-center gap-3">
        <hr className="flex-1 border-gray-200 dark:border-gray-700" />
        <span className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wide">
          or
        </span>
        <hr className="flex-1 border-gray-200 dark:border-gray-700" />
      </div>

      {/* URL input */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="article-url"
          className="text-sm font-medium text-gray-700 dark:text-gray-300"
        >
          Enter article URL
        </label>
        <input
          id="article-url"
          name="article-url"
          type="url"
          disabled={urlDisabled || loading}
          value={articleUrl}
          onChange={(e) => {
            setArticleUrl(e.target.value)
            setValidationError(null)
          }}
          placeholder="https://example.com/article"
          aria-describedby={validationError ? 'form-error' : undefined}
          className={[
            'w-full min-h-[44px] rounded-lg border px-3 py-2 text-sm',
            'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100',
            'placeholder-gray-400 dark:placeholder-gray-500',
            'focus:outline-none focus:ring-2 focus:ring-blue-500',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            bothFilled || (validationError && !articleText.trim() && !articleUrl.trim())
              ? 'border-red-400 dark:border-red-500'
              : 'border-gray-300 dark:border-gray-600',
          ].join(' ')}
        />
        {urlDisabled && (
          <p className="text-xs text-gray-600 dark:text-gray-400">
            Disabled while article text is filled
          </p>
        )}
        {!urlDisabled && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Works with publicly accessible articles. Paywalled or Cloudflare-protected sites may not work — paste the text directly instead.
          </p>
        )}
      </div>

      {/* Inline validation error */}
      {validationError && (
        <p
          id="form-error"
          role="alert"
          className="text-sm text-red-600 dark:text-red-400 flex items-center gap-1"
        >
          <svg
            className="w-4 h-4 flex-shrink-0"
            fill="currentColor"
            viewBox="0 0 20 20"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
          {validationError}
        </p>
      )}

      {/* API error with retry */}
      {apiError && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 p-4 flex flex-col gap-2"
        >
          <p className="text-sm text-red-700 dark:text-red-400 flex items-start gap-2">
            <svg
              className="w-4 h-4 flex-shrink-0 mt-0.5"
              fill="currentColor"
              viewBox="0 0 20 20"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            <span>{apiError}</span>
          </p>
          <button
            type="button"
            onClick={handleRetry}
            className="self-start text-sm font-medium text-red-700 dark:text-red-400 underline hover:no-underline focus:outline-none focus:ring-2 focus:ring-red-500 rounded min-h-[44px] px-1"
          >
            Try again
          </button>
        </div>
      )}

      {/* Submit button */}
      <button
        type="submit"
        disabled={loading}
        className={[
          'w-full min-h-[44px] rounded-lg px-4 py-2 text-sm font-semibold',
          'bg-blue-600 hover:bg-blue-700 active:bg-blue-800',
          'text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
          'dark:focus:ring-offset-gray-900',
          'disabled:opacity-60 disabled:cursor-not-allowed',
          'transition-colors flex items-center justify-center gap-2',
        ].join(' ')}
      >
        {loading ? (
          <>
            {/* Loading spinner */}
            <svg
              className="w-4 h-4 animate-spin"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            Analyzing…
          </>
        ) : (
          'Check Article'
        )}
      </button>
    </form>
  )
}
