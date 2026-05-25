import { useState, useEffect } from 'react'
import { getAuthHeaders } from './AuthGuard'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

interface AnalyticsData {
  total_submissions: number
  real_percentage: number
  fake_percentage: number
  model_accuracy: number
}

// ── Spinner icon ──────────────────────────────────────────────────────────────
function Spinner({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg
      className={`${className} animate-spin`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  )
}

// ── Stat card ─────────────────────────────────────────────────────────────────
interface StatCardProps {
  label: string
  value: string
  icon: React.ReactNode
  colorClass: string
}

function StatCard({ label, value, icon, colorClass }: StatCardProps) {
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-5 flex items-center gap-4">
      <div
        className={`flex-shrink-0 w-12 h-12 rounded-lg flex items-center justify-center text-white ${colorClass}`}
        aria-hidden="true"
      >
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-sm text-gray-700 dark:text-gray-300 truncate">{label}</p>
        <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 tabular-nums">{value}</p>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export function AnalyticsWidgets() {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAnalytics = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/analytics`, {
        headers: { ...getAuthHeaders() },
      })
      if (!response.ok) {
        throw new Error(`Failed to load analytics (HTTP ${response.status}).`)
      }
      const json: AnalyticsData = await response.json()
      setData(json)
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'An unexpected error occurred while loading analytics.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAnalytics()
  }, [])

  return (
    <section
      aria-labelledby="analytics-heading"
      className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-6 flex flex-col gap-5"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2
            id="analytics-heading"
            className="text-lg font-semibold text-gray-900 dark:text-gray-100"
          >
            Analytics
          </h2>
          <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
            Live statistics from the detection pipeline.
          </p>
        </div>

        {/* Refresh button */}
        {!loading && (
          <button
            type="button"
            onClick={fetchAnalytics}
            className={[
              'min-h-[44px] rounded-lg px-4 py-2 text-sm font-semibold',
              'bg-gray-100 hover:bg-gray-200 active:bg-gray-300',
              'dark:bg-gray-700 dark:hover:bg-gray-600 dark:active:bg-gray-500',
              'text-gray-700 dark:text-gray-200',
              'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800',
              'transition-colors flex items-center gap-2',
            ].join(' ')}
            aria-label="Refresh analytics"
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

      {/* Loading state */}
      {loading && (
        <div
          className="flex items-center justify-center gap-3 py-10 text-gray-500 dark:text-gray-400"
          role="status"
          aria-label="Loading analytics"
        >
          <Spinner />
          <span className="text-sm">Loading analytics…</span>
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 p-4 flex flex-col gap-3"
        >
          <div className="flex items-start gap-3">
            <svg
              className="w-4 h-4 flex-shrink-0 text-red-600 dark:text-red-400 mt-0.5"
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
            <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
          </div>
          <button
            type="button"
            onClick={fetchAnalytics}
            className={[
              'self-start min-h-[44px] rounded-lg px-4 py-2 text-sm font-semibold',
              'bg-red-100 hover:bg-red-200 active:bg-red-300',
              'dark:bg-red-900/30 dark:hover:bg-red-900/50',
              'text-red-700 dark:text-red-300',
              'focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800',
              'transition-colors',
            ].join(' ')}
          >
            Try again
          </button>
        </div>
      )}

      {/* Stat cards */}
      {!loading && data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <StatCard
            label="Total Submissions"
            value={data.total_submissions.toLocaleString()}
            colorClass="bg-blue-500"
            icon={
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            }
          />
          <StatCard
            label="Real News"
            value={`${data.real_percentage.toFixed(1)}%`}
            colorClass="bg-green-500"
            icon={
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            }
          />
          <StatCard
            label="Fake News"
            value={`${data.fake_percentage.toFixed(1)}%`}
            colorClass="bg-red-500"
            icon={
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            }
          />
          <StatCard
            label="Model Accuracy"
            value={`${(data.model_accuracy * 100).toFixed(1)}%`}
            colorClass="bg-indigo-500"
            icon={
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            }
          />
        </div>
      )}
    </section>
  )
}
