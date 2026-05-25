"""
Property-based tests for the CSV parser in backend/ml/data_loader.py.

# Feature: fake-news-detector, Property 7: CSV Parsing Skips Malformed Rows Without Halting

Property 7: CSV Parsing Skips Malformed Rows Without Halting
  For any CSV file containing a mix of valid rows and malformed rows
  (missing `text` column or having empty/null text), the parser SHALL
  parse all valid rows into structured records and SHALL NOT include any
  malformed rows in the resulting dataset, while continuing to process
  the entire file.

Validates: Requirements 12.1, 12.2
"""

import io
import random
import tempfile
import textwrap
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from ml.data_loader import _load_single_csv


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A "valid" row has a non-empty, non-whitespace text value.
# We generate text that won't break CSV parsing (no unescaped quotes/newlines).
_safe_text = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),   # exclude surrogates
        blacklist_characters=('\"', '\n', '\r', '\x00'),
    ),
    min_size=1,
    max_size=200,
).filter(lambda t: t.strip() != "")

# A "valid row" dict has at least a non-empty text field plus some extra columns.
_valid_row_strategy = st.fixed_dictionaries(
    {
        "title": st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),
                blacklist_characters=('\"', '\n', '\r', '\x00'),
            ),
            max_size=80,
        ),
        "text": _safe_text,
        "subject": st.sampled_from(["politics", "world", "sports", "tech", "health"]),
        "date": st.just("2023-01-01"),
    }
)

# A "malformed row" is one where the text field is either empty or whitespace-only.
_malformed_row_strategy = st.fixed_dictionaries(
    {
        "title": st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),
                blacklist_characters=('\"', '\n', '\r', '\x00'),
            ),
            max_size=80,
        ),
        # text is empty or whitespace-only
        "text": st.one_of(
            st.just(""),
            st.text(
                alphabet=st.sampled_from([" ", "\t"]),
                min_size=1,
                max_size=10,
            ),
        ),
        "subject": st.sampled_from(["politics", "world"]),
        "date": st.just("2023-01-01"),
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape_csv_field(value: str) -> str:
    """Wrap a field in double-quotes if it contains commas, quotes, or whitespace."""
    if any(c in value for c in (',', '"', '\n', '\r')):
        return '"' + value.replace('"', '""') + '"'
    return value


def _rows_to_csv(rows: list[dict]) -> str:
    """Convert a list of row dicts to a CSV string with header."""
    header = "title,text,subject,date"
    lines = [header]
    for row in rows:
        fields = [
            _escape_csv_field(str(row.get("title", ""))),
            _escape_csv_field(str(row.get("text", ""))),
            _escape_csv_field(str(row.get("subject", ""))),
            _escape_csv_field(str(row.get("date", ""))),
        ]
        lines.append(",".join(fields))
    return "\n".join(lines) + "\n"


def _write_csv_file(tmp_path: Path, rows: list[dict], filename: str = "test.csv") -> Path:
    """Write rows to a CSV file and return the path."""
    content = _rows_to_csv(rows)
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Property 7: CSV Parsing Skips Malformed Rows Without Halting
# ---------------------------------------------------------------------------

