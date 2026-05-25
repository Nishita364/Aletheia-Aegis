/**
 * Unit tests for HighlightedText component
 *
 * Covers:
 *  1. Single phrase highlighted — renders a <mark> element containing the phrase
 *  2. Multiple non-overlapping phrases — each phrase gets its own <mark> element
 *  3. Overlapping phrases — merged into a single <mark> element (no double-wrapping)
 *  4. Phrase not present in text — no <mark> elements rendered, plain text shown
 *  5. Empty phrases array — no <mark> elements rendered, plain text shown
 *
 * _Requirements: 3.3_
 */

import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { HighlightedText } from '../HighlightedText'

describe('HighlightedText', () => {
  // ---------------------------------------------------------------------------
  // 1. Single phrase highlighted
  // ---------------------------------------------------------------------------
  describe('single phrase highlighted', () => {
    it('wraps the matching phrase in a <mark> element', () => {
      const { container } = render(
        <HighlightedText text="The quick brown fox" phrases={['quick']} />,
      )

      const marks = container.querySelectorAll('mark')
      expect(marks).toHaveLength(1)
      expect(marks[0].textContent).toBe('quick')
    })

    it('renders the surrounding text outside the <mark>', () => {
      const { container } = render(
        <HighlightedText text="The quick brown fox" phrases={['quick']} />,
      )

      const wrapper = container.firstElementChild!
      expect(wrapper.textContent).toBe('The quick brown fox')
    })

    it('highlights a phrase that appears at the start of the text', () => {
      const { container } = render(
        <HighlightedText text="Hello world" phrases={['Hello']} />,
      )

      const marks = container.querySelectorAll('mark')
      expect(marks).toHaveLength(1)
      expect(marks[0].textContent).toBe('Hello')
    })

    it('highlights a phrase that appears at the end of the text', () => {
      const { container } = render(
        <HighlightedText text="Hello world" phrases={['world']} />,
      )

      const marks = container.querySelectorAll('mark')
      expect(marks).toHaveLength(1)
      expect(marks[0].textContent).toBe('world')
    })
  })

  // ---------------------------------------------------------------------------
  // 2. Multiple non-overlapping phrases
  // ---------------------------------------------------------------------------
  describe('multiple non-overlapping phrases', () => {
    it('renders a separate <mark> for each phrase', () => {
      const { container } = render(
        <HighlightedText
          text="The quick brown fox jumps"
          phrases={['quick', 'fox']}
        />,
      )

      const marks = container.querySelectorAll('mark')
      expect(marks).toHaveLength(2)
      expect(marks[0].textContent).toBe('quick')
      expect(marks[1].textContent).toBe('fox')
    })

    it('preserves the full text content across all nodes', () => {
      const text = 'The quick brown fox jumps'
      const { container } = render(
        <HighlightedText text={text} phrases={['quick', 'fox']} />,
      )

      expect(container.firstElementChild!.textContent).toBe(text)
    })

    it('handles three non-overlapping phrases', () => {
      const { container } = render(
        <HighlightedText
          text="alpha beta gamma delta"
          phrases={['alpha', 'gamma', 'delta']}
        />,
      )

      const marks = container.querySelectorAll('mark')
      expect(marks).toHaveLength(3)
      const markTexts = Array.from(marks).map((m) => m.textContent)
      expect(markTexts).toContain('alpha')
      expect(markTexts).toContain('gamma')
      expect(markTexts).toContain('delta')
    })
  })

  // ---------------------------------------------------------------------------
  // 3. Overlapping phrases
  // ---------------------------------------------------------------------------
  describe('overlapping phrases', () => {
    it('merges two overlapping phrases into a single <mark>', () => {
      // "quick brown" and "brown fox" overlap on "brown"
      const { container } = render(
        <HighlightedText
          text="The quick brown fox"
          phrases={['quick brown', 'brown fox']}
        />,
      )

      const marks = container.querySelectorAll('mark')
      expect(marks).toHaveLength(1)
      expect(marks[0].textContent).toBe('quick brown fox')
    })

    it('merges a phrase that is a substring of another phrase', () => {
      // "brown" is contained within "quick brown fox"
      const { container } = render(
        <HighlightedText
          text="The quick brown fox"
          phrases={['quick brown fox', 'brown']}
        />,
      )

      const marks = container.querySelectorAll('mark')
      expect(marks).toHaveLength(1)
      expect(marks[0].textContent).toBe('quick brown fox')
    })

    it('does not double-wrap any character', () => {
      const { container } = render(
        <HighlightedText
          text="abcdef"
          phrases={['abc', 'cde']}
        />,
      )

      // Merged range should be "abcde" — one mark, no nested marks
      const marks = container.querySelectorAll('mark')
      expect(marks).toHaveLength(1)
      expect(marks[0].textContent).toBe('abcde')
      // No nested <mark> elements
      expect(marks[0].querySelectorAll('mark')).toHaveLength(0)
    })
  })

  // ---------------------------------------------------------------------------
  // 4. Phrase not present in text
  // ---------------------------------------------------------------------------
  describe('phrase not present in text', () => {
    it('renders no <mark> elements when the phrase is absent', () => {
      const { container } = render(
        <HighlightedText text="Hello world" phrases={['xyz']} />,
      )

      expect(container.querySelectorAll('mark')).toHaveLength(0)
    })

    it('renders the full plain text when the phrase is absent', () => {
      const text = 'Hello world'
      const { container } = render(
        <HighlightedText text={text} phrases={['xyz']} />,
      )

      expect(container.firstElementChild!.textContent).toBe(text)
    })

    it('is case-sensitive — does not highlight mismatched case', () => {
      const { container } = render(
        <HighlightedText text="Hello World" phrases={['hello']} />,
      )

      // "hello" (lowercase) should not match "Hello" (uppercase H)
      expect(container.querySelectorAll('mark')).toHaveLength(0)
    })
  })

  // ---------------------------------------------------------------------------
  // 5. Empty phrases array
  // ---------------------------------------------------------------------------
  describe('empty phrases array', () => {
    it('renders no <mark> elements when phrases is empty', () => {
      const { container } = render(
        <HighlightedText text="Hello world" phrases={[]} />,
      )

      expect(container.querySelectorAll('mark')).toHaveLength(0)
    })

    it('renders the full plain text when phrases is empty', () => {
      const text = 'Hello world'
      const { container } = render(
        <HighlightedText text={text} phrases={[]} />,
      )

      expect(container.firstElementChild!.textContent).toBe(text)
    })

    it('renders no <mark> elements when phrases contains only empty strings', () => {
      const { container } = render(
        <HighlightedText text="Hello world" phrases={['', '']} />,
      )

      expect(container.querySelectorAll('mark')).toHaveLength(0)
    })
  })
})
