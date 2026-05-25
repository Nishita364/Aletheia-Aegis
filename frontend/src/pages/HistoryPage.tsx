import { useEffect, useState, useCallback } from 'react'
import { HistoryList } from '../components/HistoryList'
import type { PredictionResponse } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type FetchState = 'idle' | 'loading' | 'success' | 'error' | 'unavailable'

export function HistoryPage() {
  const [items, setItems] = useState<PredictionResponse[]>([])
  const [fetchState, setFetchState] = useState<FetchState>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const fetchHistory = useCallback(async () => {
    setFetchState('loading')
    setErrorMessage(null)

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/history`)

      if (response.status === 503) {
        setFetchState('unavailable')
        return
      }

      if (!response.ok) {
        throw new Error(`Failed to load history (HTTP ${response.status}).`)
      }

      const data: PredictionResponse[] = await response.json()

      // Sort by timestamp descending (most recent first) — the API should
      // already return them in this order, but we enforce it client-side too.
      const sorted = [...data].sort(
        (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
      )

      setItems(sorted)
      setFetchState('success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'An unexpected error occurred.'
      setErrorMessage(msg)
      setFetchState('error')
    }
  }, [])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  const handleDelete = useCallback((id: string) => {
    setItems((prev) => prev.filter((item) => item.id !== id))
  }, [])

  // ── Loading state ─────────────────────────────────────────────────────────
  const isLoading = fetchState === 'idle' || fetchState === 'loading'

  return (
    <div className="flex flex-col gap-6 w-full max-w-5xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">History</h1>
        {fetchState === 'success' && (
          <button
            type="button"
            onClick={fetchHistory}
            className={[
              'min-h-[44px] inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium',
              'border border-gray-300 dark:border-gray-600',
              'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300',
              'hover:bg-gray-50 dark:hover:bg-gray-700',
              'focus:outline-none focus:ring-2 focus:ring-blue-500',
              'transition-colors',
            ].join(' ')}
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            Refresh
          </button>
        )}
      </div>

      {/* Loading spinner */}
      {isLoading && (
        <div
          className="flex flex-col items-center justify-center gap-4 py-16"
          role="status"
          aria-live="polite"
          aria-label="Loading history"
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
          <p className="text-gray-700 dark:text-gray-300 text-sm">Loading history…</p>
        </div>
      )}

      {/* 503 — history temporarily unavailable */}
      {fetchState === 'unavailable' && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-lg border border-yellow-300 dark:border-yellow-700 bg-yellow-50 dark:bg-yellow-900/20 p-5 flex flex-col gap-3"
        >
          <div className="flex items-start gap-3">
            <svg
              className="w-5 h-5 flex-shrink-0 text-yellow-600 dark:text-yellow-400 mt-0.5"
              fill="currentColor"
              viewBox="0 0 20 20"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            <p className="text-sm text-yellow-800 dark:text-yellow-300 font-medium">
              History is temporarily unavailable. Please try again later.
            </p>
          </div>
          <button
            type="button"
            onClick={fetchHistory}
            className={[
              'self-start min-h-[44px] inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium',
              'border border-yellow-400 dark:border-yellow-600',
              'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-300',
              'hover:bg-yellow-200 dark:hover:bg-yellow-900/60',
              'focus:outline-none focus:ring-2 focus:ring-yellow-500',
              'transition-colors',
            ].join(' ')}
          >
            Try again
          </button>
        </div>
      )}

      {/* Generic error */}
      {fetchState === 'error' && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 p-5 flex flex-col gap-3"
        >
          <div className="flex items-start gap-3">
            <svg
              className="w-5 h-5 flex-shrink-0 text-red-600 dark:text-red-400 mt-0.5"
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
            <p className="text-sm text-red-700 dark:text-red-400">
              {errorMessage ?? 'Failed to load history.'}
            </p>
          </div>
          <button
            type="button"
            onClick={fetchHistory}
            className={[
              'self-start min-h-[44px] inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium',
              'border border-red-300 dark:border-red-700',
              'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400',
              'hover:bg-red-200 dark:hover:bg-red-900/60',
              'focus:outline-none focus:ring-2 focus:ring-red-500',
              'transition-colors',
            ].join(' ')}
          >
            Try again
          </button>
        </div>
      )}

      {/* History list */}
      {fetchState === 'success' && (
        <HistoryList items={items} onDelete={handleDelete} />
      )}
    </div>
  )
}
