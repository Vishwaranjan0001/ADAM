"""Quality gate evaluation system for document text extraction and OCR.

Evaluates per-page quality criteria including extraction confidence, character yield,
script consistency, tables, seals/signatures, handwriting, and text-OCR divergence.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import List, Optional, Tuple, Any


# ---------------------------------------------------------------------------
# Constants and Enumerations
# ---------------------------------------------------------------------------

class FlagType:
    """Standard quality flag types."""
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    LOW_CHAR_YIELD = "LOW_CHAR_YIELD"
    MIXED_SCRIPT = "MIXED_SCRIPT"
    HAS_TABLES = "HAS_TABLES"
    SEAL_SIGNATURE = "SEAL_SIGNATURE"
    HANDWRITTEN = "HANDWRITTEN"
    CONTRADICTORY_TEXT = "CONTRADICTORY_TEXT"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"


class Severity:
    """Urgency severity levels for quality flags."""
    WARNING = "WARNING"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class ReviewStatus:
    """Document/page review outcomes determined by quality gate evaluation."""
    FLAGGED = "FLAGGED"
    AUTO_APPROVED = "AUTO_APPROVED"


# Module-level aliases for direct import convenience
FLAG_LOW_CONFIDENCE = FlagType.LOW_CONFIDENCE
FLAG_LOW_CHAR_YIELD = FlagType.LOW_CHAR_YIELD
FLAG_MIXED_SCRIPT = FlagType.MIXED_SCRIPT
FLAG_HAS_TABLES = FlagType.HAS_TABLES
FLAG_SEAL_SIGNATURE = FlagType.SEAL_SIGNATURE
FLAG_HANDWRITTEN = FlagType.HANDWRITTEN
FLAG_CONTRADICTORY_TEXT = FlagType.CONTRADICTORY_TEXT
FLAG_OCR_UNAVAILABLE = FlagType.OCR_UNAVAILABLE

SEVERITY_WARNING = Severity.WARNING
SEVERITY_REQUIRES_REVIEW = Severity.REQUIRES_REVIEW

REVIEW_STATUS_FLAGGED = ReviewStatus.FLAGGED
REVIEW_STATUS_AUTO_APPROVED = ReviewStatus.AUTO_APPROVED


# ---------------------------------------------------------------------------
# Data Containers
# ---------------------------------------------------------------------------

@dataclass
class QualityFlag:
    """Represents a quality issue, anomaly, or review gate triggered on a document page.

    Attributes:
        flag_type: Identifier of the quality condition (e.g., LOW_CONFIDENCE,
            LOW_CHAR_YIELD, MIXED_SCRIPT, HAS_TABLES, SEAL_SIGNATURE, HANDWRITTEN,
            CONTRADICTORY_TEXT, OCR_UNAVAILABLE).
        severity: Urgency level ('WARNING' or 'REQUIRES_REVIEW').
        message: Human-readable diagnostic description of the condition.
        page_number: 1-indexed page number where the flag was raised.
    """
    flag_type: str
    severity: str
    message: str
    page_number: int


# ---------------------------------------------------------------------------
# Abstract Base Quality Gate
# ---------------------------------------------------------------------------

class BaseQualityGate(ABC):
    """Abstract base class for quality gate evaluators."""

    @classmethod
    @abstractmethod
    def evaluate(cls, *args: Any, **kwargs: Any) -> List[QualityFlag]:
        """Evaluate extraction data against quality gates and return detected flags."""
        pass


# ---------------------------------------------------------------------------
# Page Quality Gate Implementation
# ---------------------------------------------------------------------------

class PageQualityGate(BaseQualityGate):
    """Evaluates per-page quality criteria for document text extraction and OCR.

    Rules enforced:
    a. LOW_CONFIDENCE: text_confidence < CONFIDENCE_THRESHOLD (0.85) -> REQUIRES_REVIEW
    b. LOW_CHAR_YIELD: len(clean_text) < MIN_CHAR_YIELD (20) and not is_scanned -> WARNING;
                       if scanned and no OCR text -> REQUIRES_REVIEW
    c. MIXED_SCRIPT: detected_language == 'bilingual' or script ratio >= 0.15 -> WARNING
    d. HAS_TABLES: has_tables == True -> WARNING (human review for numeric accuracy)
    e. SEAL_SIGNATURE: image-heavy page with very little text -> WARNING
    f. CONTRADICTORY_TEXT: both clean_text and ocr_text present and similarity < 0.70 -> REQUIRES_REVIEW
    g. OCR_UNAVAILABLE: is_scanned and (ocr_text is None or empty) -> REQUIRES_REVIEW
    """

    CONFIDENCE_THRESHOLD: float = 0.85
    MIN_CHAR_YIELD: int = 20
    MIXED_SCRIPT_RATIO_THRESHOLD: float = 0.15
    CONTRADICTORY_TEXT_THRESHOLD: float = 0.70
    SEAL_SIGNATURE_TEXT_THRESHOLD: int = 100

    SEAL_SIGNATURE_PATTERN: re.Pattern = re.compile(
        r"(?:"
        r"हस्ताक्षर|हस्ताक्षरित|ह०|"
        r"मुहर|मोहर|सील|"
        r"sd[\/\.\-]|s\/d|"
        r"signature|signed|seal|attested"
        r")",
        re.IGNORECASE,
    )

    @classmethod
    def evaluate(
        cls,
        page_number: int,
        clean_text: str,
        ocr_text: Optional[str] = None,
        text_confidence: float = 1.0,
        is_scanned: bool = False,
        has_tables: bool = False,
        detected_language: str = "hi",
        is_image_heavy: bool = False,
        image_count: int = 0,
        has_handwritten: bool = False,
        **kwargs: Any,
    ) -> List[QualityFlag]:
        """Evaluate a document page against all quality gate rules.

        Args:
            page_number: 1-indexed page number.
            clean_text: Digital extracted text from PDF native streams.
            ocr_text: Text produced by OCR engine, or None if OCR was not run.
            text_confidence: Extraction/OCR confidence score in range [0.0, 1.0].
            is_scanned: True if the page is a bitmap/scanned document page.
            has_tables: True if structured tables were detected on the page.
            detected_language: Primary language tag ('hi', 'en', 'bilingual').
            is_image_heavy: Optional flag indicating an image-heavy page layout.
            image_count: Optional count of embedded raster images on the page.
            has_handwritten: Optional flag indicating presence of handwritten notes.
            **kwargs: Extra parameters for forward compatibility (e.g., is_handwritten).

        Returns:
            List[QualityFlag]: List of quality flags triggered for the page.
        """
        flags: List[QualityFlag] = []

        clean_stripped = (clean_text or "").strip()
        clean_len = len(clean_stripped)
        ocr_stripped = (ocr_text or "").strip()
        has_ocr = bool(ocr_stripped)
        ocr_len = len(ocr_stripped)

        # -------------------------------------------------------------------
        # Rule a: LOW_CONFIDENCE
        # If text_confidence < CONFIDENCE_THRESHOLD -> REQUIRES_REVIEW
        # -------------------------------------------------------------------
        if text_confidence < cls.CONFIDENCE_THRESHOLD:
            flags.append(
                QualityFlag(
                    flag_type=FlagType.LOW_CONFIDENCE,
                    severity=Severity.REQUIRES_REVIEW,
                    message=(
                        f"Text extraction confidence {text_confidence:.2f} is below "
                        f"threshold {cls.CONFIDENCE_THRESHOLD:.2f}"
                    ),
                    page_number=page_number,
                )
            )

        # -------------------------------------------------------------------
        # Rule b: LOW_CHAR_YIELD
        # If len(clean_text.strip()) < MIN_CHAR_YIELD and not is_scanned -> WARNING;
        # if scanned and no OCR text -> REQUIRES_REVIEW
        # -------------------------------------------------------------------
        if not is_scanned:
            if clean_len < cls.MIN_CHAR_YIELD:
                flags.append(
                    QualityFlag(
                        flag_type=FlagType.LOW_CHAR_YIELD,
                        severity=Severity.WARNING,
                        message=(
                            f"Page character yield ({clean_len} characters) is below "
                            f"minimum threshold ({cls.MIN_CHAR_YIELD})"
                        ),
                        page_number=page_number,
                    )
                )
        else:
            if not has_ocr:
                flags.append(
                    QualityFlag(
                        flag_type=FlagType.LOW_CHAR_YIELD,
                        severity=Severity.REQUIRES_REVIEW,
                        message="Scanned page produced no OCR text output",
                        page_number=page_number,
                    )
                )
            elif ocr_len < cls.MIN_CHAR_YIELD:
                flags.append(
                    QualityFlag(
                        flag_type=FlagType.LOW_CHAR_YIELD,
                        severity=Severity.WARNING,
                        message=(
                            f"Scanned page OCR text character yield ({ocr_len} characters) "
                            f"is below minimum threshold ({cls.MIN_CHAR_YIELD})"
                        ),
                        page_number=page_number,
                    )
                )

        # -------------------------------------------------------------------
        # Rule c: MIXED_SCRIPT
        # If detected_language == 'bilingual' -> WARNING
        # Also triggers if mixed Devanagari/Latin script ratio >= threshold
        # -------------------------------------------------------------------
        is_bilingual = (
            (detected_language is not None and detected_language.lower() == "bilingual")
            or cls.is_mixed_script(clean_stripped, cls.MIXED_SCRIPT_RATIO_THRESHOLD)
            or (has_ocr and cls.is_mixed_script(ocr_stripped, cls.MIXED_SCRIPT_RATIO_THRESHOLD))
        )
        if is_bilingual:
            flags.append(
                QualityFlag(
                    flag_type=FlagType.MIXED_SCRIPT,
                    severity=Severity.WARNING,
                    message=(
                        f"Page contains mixed script (bilingual Hindi/English content "
                        f"exceeding ratio threshold {cls.MIXED_SCRIPT_RATIO_THRESHOLD:.2f})"
                    ),
                    page_number=page_number,
                )
            )

        # -------------------------------------------------------------------
        # Rule d: HAS_TABLES
        # If has_tables -> WARNING (tables need human review for numeric accuracy)
        # -------------------------------------------------------------------
        if has_tables:
            flags.append(
                QualityFlag(
                    flag_type=FlagType.HAS_TABLES,
                    severity=Severity.WARNING,
                    message=(
                        "Page contains structured tables requiring human verification "
                        "for numeric and tabular accuracy"
                    ),
                    page_number=page_number,
                )
            )

        # -------------------------------------------------------------------
        # Rule e: SEAL_SIGNATURE
        # Detect via heuristic: image-heavy page with very little text -> WARNING
        # -------------------------------------------------------------------
        effective_text = clean_stripped or ocr_stripped
        if cls.is_seal_or_signature_page(
            text=effective_text,
            is_scanned=is_scanned,
            is_image_heavy=is_image_heavy,
            image_count=image_count,
        ):
            flags.append(
                QualityFlag(
                    flag_type=FlagType.SEAL_SIGNATURE,
                    severity=Severity.WARNING,
                    message=(
                        "Page detected as containing seals, rubber stamps, or signature "
                        "block with minimal body text"
                    ),
                    page_number=page_number,
                )
            )

        # -------------------------------------------------------------------
        # Rule f: CONTRADICTORY_TEXT
        # If both clean_text and ocr_text are non-empty and their
        # similarity ratio < 0.70 -> REQUIRES_REVIEW
        # -------------------------------------------------------------------
        if clean_stripped and ocr_stripped:
            similarity = cls.compute_similarity(clean_stripped, ocr_stripped)
            if similarity < cls.CONTRADICTORY_TEXT_THRESHOLD:
                flags.append(
                    QualityFlag(
                        flag_type=FlagType.CONTRADICTORY_TEXT,
                        severity=Severity.REQUIRES_REVIEW,
                        message=(
                            f"Digital text and OCR text differ significantly "
                            f"(similarity ratio {similarity:.2f} < threshold "
                            f"{cls.CONTRADICTORY_TEXT_THRESHOLD:.2f})"
                        ),
                        page_number=page_number,
                    )
                )

        # -------------------------------------------------------------------
        # Rule g: OCR_UNAVAILABLE
        # If is_scanned and (ocr_text is None or ocr_text == '') -> REQUIRES_REVIEW
        # -------------------------------------------------------------------
        if is_scanned and (ocr_text is None or ocr_text == ""):
            flags.append(
                QualityFlag(
                    flag_type=FlagType.OCR_UNAVAILABLE,
                    severity=Severity.REQUIRES_REVIEW,
                    message="Document page is scanned but OCR text is unavailable or empty",
                    page_number=page_number,
                )
            )

        # -------------------------------------------------------------------
        # HANDWRITTEN Check (Explicit parameter or keyword detection)
        # -------------------------------------------------------------------
        is_handwritten = has_handwritten or kwargs.get("is_handwritten", False)
        if is_handwritten:
            flags.append(
                QualityFlag(
                    flag_type=FlagType.HANDWRITTEN,
                    severity=Severity.REQUIRES_REVIEW,
                    message="Page contains detected handwritten text or annotations requiring human review",
                    page_number=page_number,
                )
            )

        return flags

    # -----------------------------------------------------------------------
    # Helper Methods
    # -----------------------------------------------------------------------

    @staticmethod
    def compute_similarity(text1: str, text2: str) -> float:
        """Compute character-level similarity ratio between two strings using difflib.SequenceMatcher.

        Whitespace runs are collapsed to ensure line wrapping and spacing differences
        do not artificially penalize matching characters.

        Args:
            text1: First text snippet.
            text2: Second text snippet.

        Returns:
            float: Similarity ratio in range [0.0, 1.0].
        """
        if not text1 and not text2:
            return 1.0
        if not text1 or not text2:
            return 0.0

        normalized1 = " ".join(text1.split())
        normalized2 = " ".join(text2.split())

        if not normalized1 and not normalized2:
            return 1.0
        if not normalized1 or not normalized2:
            return 0.0

        return SequenceMatcher(None, normalized1, normalized2).ratio()

    @classmethod
    def is_mixed_script(
        cls,
        text: str,
        threshold: float = MIXED_SCRIPT_RATIO_THRESHOLD,
    ) -> bool:
        """Determine whether text contains a significant mix of Devanagari and Latin scripts.

        Args:
            text: Input string to evaluate.
            threshold: Minimum proportion of minority script required to qualify as mixed.

        Returns:
            bool: True if minority script ratio meets or exceeds threshold.
        """
        if not text or not text.strip():
            return False

        devanagari_chars = sum(1 for c in text if "\u0900" <= c <= "\u097f")
        latin_chars = sum(1 for c in text if ("a" <= c <= "z") or ("A" <= c <= "Z"))
        total_letters = devanagari_chars + latin_chars

        if total_letters == 0:
            return False

        dev_ratio = devanagari_chars / total_letters
        lat_ratio = latin_chars / total_letters

        return (
            devanagari_chars >= 5
            and latin_chars >= 5
            and min(dev_ratio, lat_ratio) >= threshold
        )

    @classmethod
    def is_seal_or_signature_page(
        cls,
        text: str,
        is_scanned: bool = False,
        is_image_heavy: bool = False,
        image_count: int = 0,
    ) -> bool:
        """Evaluate heuristic for pages containing seals, rubber stamps, or signature blocks.

        Heuristic criteria:
        1. Page has minimal body text (< SEAL_SIGNATURE_TEXT_THRESHOLD).
        2. AND either:
           - is_image_heavy is True or image_count >= 2
           - image_count == 1 and character count < MIN_CHAR_YIELD
           - page is scanned or contains images AND contains signature/seal keywords

        Args:
            text: Text content of the page.
            is_scanned: Scanned document page indicator.
            is_image_heavy: Flag for image-heavy layout.
            image_count: Number of images present on the page.

        Returns:
            bool: True if the page satisfies seal/signature heuristic criteria.
        """
        clean = (text or "").strip()
        char_count = len(clean)

        if char_count >= cls.SEAL_SIGNATURE_TEXT_THRESHOLD:
            return False

        # Image-heavy condition: explicit flag or multiple images
        if is_image_heavy or image_count >= 2:
            return True

        # Single image with very low text count
        if image_count == 1 and char_count < cls.MIN_CHAR_YIELD:
            return True

        # Signature or seal keywords on scanned / image-bearing pages
        has_cue = bool(cls.SEAL_SIGNATURE_PATTERN.search(clean))
        if (is_scanned or image_count > 0 or is_image_heavy) and has_cue:
            return True

        return False


# ---------------------------------------------------------------------------
# Status Determination Function
# ---------------------------------------------------------------------------

def determine_review_status(flags: List[QualityFlag]) -> str:
    """Determine document or page review status based on quality flags.

    Status determination rules:
    - If any flag has severity 'REQUIRES_REVIEW' -> returns 'FLAGGED'
    - If flags exist but all have severity 'WARNING' -> returns 'AUTO_APPROVED'
    - If no flags -> returns 'AUTO_APPROVED'

    Args:
        flags: Collection of QualityFlag instances for the page or document.

    Returns:
        str: 'FLAGGED' if any review is required, otherwise 'AUTO_APPROVED'.
    """
    for flag in flags:
        if flag.severity == Severity.REQUIRES_REVIEW:
            return ReviewStatus.FLAGGED
    return ReviewStatus.AUTO_APPROVED
