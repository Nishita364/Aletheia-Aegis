import React from 'react'

interface HighlightedTextProps {
  text: string
  phrases: string[]
}

interface Range {
  start: number
  end: number
}

/**
 * Merge overlapping or adjacent ranges into a minimal set of non-overlapping ranges.
 * Ranges are [start, end) half-open intervals.
 */
function mergeRanges(ranges: Range[]): Range[] {
  if (ranges.length === 0) return []

  const sorted = [...ranges].sort((a, b) => a.start - b.start || a.end - b.end)
  const merged: Range[] = [{ ...sorted[0] }]

  for (let i = 1; i < sorted.length; i++) {
    const current = sorted[i]
    const last = merged[merged.length - 1]

    if (current.start <= last.end) {
      // Overlapping or adjacent — extend the last range if needed
      last.end = Math.max(last.end, current.end)
    } else {
      merged.push({ ...current })
    }
  }

  return merged
}

/**
 * Find all (case-sensitive) occurrences of `phrase` in `text` and return their ranges.
 */
function findRanges(text: string, phrase: string): Range[] {
  if (!phrase) return []
  const ranges: Range[] = []
  let searchFrom = 0

  while (searchFrom < text.length) {
    const idx = text.indexOf(phrase, searchFrom)
    if (idx === -1) break
    ranges.push({ start: idx, end: idx + phrase.length })
    searchFrom = idx + 1 // allow overlapping phrase matches to be found
  }

  return ranges
}

/**
 * HighlightedText renders `text` with each occurrence of any phrase in `phrases`
 * wrapped in a <mark> element. Overlapping phrase ranges are merged before rendering
 * so no character is double-wrapped.
 */
export function HighlightedText({ text, phrases }: HighlightedTextProps) {
  // Collect all ranges from all phrases
  const allRanges: Range[] = []
  for (const phrase of phrases) {
    if (phrase.length > 0) {
      allRanges.push(...findRanges(text, phrase))
    }
  }

  const merged = mergeRanges(allRanges)

  if (merged.length === 0) {
    // No matches — render plain text
    return (
      <span className="whitespace-pre-wrap break-words text-sm text-gray-800 dark:text-gray-200">
        {text}
      </span>
    )
  }

  // Build an array of React nodes by slicing the text around highlighted ranges
  const nodes: React.ReactNode[] = []
  let cursor = 0

  for (const range of merged) {
    // Plain text before this highlight
    if (cursor < range.start) {
      nodes.push(
        <React.Fragment key={`plain-${cursor}`}>
          {text.slice(cursor, range.start)}
        </React.Fragment>,
      )
    }

    // Highlighted segment
    nodes.push(
      <mark
        key={`mark-${range.start}`}
        className="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5"
      >
        {text.slice(range.start, range.end)}
      </mark>,
    )

    cursor = range.end
  }

  // Any remaining plain text after the last highlight
  if (cursor < text.length) {
    nodes.push(
      <React.Fragment key={`plain-${cursor}`}>{text.slice(cursor)}</React.Fragment>,
    )
  }

  return (
    <span className="whitespace-pre-wrap break-words text-sm text-gray-800 dark:text-gray-200">
      {nodes}
    </span>
  )
}
