"""Unit tests for the document extraction quality gate evaluation system."""

import pytest

from adam.extract.quality import (
    QualityFlag,
    PageQualityGate,
    determine_review_status,
    FlagType,
    Severity,
    ReviewStatus,
    FLAG_LOW_CONFIDENCE,
    FLAG_LOW_CHAR_YIELD,
    FLAG_MIXED_SCRIPT,
    FLAG_HAS_TABLES,
    FLAG_SEAL_SIGNATURE,
    FLAG_HANDWRITTEN,
    FLAG_CONTRADICTORY_TEXT,
    FLAG_OCR_UNAVAILABLE,
    SEVERITY_WARNING,
    SEVERITY_REQUIRES_REVIEW,
    REVIEW_STATUS_FLAGGED,
    REVIEW_STATUS_AUTO_APPROVED,
)


def test_quality_flag_dataclass():
    """Test QualityFlag instantiation and attribute access."""
    flag = QualityFlag(
        flag_type=FlagType.LOW_CONFIDENCE,
        severity=Severity.REQUIRES_REVIEW,
        message="Confidence score is low",
        page_number=1,
    )
    assert flag.flag_type == "LOW_CONFIDENCE"
    assert flag.severity == "REQUIRES_REVIEW"
    assert flag.message == "Confidence score is low"
    assert flag.page_number == 1


def test_page_quality_gate_constants():
    """Verify standard thresholds on PageQualityGate."""
    assert PageQualityGate.CONFIDENCE_THRESHOLD == 0.85
    assert PageQualityGate.MIN_CHAR_YIELD == 20
    assert PageQualityGate.MIXED_SCRIPT_RATIO_THRESHOLD == 0.15
    assert PageQualityGate.CONTRADICTORY_TEXT_THRESHOLD == 0.70


def test_rule_a_low_confidence():
    """Test Rule a: text_confidence < 0.85 triggers LOW_CONFIDENCE with REQUIRES_REVIEW."""
    # Below threshold
    flags_low = PageQualityGate.evaluate(
        page_number=1,
        clean_text="उत्तराखंड शासन वित्त विभाग का शासनादेश संख्या 100।",
        ocr_text=None,
        text_confidence=0.84,
        is_scanned=False,
        has_tables=False,
        detected_language="hi",
    )
    assert any(f.flag_type == FlagType.LOW_CONFIDENCE and f.severity == Severity.REQUIRES_REVIEW for f in flags_low)

    # At or above threshold
    flags_ok = PageQualityGate.evaluate(
        page_number=1,
        clean_text="उत्तराखंड शासन वित्त विभाग का शासनादेश संख्या 100।",
        ocr_text=None,
        text_confidence=0.85,
        is_scanned=False,
        has_tables=False,
        detected_language="hi",
    )
    assert not any(f.flag_type == FlagType.LOW_CONFIDENCE for f in flags_ok)


def test_rule_b_low_char_yield_digital():
    """Test Rule b: Digital text with < MIN_CHAR_YIELD triggers LOW_CHAR_YIELD as WARNING."""
    # Under 20 chars
    flags = PageQualityGate.evaluate(
        page_number=1,
        clean_text="Short text",  # 10 chars
        ocr_text=None,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=False,
        detected_language="en",
    )
    flag_types = [f.flag_type for f in flags]
    assert FlagType.LOW_CHAR_YIELD in flag_types
    yield_flag = next(f for f in flags if f.flag_type == FlagType.LOW_CHAR_YIELD)
    assert yield_flag.severity == Severity.WARNING


