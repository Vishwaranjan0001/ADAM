"""Extraction and OCR quality evaluation metrics including CER and exact match scores."""

import logging
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Acceptance threshold for clean Hindi/English text extractions
DEFAULT_EXACT_MATCH_THRESHOLD: float = 0.98


@dataclass
class PageQualityScore:
    """Evaluation metrics for a single document page against ground truth text."""

    page_number: int
    cer: float
    exact_match: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert page quality score into a dictionary representation."""
        return {
            "page_number": self.page_number,
            "cer": self.cer,
            "exact_match": self.exact_match,
        }


@dataclass
class ExtractionQualityReport:
    """Aggregated extraction quality report across evaluated document pages."""

    per_page: List[Dict[str, Any]] = field(default_factory=list)
    aggregate_cer: float = 0.0
    aggregate_exact_match: float = 0.0
    pages_evaluated: int = 0
    meets_threshold: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert quality report to dictionary representation."""
        return {
            "per_page": self.per_page,
            "aggregate_cer": self.aggregate_cer,
            "aggregate_exact_match": self.aggregate_exact_match,
            "pages_evaluated": self.pages_evaluated,
            "meets_threshold": self.meets_threshold,
        }


class BaseExtractionMetric(ABC):
    """Abstract base class for text extraction quality metrics."""

    @abstractmethod
    def evaluate(self, reference: str, hypothesis: str) -> float:
        """Evaluate hypothesis text against reference ground truth.

        Args:
            reference: Reference ground truth string.
            hypothesis: Extracted or OCR candidate string.

        Returns:
            Metric score as a float.
        """
        pass


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute standard Levenshtein edit distance using dynamic programming.

    Uses an O(min(len(s1), len(s2))) space-optimized row-buffer algorithm.
    Allowed operations: insertion, deletion, substitution (cost 1 each).

    Args:
        s1: First string.
        s2: Second string.

    Returns:
        Minimum number of single-character edits required to transform s1 into s2.
    """
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    # Ensure s2 is the shorter string to optimize space buffer
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    # s1 is longer or equal to s2; buffer size is len(s2) + 1
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1] * (len(s2) + 1)
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row[j + 1] = min(
                prev_row[j + 1] + 1,  # deletion from s1
                curr_row[j] + 1,      # insertion into s1
                prev_row[j] + cost,   # substitution or match
            )
        prev_row = curr_row

    return prev_row[len(s2)]


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate (CER) between reference and hypothesis strings.

    Normalizes both strings using Unicode NFC (crucial for Devanagari and Latin conjuncts).
    Computes minimum edit distance (Levenshtein) via dynamic programming without external dependencies.
    Returns edit_distance / len(reference) if reference is non-empty, else 0.0.

    Args:
        reference: Ground truth reference text.
        hypothesis: Extracted or OCR candidate text.

    Returns:
        Character error rate as a float (0.0 represents zero errors).
    """
    if reference is None:
        reference = ""
    if hypothesis is None:
        hypothesis = ""

    ref_norm = unicodedata.normalize("NFC", reference)
    hyp_norm = unicodedata.normalize("NFC", hypothesis)

    if not ref_norm:
        return 0.0

    edit_dist = levenshtein_distance(ref_norm, hyp_norm)
    return float(edit_dist / len(ref_norm))


def exact_match_score(reference: str, hypothesis: str) -> float:
    """Compute position-aligned character exact match percentage.

    Both strings are normalized to Unicode NFC before comparison.
    Compares characters at corresponding positions (0-indexed).
    The score represents the percentage of matching characters over the maximum
    length of the two strings, constrained strictly to [0.0, 1.0].
    If both strings are empty, returns 1.0.

    Args:
        reference: Ground truth reference text.
        hypothesis: Extracted or OCR candidate text.

    Returns:
        Exact match score in the range [0.0, 1.0].
    """
    if reference is None:
        reference = ""
    if hypothesis is None:
        hypothesis = ""

    ref_norm = unicodedata.normalize("NFC", reference)
    hyp_norm = unicodedata.normalize("NFC", hypothesis)

    if not ref_norm and not hyp_norm:
        return 1.0

    max_len = max(len(ref_norm), len(hyp_norm))
    if max_len == 0:
        return 1.0

    matches = sum(1 for r, h in zip(ref_norm, hyp_norm) if r == h)
    return float(matches / max_len)


