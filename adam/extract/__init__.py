"""Text extraction, table parsing, metadata attribution, and precedent tracking."""

from adam.extract.pdf import PdfExtractor, ExtractedPage
from adam.extract.precedents import PrecedentCitationParser, ParsedCitation
from adam.extract.metadata import AdministrativeMetadataExtractor, ExtractedMetadata
from adam.extract.pipeline import DocumentExtractionPipeline
from adam.extract.blocks import (
    BlockExtractor,
    ExtractedBlock,
    resolve_block_citation,
    get_approved_blocks,
)
from adam.extract.ocr import (
    OcrResult,
    BaseOcrEngine,
    TesseractOcrEngine,
    PaddleOcrEngine,
    NullOcrEngine,
    get_ocr_engine,
)

from adam.extract.quality import (
    QualityFlag,
    PageQualityGate,
    determine_review_status,
    FlagType,
    Severity,
    ReviewStatus,
)
from adam.extract.metrics import (
    character_error_rate,
    exact_match_score,
    report_extraction_quality,
    PageQualityScore,
    ExtractionQualityReport,
    CharacterErrorRateMetric,
    ExactMatchMetric,
)
from adam.extract.preprocess import (
    render_page_image,
    detect_rotation,
    preprocess_for_ocr,
    PageImageMetadata,
    StandardOCRPreprocessor,
)

__all__ = [
    "PdfExtractor",
    "ExtractedPage",
    "PrecedentCitationParser",
    "ParsedCitation",
    "AdministrativeMetadataExtractor",
    "ExtractedMetadata",
    "DocumentExtractionPipeline",
    "BlockExtractor",
    "ExtractedBlock",
    "resolve_block_citation",
    "get_approved_blocks",
    "OcrResult",
    "BaseOcrEngine",
    "TesseractOcrEngine",
    "PaddleOcrEngine",
    "NullOcrEngine",
    "get_ocr_engine",
    "QualityFlag",
    "PageQualityGate",
    "determine_review_status",
    "FlagType",
    "Severity",
    "ReviewStatus",
    "character_error_rate",
    "exact_match_score",
    "report_extraction_quality",
    "PageQualityScore",
    "ExtractionQualityReport",
    "CharacterErrorRateMetric",
    "ExactMatchMetric",
    "render_page_image",
    "detect_rotation",
    "preprocess_for_ocr",
    "PageImageMetadata",
    "StandardOCRPreprocessor",
]

