"""
Unit tests for backend/ml/data_loader.py

Covers:
- Valid CSV loading (labels, row counts, column presence)
- Malformed row skipping (null text, empty text, non-string text)
- preprocess(): lowercasing
- preprocess(): HTML tag stripping
- preprocess(): Unicode NFC normalisation
"""

import io
import textwrap
from pathlib import Path

import pandas as pd
import pytest

from ml.data_loader import _load_single_csv, load_data, preprocess


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_csv(tmp_path: Path, filename: str, content: str) -> Path:
    """Write *content* to *tmp_path/filename* and return the Path."""
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# preprocess() tests
# ---------------------------------------------------------------------------


class TestPreprocess:
    def test_lowercases_text(self):
        assert preprocess("Hello WORLD") == "hello world"

    def test_lowercases_mixed_case(self):
        result = preprocess("Breaking NEWS: Scientists DISCOVER New Planet")
        assert result == result.lower()

    def test_strips_simple_html_tags(self):
        result = preprocess("<p>Hello <b>world</b></p>")
        assert "<" not in result
        assert ">" not in result
        assert "hello" in result
        assert "world" in result

    def test_strips_anchor_tags(self):
        result = preprocess('<a href="http://example.com">Click here</a>')
        assert "<a" not in result
        assert "href" not in result
        assert "click here" in result

    def test_strips_nested_html(self):
        html = "<div><span class='x'><em>Fake</em> news</span></div>"
        result = preprocess(html)
        assert "<" not in result
        assert "fake" in result
        assert "news" in result

    def test_no_html_unchanged_structure(self):
        plain = "This is plain text without any markup."
        result = preprocess(plain)
        assert result == plain.lower()

    def test_nfc_normalisation_composed_form(self):
        # 'é' can be represented as U+00E9 (precomposed) or
        # U+0065 + U+0301 (decomposed).  After NFC both should be equal.
        precomposed = "\u00e9"          # é  (NFC)
        decomposed = "e\u0301"          # e + combining acute accent (NFD)
        assert preprocess(precomposed) == preprocess(decomposed)

    def test_nfc_normalisation_returns_string(self):
        result = preprocess("café")
        assert isinstance(result, str)

    def test_empty_string(self):
        assert preprocess("") == ""

    def test_whitespace_only(self):
        assert preprocess("   \t\n  ") == "   \t\n  "

    def test_html_entities_decoded(self):
        # html.parser with convert_charrefs=True decodes &amp; etc.
        result = preprocess("<p>AT&amp;T</p>")
        assert "at&t" in result

    def test_combined_html_and_case(self):
        result = preprocess("<H1>BREAKING NEWS</H1>")
        assert "breaking news" in result
        assert "<" not in result


# ---------------------------------------------------------------------------
# _load_single_csv() tests
# ---------------------------------------------------------------------------


class TestLoadSingleCsv:
    def test_valid_csv_returns_correct_columns(self, tmp_path):
        csv_path = _write_csv(
            tmp_path,
            "valid.csv",
            """\
            title,text,subject,date
            Article 1,This is real news.,politics,2023-01-01
            Article 2,Another real article.,world,2023-01-02
            """,
        )
        df = _load_single_csv(csv_path, label=0)
        assert list(df.columns) == ["text", "label"]

    def test_valid_csv_assigns_label(self, tmp_path):
        csv_path = _write_csv(
            tmp_path,
            "fake.csv",
            """\
            title,text,subject,date
            Fake 1,This is fake news.,politics,2023-01-01
            """,
        )
        df = _load_single_csv(csv_path, label=1)
        assert (df["label"] == 1).all()

    def test_valid_csv_assigns_real_label(self, tmp_path):
        csv_path = _write_csv(
            tmp_path,
            "true.csv",
            """\
            title,text,subject,date
            Real 1,This is real news.,politics,2023-01-01
            """,
        )
        df = _load_single_csv(csv_path, label=0)
        assert (df["label"] == 0).all()

    def test_valid_csv_row_count(self, tmp_path):
        csv_path = _write_csv(
            tmp_path,
            "multi.csv",
            """\
            title,text,subject,date
            A,Text one.,politics,2023-01-01
            B,Text two.,world,2023-01-02
            C,Text three.,sports,2023-01-03
            """,
        )
        df = _load_single_csv(csv_path, label=0)
        assert len(df) == 3

    def test_skips_row_with_null_text(self, tmp_path):
        csv_path = _write_csv(
            tmp_path,
            "null_text.csv",
            """\
            title,text,subject,date
            Good,Valid text here.,politics,2023-01-01
            Bad,,world,2023-01-02
            """,
        )
        df = _load_single_csv(csv_path, label=0)
        # Only the row with valid text should remain.
        assert len(df) == 1
        assert df.iloc[0]["text"] == "Valid text here."

    def test_skips_row_with_whitespace_only_text(self, tmp_path):
        csv_path = _write_csv(
            tmp_path,
            "ws_text.csv",
            """\
            title,text,subject,date
            Good,Real content.,politics,2023-01-01
            Bad,"   ",world,2023-01-02
            """,
        )
        df = _load_single_csv(csv_path, label=0)
        assert len(df) == 1

    def test_skips_multiple_malformed_rows(self, tmp_path):
        csv_path = _write_csv(
            tmp_path,
            "mixed.csv",
            """\
            title,text,subject,date
            Good1,First valid article.,politics,2023-01-01
            Bad1,,world,2023-01-02
            Good2,Second valid article.,sports,2023-01-03
            Bad2,"  ",tech,2023-01-04
            Good3,Third valid article.,health,2023-01-05
            """,
        )
        df = _load_single_csv(csv_path, label=1)
        assert len(df) == 3

    def test_raises_on_missing_text_column(self, tmp_path):
        csv_path = _write_csv(
            tmp_path,
            "no_text_col.csv",
            """\
            title,body,subject,date
            Article 1,Some content.,politics,2023-01-01
            """,
        )
        with pytest.raises(ValueError, match="missing the required 'text' column"):
            _load_single_csv(csv_path, label=0)

    def test_empty_csv_returns_empty_dataframe(self, tmp_path):
        csv_path = _write_csv(
            tmp_path,
            "empty.csv",
            """\
            title,text,subject,date
            """,
        )
        df = _load_single_csv(csv_path, label=0)
        assert len(df) == 0
        assert "text" in df.columns
        assert "label" in df.columns

    def test_all_malformed_returns_empty_dataframe(self, tmp_path):
        csv_path = _write_csv(
            tmp_path,
            "all_bad.csv",
            """\
            title,text,subject,date
            Bad1,,world,2023-01-02
            Bad2,"  ",tech,2023-01-04
            """,
        )
        df = _load_single_csv(csv_path, label=0)
        assert len(df) == 0