def test_rule_b_and_g_scanned_without_ocr():
    """Test Rules b & g: Scanned page without OCR text triggers LOW_CHAR_YIELD & OCR_UNAVAILABLE as REQUIRES_REVIEW."""
    flags = PageQualityGate.evaluate(
        page_number=2,
        clean_text="",
        ocr_text=None,
        text_confidence=0.90,
        is_scanned=True,
        has_tables=False,
        detected_language="hi",
    )
    flag_dict = {f.flag_type: f.severity for f in flags}
    assert FlagType.LOW_CHAR_YIELD in flag_dict
    assert flag_dict[FlagType.LOW_CHAR_YIELD] == Severity.REQUIRES_REVIEW
    assert FlagType.OCR_UNAVAILABLE in flag_dict
    assert flag_dict[FlagType.OCR_UNAVAILABLE] == Severity.REQUIRES_REVIEW

    # Empty string ocr_text
    flags_empty = PageQualityGate.evaluate(
        page_number=2,
        clean_text="",
        ocr_text="",
        text_confidence=0.90,
        is_scanned=True,
        has_tables=False,
        detected_language="hi",
    )
    empty_dict = {f.flag_type: f.severity for f in flags_empty}
    assert FlagType.OCR_UNAVAILABLE in empty_dict
    assert empty_dict[FlagType.OCR_UNAVAILABLE] == Severity.REQUIRES_REVIEW


def test_rule_c_mixed_script():
    """Test Rule c: Bilingual script triggers MIXED_SCRIPT with WARNING."""
    # Via detected_language parameter
    flags_lang = PageQualityGate.evaluate(
        page_number=1,
        clean_text="Finance Department Notification dated 2024",
        ocr_text=None,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=False,
        detected_language="bilingual",
    )
    assert any(f.flag_type == FlagType.MIXED_SCRIPT and f.severity == Severity.WARNING for f in flags_lang)

    # Via text script ratio heuristic
    mixed_text = "उत्तराखंड शासन Finance Department Government of Uttarakhand"
    flags_heuristic = PageQualityGate.evaluate(
        page_number=1,
        clean_text=mixed_text,
        ocr_text=None,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=False,
        detected_language="hi",
    )
    assert any(f.flag_type == FlagType.MIXED_SCRIPT and f.severity == Severity.WARNING for f in flags_heuristic)

    # Monolingual Hindi should not trigger MIXED_SCRIPT
    hindi_text = "उत्तराखंड शासन द्वारा जारी महत्वपूर्ण शासनादेश एवं सेवा नियमावली।"
    flags_hi = PageQualityGate.evaluate(
        page_number=1,
        clean_text=hindi_text,
        ocr_text=None,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=False,
        detected_language="hi",
    )
    assert not any(f.flag_type == FlagType.MIXED_SCRIPT for f in flags_hi)


def test_rule_d_has_tables():
    """Test Rule d: Page with tables triggers HAS_TABLES with WARNING."""
    flags = PageQualityGate.evaluate(
        page_number=3,
        clean_text="Detailed pay scale matrix for government employees.",
        ocr_text=None,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=True,
        detected_language="en",
    )
    assert any(f.flag_type == FlagType.HAS_TABLES and f.severity == Severity.WARNING for f in flags)

    flags_no_tables = PageQualityGate.evaluate(
        page_number=3,
        clean_text="Detailed pay scale matrix for government employees.",
        ocr_text=None,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=False,
        detected_language="en",
    )
    assert not any(f.flag_type == FlagType.HAS_TABLES for f in flags_no_tables)


def test_rule_e_seal_signature_heuristic():
    """Test Rule e: Image-heavy page with minimal text triggers SEAL_SIGNATURE with WARNING."""
    # Image-heavy page with little text
    flags = PageQualityGate.evaluate(
        page_number=4,
        clean_text="Sd/- Secretary (Finance)",
        ocr_text=None,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=False,
        detected_language="en",
        is_image_heavy=True,
    )
    assert any(f.flag_type == FlagType.SEAL_SIGNATURE and f.severity == Severity.WARNING for f in flags)

    # Multiple images on page with little text
    flags_img = PageQualityGate.evaluate(
        page_number=4,
        clean_text="Approved by Director",
        ocr_text=None,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=False,
        detected_language="en",
        image_count=2,
    )
    assert any(f.flag_type == FlagType.SEAL_SIGNATURE and f.severity == Severity.WARNING for f in flags_img)

    # Scanned page with signature keyword
    flags_sig = PageQualityGate.evaluate(
        page_number=4,
        clean_text="हस्ताक्षर अपर सचिव",
        ocr_text="हस्ताक्षर अपर सचिव",
        text_confidence=0.95,
        is_scanned=True,
        has_tables=False,
        detected_language="hi",
    )
    assert any(f.flag_type == FlagType.SEAL_SIGNATURE and f.severity == Severity.WARNING for f in flags_sig)