@given(
    valid_rows=st.lists(_valid_row_strategy, min_size=1, max_size=20),
    malformed_rows=st.lists(_malformed_row_strategy, min_size=0, max_size=10),
    label=st.integers(min_value=0, max_value=1),
)
@settings(max_examples=20)
def test_property7_csv_parsing_skips_malformed_rows(
    valid_rows: list[dict],
    malformed_rows: list[dict],
    label: int,
) -> None:
    """
    **Validates: Requirements 12.1, 12.2**

    Property 7: CSV Parsing Skips Malformed Rows Without Halting

    For any CSV with a mix of valid rows (non-empty text) and malformed rows
    (empty or whitespace-only text):
    - All valid rows appear in the output DataFrame (by text content).
    - No malformed rows appear in the output DataFrame.
    - The parser does not raise an exception (it continues processing).
    """
    # Interleave valid and malformed rows to create a realistic mixed CSV.
    rng = random.Random(42)
    all_rows = valid_rows + malformed_rows
    rng.shuffle(all_rows)

    with tempfile.TemporaryDirectory() as _tmp:
        tmp_path = Path(_tmp)
        csv_path = _write_csv_file(tmp_path, all_rows)

        # The parser must not raise an exception.
        df = _load_single_csv(csv_path, label=label)

    # --- Assertion 1: All valid rows appear in the output ---
    # Collect the expected text values from valid rows.
    expected_texts = {row["text"].strip() for row in valid_rows}
    actual_texts = set(df["text"].str.strip().tolist())

    for expected_text in expected_texts:
        assert expected_text in actual_texts, (
            f"Valid row with text {expected_text!r} was not found in the output. "
            f"Output texts: {actual_texts}"
        )

    # --- Assertion 2: No malformed rows appear in the output ---
    # Malformed rows have empty or whitespace-only text; after stripping they are "".
    for row in malformed_rows:
        malformed_text = row["text"]
        # A malformed row's text, when stripped, is empty.
        # It should not appear in the output (the output only has non-empty stripped text).
        assert malformed_text.strip() == "", (
            f"Test setup error: malformed row text {malformed_text!r} is not whitespace-only"
        )
        # Verify the raw malformed text is not in the output.
        if malformed_text in df["text"].tolist():
            assert False, (
                f"Malformed row with text {malformed_text!r} appeared in the output DataFrame."
            )

    # --- Assertion 3: Output row count equals number of valid rows ---
    assert len(df) == len(valid_rows), (
        f"Expected {len(valid_rows)} valid rows in output, got {len(df)}. "
        f"Malformed rows: {len(malformed_rows)}"
    )

    # --- Assertion 4: All output rows have the correct label ---
    assert (df["label"] == label).all(), (
        f"Some rows have incorrect label. Expected all to be {label}."
    )

    # --- Assertion 5: Output columns are exactly ['text', 'label'] ---
    assert list(df.columns) == ["text", "label"], (
        f"Unexpected columns in output: {list(df.columns)}"
    )


@given(
    valid_rows=st.lists(_valid_row_strategy, min_size=1, max_size=20),
    label=st.integers(min_value=0, max_value=1),
)
@settings(max_examples=20)
def test_property7_all_valid_rows_no_malformed(
    valid_rows: list[dict],
    label: int,
) -> None:
    """
    **Validates: Requirements 12.1, 12.2**

    Degenerate case of Property 7: when all rows are valid, all rows appear
    in the output and the parser does not halt.
    """
    with tempfile.TemporaryDirectory() as _tmp:
        tmp_path = Path(_tmp)
        csv_path = _write_csv_file(tmp_path, valid_rows)
        df = _load_single_csv(csv_path, label=label)

    assert len(df) == len(valid_rows), (
        f"Expected {len(valid_rows)} rows, got {len(df)}"
    )
    assert (df["label"] == label).all()
    assert list(df.columns) == ["text", "label"]


@given(
    malformed_rows=st.lists(_malformed_row_strategy, min_size=1, max_size=20),
    label=st.integers(min_value=0, max_value=1),
)
@settings(max_examples=20)
def test_property7_all_malformed_rows_returns_empty(
    malformed_rows: list[dict],
    label: int,
) -> None:
    """
    **Validates: Requirements 12.1, 12.2**

    Degenerate case of Property 7: when all rows are malformed, the parser
    returns an empty DataFrame without raising an exception.
    """
    with tempfile.TemporaryDirectory() as _tmp:
        tmp_path = Path(_tmp)
        csv_path = _write_csv_file(tmp_path, malformed_rows)
        df = _load_single_csv(csv_path, label=label)

    assert len(df) == 0, (
        f"Expected empty DataFrame when all rows are malformed, got {len(df)} rows"
    )
    assert "text" in df.columns
    assert "label" in df.columns
