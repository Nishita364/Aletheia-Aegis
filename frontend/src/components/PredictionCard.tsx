import type React from 'react'
import type { FactCheckResult } from '../types'

interface PredictionCardProps {
  label: 'Real' | 'Fake'
  confidence: number
  explanation: string
  suspiciousPhrases: string[]
  trustRating?: string | null
  factChecks?: FactCheckResult[]
  factCheckError?: boolean
}

/** Map trust rating values to Tailwind colour classes */
const trustRatingStyles: Record<string, string> = {
  High: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 border-green-300 dark:border-green-700',
  Medium:
    'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700',
  Low: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 border-red-300 dark:border-red-700',
  Unknown:
    'bg-gray-100 text-gray-700 dark:bg-gray-700/60 dark:text-gray-300 border-gray-300 dark:border-gray-600',
}

export function PredictionCard({
  label,
  confidence,
  explanation,
  trustRating,
  factChecks,
  factCheckError,
}: PredictionCardProps) {
  const isReal = label === 'Real'
  const confidencePct = (confidence * 100).toFixed(1)

  // ── Label badge ──────────────────────────────────────────────────────────────
  const labelBadgeClass = isReal
    ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 border border-green-300 dark:border-green-700'
    : 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 border border-red-300 dark:border-red-700'

  const labelText = isReal ? 'Real News ✅' : 'Fake News ❌'

  // ── Confidence bar colour ─────────────────────────────────────────────────────
  const barColour =
    confidence >= 0.75
      ? 'bg-green-500 dark:bg-green-400'
      : confidence >= 0.5
        ? 'bg-yellow-500 dark:bg-yellow-400'
        : 'bg-red-500 dark:bg-red-400'

  // ── Trust rating badge ────────────────────────────────────────────────────────
  const trustBadgeClass =
    trustRating && trustRatingStyles[trustRating]
      ? trustRatingStyles[trustRating]
      : trustRatingStyles['Unknown']

  // ── Fact-check section ────────────────────────────────────────────────────────
  let factCheckContent: React.ReactNode

  if (factCheckError) {
    factCheckContent = (
      <p className="text-sm text-gray-500 dark:text-gray-400 italic">
        Fact-check service is currently unavailable.
      </p>
    )
  } else if (!factChecks || factChecks.length === 0) {
    factCheckContent = (
      <p className="text-sm text-gray-500 dark:text-gray-400 italic">
        No independent fact-checks found for this content.
      </p>
    )
  } else {
    factCheckContent = (
      <ul className="flex flex-col gap-3" aria-label="Fact-check results">
        {factChecks.map((fc, idx) => (
          <li
            key={idx}
            className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-3 flex flex-col gap-1"
          >
            <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
              &ldquo;{fc.claim}&rdquo;
            </p>
            <div className="flex flex-wrap items-center gap-2 text-xs text-gray-700 dark:text-gray-300">
              <span className="font-semibold text-gray-700 dark:text-gray-300">
                Rating:
              </span>
              <span>{fc.rating}</span>
              <span aria-hidden="true">·</span>
              <span className="font-semibold text-gray-700 dark:text-gray-300">
                Source:
              </span>
              <span>{fc.source}</span>
            </div>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <article
      className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm flex flex-col gap-6 p-6"
      aria-label="Prediction result"
    >
      {/* ── Verdict badge ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`inline-flex items-center rounded-full px-4 py-1.5 text-base font-bold border ${labelBadgeClass}`}
          role="status"
          aria-label={`Verdict: ${labelText}`}
        >
          {labelText}
        </span>

        {/* Trust rating badge — only shown when a rating is provided */}
        {trustRating && (
          <span
            className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold border ${trustBadgeClass}`}
            aria-label={`Source trust rating: ${trustRating}`}
          >
            Trust: {trustRating}
          </span>
        )}
      </div>

      {/* ── Confidence bar ────────────────────────────────────────────────── */}
      <section aria-labelledby="confidence-heading">
        <h2
          id="confidence-heading"
          className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2"
        >
          Confidence
        </h2>
        <div
          className="w-full h-3 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden"
          role="progressbar"
          aria-valuenow={parseFloat(confidencePct)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Confidence: ${confidencePct}%`}
        >
          <div
            className={`h-full rounded-full transition-all duration-500 ${barColour}`}
            style={{ width: `${confidencePct}%` }}
          />
        </div>
        <p className="mt-1 text-sm font-medium text-gray-700 dark:text-gray-300">
          {confidencePct}%
        </p>
      </section>

      {/* ── Explanation ───────────────────────────────────────────────────── */}
      <section aria-labelledby="explanation-heading">
        <h2
          id="explanation-heading"
          className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1"
        >
          Explanation
        </h2>
        <p className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed">
          {explanation}
        </p>
      </section>

      {/* ── Fact-checks ───────────────────────────────────────────────────── */}
      <section aria-labelledby="factcheck-heading">
        <h2
          id="factcheck-heading"
          className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2"
        >
          Fact-Checks
        </h2>
        {factCheckContent}
      </section>
    </article>
  )
}