def test_rule_f_contradictory_text():
    """Test Rule f: Divergent clean_text and ocr_text triggers CONTRADICTORY_TEXT with REQUIRES_REVIEW."""
    clean = "Uttarakhand Government Finance Department Notification regarding Dearness Allowance"
    ocr_mismatch = "Random noisy text about agricultural subsidies and irrigation projects"

    flags = PageQualityGate.evaluate(
        page_number=1,
        clean_text=clean,
        ocr_text=ocr_mismatch,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=False,
        detected_language="en",
    )
    assert any(f.flag_type == FlagType.CONTRADICTORY_TEXT and f.severity == Severity.REQUIRES_REVIEW for f in flags)

    # Matching clean and ocr text (above 0.70 ratio)
    ocr_matching = "Uttarakhand Government Finance Dept Notification regarding Dearness Allowance"
    flags_ok = PageQualityGate.evaluate(
        page_number=1,
        clean_text=clean,
        ocr_text=ocr_matching,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=False,
        detected_language="en",
    )
    assert not any(f.flag_type == FlagType.CONTRADICTORY_TEXT for f in flags_ok)


def test_handwritten_flag():
    """Test HANDWRITTEN flag triggers REQUIRES_REVIEW when handwritten notes are detected."""
    flags = PageQualityGate.evaluate(
        page_number=1,
        clean_text="Government Order with marginal hand notes on the left column.",
        ocr_text=None,
        text_confidence=0.95,
        is_scanned=False,
        has_tables=False,
        detected_language="en",
        has_handwritten=True,
    )
    assert any(f.flag_type == FlagType.HANDWRITTEN and f.severity == Severity.REQUIRES_REVIEW for f in flags)


def test_determine_review_status():
    """Test determine_review_status logic:
    - Any REQUIRES_REVIEW -> 'FLAGGED'
    - Only WARNING or empty -> 'AUTO_APPROVED'
    """
    # 1. No flags -> AUTO_APPROVED
    assert determine_review_status([]) == ReviewStatus.AUTO_APPROVED

    # 2. Only WARNING flags -> AUTO_APPROVED
    warning_flags = [
        QualityFlag(FlagType.HAS_TABLES, Severity.WARNING, "Tables present", 1),
        QualityFlag(FlagType.MIXED_SCRIPT, Severity.WARNING, "Bilingual", 1),
        QualityFlag(FlagType.SEAL_SIGNATURE, Severity.WARNING, "Seal page", 2),
    ]
    assert determine_review_status(warning_flags) == ReviewStatus.AUTO_APPROVED

    # 3. Any REQUIRES_REVIEW -> FLAGGED
    review_flags = [
        QualityFlag(FlagType.LOW_CONFIDENCE, Severity.REQUIRES_REVIEW, "Low conf", 1),
    ]
    assert determine_review_status(review_flags) == ReviewStatus.FLAGGED

    # 4. Mixed WARNING and REQUIRES_REVIEW -> FLAGGED
    mixed_flags = [
        QualityFlag(FlagType.HAS_TABLES, Severity.WARNING, "Tables", 1),
        QualityFlag(FlagType.CONTRADICTORY_TEXT, Severity.REQUIRES_REVIEW, "Mismatch", 1),
    ]
    assert determine_review_status(mixed_flags) == ReviewStatus.FLAGGED


def test_sequence_matcher_similarity():
    """Test compute_similarity character-level comparison using SequenceMatcher."""
    # Exact match
    assert PageQualityGate.compute_similarity("Hello World", "Hello World") == 1.0

    # Whitespace normalization
    assert PageQualityGate.compute_similarity("Hello   World\n", "Hello World") == 1.0

    # Completely different
    sim = PageQualityGate.compute_similarity("abcdef", "uvwxyz")
    assert sim == 0.0

    # Partial similarity
    sim_partial = PageQualityGate.compute_similarity("Finance Department", "Finance Dept")
    assert 0.70 < sim_partial < 1.0