# ---------------------------------------------------------------------------
# load_data() tests
# ---------------------------------------------------------------------------


class TestLoadData:
    def test_load_data_combines_fake_and_true(self, tmp_path):
        fake_csv = _write_csv(
            tmp_path,
            "Fake.csv",
            """\
            title,text,subject,date
            F1,Fake article one.,politics,2023-01-01
            F2,Fake article two.,world,2023-01-02
            """,
        )
        true_csv = _write_csv(
            tmp_path,
            "True.csv",
            """\
            title,text,subject,date
            T1,Real article one.,politics,2023-01-01
            T2,Real article two.,world,2023-01-02
            T3,Real article three.,sports,2023-01-03
            """,
        )
        df = load_data(fake_csv=fake_csv, true_csv=true_csv)
        assert len(df) == 5

    def test_load_data_has_correct_columns(self, tmp_path):
        fake_csv = _write_csv(
            tmp_path,
            "Fake.csv",
            "title,text,subject,date\nF1,Fake text.,politics,2023-01-01\n",
        )
        true_csv = _write_csv(
            tmp_path,
            "True.csv",
            "title,text,subject,date\nT1,Real text.,politics,2023-01-01\n",
        )
        df = load_data(fake_csv=fake_csv, true_csv=true_csv)
        assert set(df.columns) == {"text", "label"}

    def test_load_data_fake_label_is_1(self, tmp_path):
        fake_csv = _write_csv(
            tmp_path,
            "Fake.csv",
            "title,text,subject,date\nF1,Fake text.,politics,2023-01-01\n",
        )
        true_csv = _write_csv(
            tmp_path,
            "True.csv",
            "title,text,subject,date\nT1,Real text.,politics,2023-01-01\n",
        )
        df = load_data(fake_csv=fake_csv, true_csv=true_csv)
        fake_rows = df[df["text"] == "Fake text."]
        assert (fake_rows["label"] == 1).all()

    def test_load_data_real_label_is_0(self, tmp_path):
        fake_csv = _write_csv(
            tmp_path,
            "Fake.csv",
            "title,text,subject,date\nF1,Fake text.,politics,2023-01-01\n",
        )
        true_csv = _write_csv(
            tmp_path,
            "True.csv",
            "title,text,subject,date\nT1,Real text.,politics,2023-01-01\n",
        )
        df = load_data(fake_csv=fake_csv, true_csv=true_csv)
        real_rows = df[df["text"] == "Real text."]
        assert (real_rows["label"] == 0).all()

    def test_load_data_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_data(
                fake_csv=tmp_path / "nonexistent_fake.csv",
                true_csv=tmp_path / "nonexistent_true.csv",
            )

    def test_load_data_skips_malformed_rows_in_combined(self, tmp_path):
        fake_csv = _write_csv(
            tmp_path,
            "Fake.csv",
            """\
            title,text,subject,date
            F1,Fake article.,politics,2023-01-01
            F_bad,,world,2023-01-02
            """,
        )
        true_csv = _write_csv(
            tmp_path,
            "True.csv",
            """\
            title,text,subject,date
            T1,Real article.,politics,2023-01-01
            """,
        )
        df = load_data(fake_csv=fake_csv, true_csv=true_csv)
        # 1 valid fake + 1 valid real = 2 rows (malformed fake row skipped)
        assert len(df) == 2
