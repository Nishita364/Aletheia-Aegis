"""
CSV loader and preprocessor for the Fake News Detector training pipeline.

Loads archive/Fake.csv (label=1) and archive/True.csv (label=0), concatenates
them into a single DataFrame, and exposes a preprocess() function that
normalises raw article text before vectorisation.

Requirements: 2.3, 12.1, 12.2
"""

import logging
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

import pandas as pd

# Regex to strip wire-service datelines like:
#   "WASHINGTON (Reuters) - "
#   "NEW YORK (AP) - "
#   "LONDON (AFP) - "
# These appear only in True.csv and would bias the model toward dateline patterns.
_DATELINE_RE = re.compile(
    r"^[A-Z][A-Z\s,\.]{0,50}\s*\([A-Za-z]+\)\s*[-–—]\s*",
    re.MULTILINE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "archive"
_FAKE_CSV = _ARCHIVE_DIR / "Fake.csv"
_TRUE_CSV = _ARCHIVE_DIR / "True.csv"

# ---------------------------------------------------------------------------
# HTML stripping helper
# ---------------------------------------------------------------------------


class _HTMLStripper(HTMLParser):
    """Minimal HTMLParser subclass that collects non-tag text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:  # noqa: D102
        self._parts.append(data)

    def get_text(self) -> str:  # noqa: D102
        return " ".join(self._parts)


def _strip_html(text: str) -> str:
    """Remove HTML tags from *text* using the stdlib html.parser."""
    # Fast path: skip parsing when there are no angle brackets.
    if "<" not in text:
        return text
    stripper = _HTMLStripper()
    try:
        stripper.feed(text)
        return stripper.get_text()
    except Exception:  # pragma: no cover – defensive fallback
        # Fall back to a simple regex if the parser raises unexpectedly.
        return re.sub(r"<[^>]+>", " ", text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def preprocess(text: str) -> str:
    """Normalise *text* for ML feature extraction.

    Steps applied in order:
    1. Unicode NFC normalisation (handles Telugu/Hindi composed forms).
    2. HTML tag stripping.
    3. Lowercase conversion.

    Parameters
    ----------
    text:
        Raw article text (may contain HTML markup or Unicode variants).

    Returns
    -------
    str
        Cleaned, lowercased, NFC-normalised text.
    """
    # 1. NFC normalisation first so that HTML entities decoded by the parser
    #    are already in canonical form.
    text = unicodedata.normalize("NFC", text)
    # 2. Strip HTML tags.
    text = _strip_html(text)
    # 3. Strip wire-service datelines (e.g. "WASHINGTON (Reuters) - ").
    #    These appear only in real-news articles and bias the model toward
    #    dateline patterns rather than actual content.
    text = _DATELINE_RE.sub("", text)
    # 4. Lowercase.
    text = text.lower()
    return text


def _load_single_csv(path: Path, label: int) -> pd.DataFrame:
    """Load one CSV file, assign *label*, and drop malformed rows.

    A row is considered malformed when the ``text`` column is missing,
    null, or not a non-empty string after stripping whitespace.  Such rows
    are skipped with a WARNING log entry that includes the row number.

    Parameters
    ----------
    path:
        Absolute path to the CSV file.
    label:
        Integer label to assign to every row (0 = Real, 1 = Fake).

    Returns
    -------
    pd.DataFrame
        DataFrame with columns ``text`` and ``label``.
    """
    logger.info("Loading %s (label=%d)", path, label)

    try:
        raw: pd.DataFrame = pd.read_csv(
            path,
            on_bad_lines="warn",   # skip rows with wrong number of fields
            engine="python",       # more lenient parser
            dtype={"text": str},   # always read text column as strings
        )
    except Exception as exc:
        logger.error("Failed to read %s: %s", path, exc)
        raise

    # Validate that the required column exists.
    if "text" not in raw.columns:
        raise ValueError(
            f"CSV file {path} is missing the required 'text' column. "
            f"Found columns: {list(raw.columns)}"
        )

    valid_rows: list[pd.Series] = []
    skipped = 0

    for row_number, (_, row) in enumerate(raw.iterrows(), start=2):
        # row_number starts at 2 because row 1 is the header.
        cell = row.get("text")
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            logger.warning(
                "Skipping malformed row %d in %s: 'text' field is null",
                row_number,
                path.name,
            )
            skipped += 1
            continue
        if not isinstance(cell, str) or not cell.strip():
            logger.warning(
                "Skipping malformed row %d in %s: 'text' field is empty or "
                "not a string (got %r)",
                row_number,
                path.name,
                cell,
            )
            skipped += 1
            continue
        valid_rows.append(row)

    if skipped:
        logger.warning(
            "Skipped %d malformed row(s) in %s", skipped, path.name
        )

    if not valid_rows:
        logger.warning("No valid rows found in %s", path.name)
        return pd.DataFrame(columns=["text", "label"])

    df = pd.DataFrame(valid_rows)[["text"]].copy()
    df["label"] = label
    df = df.reset_index(drop=True)
    logger.info("Loaded %d valid rows from %s", len(df), path.name)
    return df


def load_data(
    fake_csv: Optional[Path] = None,
    true_csv: Optional[Path] = None,
) -> pd.DataFrame:
    """Load and concatenate the Fake and True news CSV datasets.

    Parameters
    ----------
    fake_csv:
        Path to the fake-news CSV.  Defaults to ``archive/Fake.csv``
        relative to the repository root.
    true_csv:
        Path to the real-news CSV.  Defaults to ``archive/True.csv``
        relative to the repository root.

    Returns
    -------
    pd.DataFrame
        Concatenated DataFrame with columns ``text`` (str) and
        ``label`` (int, 0 = Real / 1 = Fake), shuffled with a fixed
        random seed for reproducibility.

    Raises
    ------
    FileNotFoundError
        If either CSV file does not exist at the resolved path.
    ValueError
        If either CSV file is missing the required ``text`` column.
    """
    fake_path = Path(fake_csv) if fake_csv is not None else _FAKE_CSV
    true_path = Path(true_csv) if true_csv is not None else _TRUE_CSV

    for p in (fake_path, true_path):
        if not p.exists():
            raise FileNotFoundError(f"Dataset file not found: {p}")

    fake_df = _load_single_csv(fake_path, label=1)
    true_df = _load_single_csv(true_path, label=0)

    combined = pd.concat([fake_df, true_df], ignore_index=True)
    combined = combined.sample(frac=1, random_state=42).reset_index(drop=True)
    logger.info(
        "Combined dataset: %d rows (%d fake, %d real)",
        len(combined),
        len(fake_df),
        len(true_df),
    )
    return combined
