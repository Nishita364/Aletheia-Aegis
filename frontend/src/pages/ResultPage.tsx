import { useEffect, useState } from 'react'
import { useParams, Link, useLocation } from 'react-router-dom'
import { PredictionCard } from '../components/PredictionCard'
import { HighlightedText } from '../components/HighlightedText'
import type { PredictionResponse } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

interface LocationState {
  result?: PredictionResponse
}

export function ResultPage() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const locationState = location.state as LocationState | null

  const [result, setResult] = useState<PredictionResponse | null>(
    locationState?.result ?? null
  )
  const [loading, setLoading] = useState(!locationState?.result)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // If result was passed via navigation state, no need to fetch
    if (locationState?.result) {
      return
    }

    if (!id) {
      setError('No result ID provided.')
      setLoading(false)
      return
    }

    let cancelled = false

    async function fetchResult() {
      setLoading(true)
      setError(null)

      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/history/${id}`)

        if (!response.ok) {
          if (response.status === 404) {
            throw new Error('Result not found. It may have been deleted.')
          }
          throw new Error(`Failed to load result (HTTP ${response.status}).`)
        }

        const data: PredictionResponse = await response.json()
        if (!cancelled) {
          setResult(data)
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : 'An unexpected error occurred.'
          setError(msg)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    fetchResult()

    return () => {
      cancelled = true
    }
  }, [id])

  // ── Loading state ─────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-4 py-20"
        role="status"
        aria-live="polite"
        aria-label="Loading prediction result"
      >
        <svg
          className="w-10 h-10 animate-spin text-blue-600 dark:text-blue-400"
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
        <p className="text-gray-700 dark:text-gray-300 text-sm">Loading result…</p>
      </div>
    )
  }

  // ── Error state ───────────────────────────────────────────────────────────
  if (error) {
    return (
      <div
        className="flex flex-col gap-4 items-start"
        role="alert"
        aria-live="assertive"
      >
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Prediction Result
        </h1>
        <div className="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 p-4 flex flex-col gap-3 w-full max-w-2xl">
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
            <span>{error}</span>
          </p>
          <Link
            to="/"
            className="self-start text-sm font-medium text-red-700 dark:text-red-400 underline hover:no-underline focus:outline-none focus:ring-2 focus:ring-red-500 rounded min-h-[44px] flex items-center px-1"
          >
            ← Back to Home
          </Link>
        </div>
      </div>
    )
  }

  // ── Result state ──────────────────────────────────────────────────────────
  if (!result) return null

  const inputText = result.input_text ?? ''
  const factCheckError =
    !Array.isArray(result.fact_checks) || result.fact_checks === undefined
  const isLowConfidence = result.confidence < 0.70

  return (
    <div className="flex flex-col gap-6 w-full max-w-3xl">
      <div className="flex items-center justify-between flex-wrap gap-2 w-full">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Prediction Result
        </h1>
        <Link
          to="/"
          className="text-sm text-blue-600 dark:text-blue-400 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 rounded min-h-[44px] flex items-center px-1"
        >
          ← New check
        </Link>
      </div>

      {/* Low-confidence warning */}
      {isLowConfidence && (
        <div
          role="alert"
          className="rounded-lg border border-yellow-300 dark:border-yellow-600 bg-yellow-50 dark:bg-yellow-900/20 p-4 flex items-start gap-3"
        >
          <svg className="w-5 h-5 flex-shrink-0 text-yellow-600 dark:text-yellow-400 mt-0.5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          <div>
            <p className="text-sm font-semibold text-yellow-800 dark:text-yellow-300">Low confidence result</p>
            <p className="text-sm text-yellow-700 dark:text-yellow-400 mt-0.5">
              The model is only {Math.round(result.confidence * 100)}% confident. This article's writing style may differ from the training data. Treat this result with caution.
            </p>
          </div>
        </div>
      )}

      {/* Prediction card */}
      <PredictionCard
        label={result.label}
        confidence={result.confidence}
        explanation={result.explanation}
        suspiciousPhrases={result.suspicious_phrases}
        trustRating={result.trust_rating}
        factChecks={result.fact_checks}
        factCheckError={factCheckError}
      />

      {/* Highlighted article text */}
      {inputText.length > 0 && (
        <section aria-labelledby="article-text-heading">
          <h2
            id="article-text-heading"
            className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2"
          >
            Article Text
            {result.suspicious_phrases.length > 0 && (
              <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
                (suspicious phrases highlighted)
              </span>
            )}
          </h2>
          <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-4 leading-relaxed">
            <HighlightedText
              text={inputText}
              phrases={result.suspicious_phrases}
            />
          </div>
        </section>
      )}

      {/* Metadata footer */}
      <p className="text-xs text-gray-600 dark:text-gray-400">
        Result ID:{' '}
        <span className="font-mono">{result.id}</span>
        {result.timestamp && (
          <>
            {' · '}
            {new Date(result.timestamp).toLocaleString()}
          </>
        )}
      </p>
    </div>
  )
}
