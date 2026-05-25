import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import type { PredictionResponse } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const PAGE_SIZE = 10

interface HistoryListProps {
  items: PredictionResponse[]
  onDelete: (id: string) => void
}

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ts
  }
}

function truncate(text: string, maxLen = 80): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen).trimEnd() + '…'
}

export function HistoryList({ items, onDelete }: HistoryListProps) {
  const navigate = useNavigate()
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [page, setPage] = useState(1)

  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE))
  const pageItems = items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleRowClick = useCallback(
    (id: string) => {
      navigate(`/result/${id}`)
    },
    [navigate],
  )

  const handleDelete = useCallback(
    async (e: React.MouseEvent, id: string) => {
      // Prevent the row click from firing
      e.stopPropagation()
      setDeleteError(null)
      setDeletingId(id)

      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/history/${id}`, {
          method: 'DELETE',
        })

        if (!response.ok) {
          throw new Error(`Failed to delete entry (HTTP ${response.status}).`)
        }

        onDelete(id)
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Failed to delete entry.'
        setDeleteError(msg)
      } finally {
        setDeletingId(null)
      }
    },
    [onDelete],
  )

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-8 text-center text-gray-400 dark:text-gray-500">
        No history yet. Submit an article to get started.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Delete error banner */}
      {deleteError && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 p-3 flex items-center justify-between gap-3"
        >
          <p className="text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
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
            {deleteError}
          </p>
          <button
            type="button"
            onClick={() => setDeleteError(null)}
            className="text-xs text-red-700 dark:text-red-400 underline hover:no-underline focus:outline-none focus:ring-2 focus:ring-red-500 rounded min-h-[44px] px-1"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* History table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 -mx-0">
        <table className="w-full min-w-[480px] text-sm" aria-label="Submission history">
          <thead>
            <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
              <th
                scope="col"
                className="px-4 py-3 text-left font-semibold text-gray-700 dark:text-gray-300"
              >
                Date
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left font-semibold text-gray-700 dark:text-gray-300"
              >
                Content
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left font-semibold text-gray-700 dark:text-gray-300"
              >
                Verdict
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left font-semibold text-gray-700 dark:text-gray-300"
              >
                Confidence
              </th>
              <th scope="col" className="px-4 py-3 text-right">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {pageItems.map((item) => {
              const isReal = item.label === 'Real'
              const confidencePct = (item.confidence * 100).toFixed(1)
              const preview = item.input_url
                ? item.input_url
                : item.input_text
                  ? truncate(item.input_text)
                  : '—'
              const isDeleting = deletingId === item.id

              return (
                <tr
                  key={item.id}
                  onClick={() => handleRowClick(item.id)}
                  className={[
                    'bg-white dark:bg-gray-900 cursor-pointer',
                    'hover:bg-blue-50 dark:hover:bg-blue-900/20',
                    'focus-within:bg-blue-50 dark:focus-within:bg-blue-900/20',
                    'transition-colors',
                    isDeleting ? 'opacity-50 pointer-events-none' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  aria-label={`View result for submission from ${formatTimestamp(item.timestamp)}`}
                >
                  {/* Date */}
                  <td className="px-4 py-3 whitespace-nowrap text-gray-700 dark:text-gray-300">
                    {formatTimestamp(item.timestamp)}
                  </td>

                  {/* Content preview */}
                  <td className="px-4 py-3 text-gray-800 dark:text-gray-200 max-w-xs min-w-0">
                    <span className="block truncate" title={item.input_url ?? item.input_text ?? ''}>
                      {preview}
                    </span>
                  </td>

                  {/* Verdict badge */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span
                      className={[
                        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold border',
                        isReal
                          ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 border-green-300 dark:border-green-700'
                          : 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 border-red-300 dark:border-red-700',
                      ].join(' ')}
                    >
                      {isReal ? 'Real ✅' : 'Fake ❌'}
                    </span>
                  </td>

                  {/* Confidence */}
                  <td className="px-4 py-3 whitespace-nowrap text-gray-700 dark:text-gray-300">
                    {confidencePct}%
                  </td>

                  {/* Delete button */}
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={(e) => handleDelete(e, item.id)}
                      disabled={isDeleting}
                      aria-label={`Delete submission from ${formatTimestamp(item.timestamp)}`}
                      className={[
                        'min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-md',
                        'text-gray-400 hover:text-red-600 dark:hover:text-red-400',
                        'hover:bg-red-50 dark:hover:bg-red-900/20',
                        'focus:outline-none focus:ring-2 focus:ring-red-500 rounded',
                        'transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
                      ].join(' ')}
                    >
                      {isDeleting ? (
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
                      ) : (
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
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      )}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <p className="text-sm text-gray-700 dark:text-gray-300">
            Page {page} of {totalPages} &middot; {items.length} entries
          </p>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              aria-label="Previous page"
              className={[
                'min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-md text-sm font-medium',
                'border border-gray-300 dark:border-gray-600',
                'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300',
                'hover:bg-gray-50 dark:hover:bg-gray-700',
                'focus:outline-none focus:ring-2 focus:ring-blue-500',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors',
              ].join(' ')}
            >
              ‹
            </button>

            {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPage(p)}
                aria-label={`Page ${p}`}
                aria-current={p === page ? 'page' : undefined}
                className={[
                  'min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-md text-sm font-medium',
                  'focus:outline-none focus:ring-2 focus:ring-blue-500',
                  'transition-colors',
                  p === page
                    ? 'bg-blue-600 text-white border border-blue-600'
                    : 'border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700',
                ].join(' ')}
              >
                {p}
              </button>
            ))}

            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              aria-label="Next page"
              className={[
                'min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-md text-sm font-medium',
                'border border-gray-300 dark:border-gray-600',
                'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300',
                'hover:bg-gray-50 dark:hover:bg-gray-700',
                'focus:outline-none focus:ring-2 focus:ring-blue-500',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors',
              ].join(' ')}
            >
              ›
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
