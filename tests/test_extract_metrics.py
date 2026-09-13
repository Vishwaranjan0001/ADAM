"""Tests for extraction and OCR metrics (CER, exact match, and quality reporting)."""

from dataclasses import dataclass
import unicodedata
import pytest

from adam.extract.metrics import (
    character_error_rate,
    exact_match_score,
    report_extraction_quality,
    levenshtein_distance,
    CharacterErrorRateMetric,
    ExactMatchMetric,
    PageQualityScore,
)


@dataclass
class DummyPage:
    page_number: int
    selected_text: str


def test_levenshtein_distance():
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("abc", "abc") == 0
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("", "test") == 4
    assert levenshtein_distance("test", "") == 4
    assert levenshtein_distance("abc", "abd") == 1
    assert levenshtein_distance("a", "b") == 1


def test_character_error_rate():
    # Identical strings
    assert character_error_rate("hello", "hello") == 0.0

    # Empty reference
    assert character_error_rate("", "hello") == 0.0
    assert character_error_rate("", "") == 0.0

    # None handling
    assert character_error_rate(None, "hello") == 0.0
    assert character_error_rate("hello", None) == 1.0

    # Total deletion
    assert character_error_rate("hello", "") == 1.0

    # Partial substitution
    # "sitting" vs "kitten": 3 edits / 7 chars
    assert character_error_rate("sitting", "kitten") == pytest.approx(3 / 7)

    # Insertion
    assert character_error_rate("cat", "cats") == pytest.approx(1 / 3)


def test_character_error_rate_unicode_nfc():
    # Decomposed vs precomposed Devanagari / Latin
    composed = "é"  # \u00e9
    decomposed = "e\u0301"  # e + combining acute accent

    assert composed != decomposed
    assert character_error_rate(composed, decomposed) == 0.0

    hindi_composed = unicodedata.normalize("NFC", "उत्तराखण्ड शासन")
    hindi_decomposed = unicodedata.normalize("NFD", "उत्तराखण्ड शासन")
    assert character_error_rate(hindi_composed, hindi_decomposed) == 0.0


def test_exact_match_score():
    # Identical
    assert exact_match_score("hello", "hello") == 1.0

    # Both empty
    assert exact_match_score("", "") == 1.0
    assert exact_match_score(None, None) == 1.0

    # One empty
    assert exact_match_score("abc", "") == 0.0
    assert exact_match_score("", "abc") == 0.0

    # Completely mismatched
    assert exact_match_score("abc", "xyz") == 0.0

    # Position-aligned match: 2 out of 3 match
    assert exact_match_score("abc", "abd") == pytest.approx(2 / 3)

    # Length discrepancy: 2 matches, max_len is 4
    assert exact_match_score("ab", "abcd") == pytest.approx(2 / 4)
    assert exact_match_score("abcd", "ab") == pytest.approx(2 / 4)


def test_exact_match_score_unicode():
    composed = "उत्तराखण्ड"
    decomposed = unicodedata.normalize("NFD", composed)
    assert exact_match_score(composed, decomposed) == 1.0


def test_report_extraction_quality_passing():
    pages = [
        DummyPage(page_number=1, selected_text="Finance Department Government of Uttarakhand"),
        DummyPage(page_number=2, selected_text="Office Memorandum No 102 Revision of Allowances"),
    ]
    reference_texts = {
        1: "Finance Department Government of Uttarakhand",
        2: "Office Memorandum No 102 Revision of Allowances",
    }

    report = report_extraction_quality(pages, reference_texts)

    assert report["pages_evaluated"] == 2
    assert report["aggregate_cer"] == 0.0
    assert report["aggregate_exact_match"] == 1.0
    assert report["meets_threshold"] is True
    assert len(report["per_page"]) == 2
    assert report["per_page"][0]["page_number"] == 1
    assert report["per_page"][0]["exact_match"] == 1.0


def test_report_extraction_quality_failing_threshold():
    pages = [
        DummyPage(page_number=1, selected_text="Totally wrong OCR text"),
        DummyPage(page_number=2, selected_text="Completely garbled output"),
    ]
    reference_texts = {
        1: "Finance Department Government of Uttarakhand",
        2: "Office Memorandum No 102 Revision of Allowances",
    }

    report = report_extraction_quality(pages, reference_texts)

    assert report["pages_evaluated"] == 2
    assert report["aggregate_exact_match"] < 0.98
    assert report["meets_threshold"] is False


def test_report_extraction_quality_missing_pages_and_dict_support():
    pages = [
        {"page_number": 1, "selected_text": "Page 1 clean text"},
        {"page_number": 2, "selected_text": "Page 2 unreferenced text"},
        {"page_number": 3, "clean_text": "Page 3 fallback clean text"},
    ]
    # Only pages 1 and 3 are present in ground truth references
    reference_texts = {
        1: "Page 1 clean text",
        3: "Page 3 fallback clean text",
    }

    report = report_extraction_quality(pages, reference_texts)

    assert report["pages_evaluated"] == 2
    assert [p["page_number"] for p in report["per_page"]] == [1, 3]
    assert report["meets_threshold"] is True


def test_report_extraction_quality_empty_input():
    report = report_extraction_quality([], {})
    assert report["pages_evaluated"] == 0
    assert report["aggregate_cer"] == 0.0
    assert report["aggregate_exact_match"] == 0.0
    assert report["meets_threshold"] is False
    assert report["per_page"] == []


def test_metric_evaluator_classes():
    cer_eval = CharacterErrorRateMetric()
    em_eval = ExactMatchMetric()

    assert cer_eval.evaluate("abc", "abc") == 0.0
    assert em_eval.evaluate("abc", "abc") == 1.0

    score = PageQualityScore(page_number=1, cer=0.05, exact_match=0.95)
    d = score.to_dict()
    assert d["page_number"] == 1
    assert d["cer"] == 0.05
    assert d["exact_match"] == 0.95