class CharacterErrorRateMetric(BaseExtractionMetric):
    """Evaluates Character Error Rate (CER) using Levenshtein distance."""

    def evaluate(self, reference: str, hypothesis: str) -> float:
        return character_error_rate(reference, hypothesis)


class ExactMatchMetric(BaseExtractionMetric):
    """Evaluates position-aligned character exact match score."""

    def evaluate(self, reference: str, hypothesis: str) -> float:
        return exact_match_score(reference, hypothesis)


def report_extraction_quality(
    pages: Sequence[Any],
    reference_texts: Dict[Any, Optional[str]],
    threshold: float = DEFAULT_EXACT_MATCH_THRESHOLD,
) -> Dict[str, Any]:
    """Evaluate OCR and text extraction quality across pages against reference text.

    Compares candidate text from each page with ground truth reference text.
    Evaluates each page possessing a matching entry in `reference_texts`.
    Candidate text is retrieved from `.selected_text`, falling back to `.clean_text`
    or dictionary keys.

    Args:
        pages: List of page objects with `.page_number` and `.selected_text` attributes
               (or dictionary equivalents).
        reference_texts: Mapping of page_number (int or str) to reference string.
        threshold: Acceptance threshold for aggregate exact match (default: 0.98).

    Returns:
        Dict containing:
            - per_page: list of dicts with {"page_number", "cer", "exact_match"}
            - aggregate_cer: mean CER across evaluated pages (float)
            - aggregate_exact_match: mean exact match across evaluated pages (float)
            - pages_evaluated: number of evaluated pages (int)
            - meets_threshold: bool (True if aggregate_exact_match >= threshold)
    """
    per_page: List[Dict[str, Any]] = []

    if not pages or not reference_texts:
        return {
            "per_page": [],
            "aggregate_cer": 0.0,
            "aggregate_exact_match": 0.0,
            "pages_evaluated": 0,
            "meets_threshold": False,
        }

    for page in pages:
        # Extract page number
        page_num: Optional[Any] = None
        if hasattr(page, "page_number"):
            page_num = page.page_number
        elif isinstance(page, dict) and "page_number" in page:
            page_num = page["page_number"]

        if page_num is None:
            continue

        # Look up reference text by exact key, string representation, or integer
        has_ref = False
        ref_text: str = ""

        if page_num in reference_texts:
            has_ref = True
            ref_text = reference_texts[page_num] or ""
        elif str(page_num) in reference_texts:
            has_ref = True
            ref_text = reference_texts[str(page_num)] or ""
        elif isinstance(page_num, str) and page_num.isdigit() and int(page_num) in reference_texts:
            has_ref = True
            ref_text = reference_texts[int(page_num)] or ""

        if not has_ref:
            # Skip pages without ground truth references
            continue

        # Extract hypothesis text
        hyp_text: str = ""
        if hasattr(page, "selected_text"):
            hyp_text = page.selected_text or ""
        elif isinstance(page, dict) and "selected_text" in page:
            hyp_text = page.get("selected_text") or ""
        elif hasattr(page, "clean_text"):
            hyp_text = page.clean_text or ""
        elif isinstance(page, dict) and "clean_text" in page:
            hyp_text = page.get("clean_text") or ""

        cer = character_error_rate(ref_text, hyp_text)
        em = exact_match_score(ref_text, hyp_text)

        # Normalize page number to int if numeric
        normalized_page_no: Any = page_num
        if isinstance(page_num, (int, str)) and str(page_num).isdigit():
            normalized_page_no = int(page_num)

        per_page.append({
            "page_number": normalized_page_no,
            "cer": cer,
            "exact_match": em,
        })

    pages_evaluated = len(per_page)
    if pages_evaluated > 0:
        aggregate_cer = sum(item["cer"] for item in per_page) / pages_evaluated
        aggregate_exact_match = sum(item["exact_match"] for item in per_page) / pages_evaluated
    else:
        aggregate_cer = 0.0
        aggregate_exact_match = 0.0

    meets_threshold = bool(aggregate_exact_match >= threshold)

    return {
        "per_page": per_page,
        "aggregate_cer": float(aggregate_cer),
        "aggregate_exact_match": float(aggregate_exact_match),
        "pages_evaluated": pages_evaluated,
        "meets_threshold": meets_threshold,
    }
