"""Block-level text extraction, spatial bounding box resolution, and block classification."""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

import fitz  # PyMuPDF

# Semantic block type constants
BLOCK_TYPE_PARAGRAPH = "PARAGRAPH"
BLOCK_TYPE_HEADING = "HEADING"
BLOCK_TYPE_LIST_ITEM = "LIST_ITEM"
BLOCK_TYPE_IMAGE = "IMAGE"
BLOCK_TYPE_TABLE = "TABLE"

VALID_BLOCK_TYPES = {
    BLOCK_TYPE_PARAGRAPH,
    BLOCK_TYPE_HEADING,
    BLOCK_TYPE_LIST_ITEM,
    BLOCK_TYPE_IMAGE,
    BLOCK_TYPE_TABLE,
}


@dataclass
class ExtractedBlock:
    """Represents a structural content block extracted from a document page.

    Attributes:
        block_type: Semantic classification of the block. Must be one of
            'PARAGRAPH', 'HEADING', 'LIST_ITEM', 'IMAGE', or 'TABLE'.
        text: Text content of the block (empty string for IMAGE blocks).
        bbox: Bounding box coordinates [x0, y0, x1, y1] in points.
        reading_order: Sequential 0-indexed reading order on the page.
        confidence: Confidence score for extraction (1.0 for digital text,
            lower for others).
    """

    block_type: str
    text: str
    bbox: List[float] = field(default_factory=list)
    reading_order: int = 0
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize extracted block into a dictionary representation."""
        return {
            "block_type": self.block_type,
            "text": self.text,
            "bbox": list(self.bbox),
            "reading_order": self.reading_order,
            "confidence": self.confidence,
        }


class BlockExtractor:
    """Extracts layout blocks with bounding boxes and classifies them semantically."""

    HEADING_FONT_SIZE_THRESHOLD: float = 14.0  # Points; text with avg font >= this is a heading
    DEFAULT_FONT_SIZE: float = 12.0

    BLOCK_TYPE_PARAGRAPH: str = BLOCK_TYPE_PARAGRAPH
    BLOCK_TYPE_HEADING: str = BLOCK_TYPE_HEADING
    BLOCK_TYPE_LIST_ITEM: str = BLOCK_TYPE_LIST_ITEM
    BLOCK_TYPE_IMAGE: str = BLOCK_TYPE_IMAGE
    BLOCK_TYPE_TABLE: str = BLOCK_TYPE_TABLE

    # Matches common administrative, legal, and standard bullet and numbering patterns:
    # - Bullet symbols: •, ▪, ▫, ·, etc.
    # - Dashes / asterisks: -, *, –, — (followed by whitespace or line end)
    # - Arabic / Devanagari numerals: 1., 1), (1), 1-, १., १), (१)
    # - Roman numerals: (i), (ii), (iv), i., i), (I), I.
    # - Latin alphabetic lists: (a), (b), a., a), (A), A.
    # - Devanagari character lists: (क), (ख), क., क), etc.
    LIST_ITEM_PATTERN = re.compile(
        r"^(?:"
        r"[•▪▫\u2022\u2023\u25e6\u2043\u2219\u00b7·](?:\s*|$)"
        r"|"
        r"[\-\*–—](?:\s+|$)"
        r"|"
        r"(?:(?:\d+|[\u0966-\u096f]+)\.(?!\d))(?:\s*|$)"
        r"|"
        r"(?:(?:\d+|[\u0966-\u096f]+)[\)\-]|\((?:\d+|[\u0966-\u096f]+)\))(?:\s*|$)"
        r"|"
        r"(?:\([ivxlcdmIVXLCDM]+\)|(?:[ivxlcdmIVXLCDM]+)[\.\)])(?:\s*|$)"
        r"|"
        r"(?:\([a-zA-Z]\)|[a-zA-Z][\.\)])(?:\s*|$)"
        r"|"
        r"(?:\([\u0904-\u0939]\)|[\u0904-\u0939][\.\)])(?:\s*|$)"
        r")",
        re.UNICODE,
    )

    @classmethod
    def extract_blocks(cls, page: fitz.Page) -> List[ExtractedBlock]:
        """Extract block-level text and layout bounding boxes from a PyMuPDF page.

        Uses page.get_text('dict') to inspect layout blocks. Digital text blocks
        are classified as HEADING, LIST_ITEM, or PARAGRAPH based on average font
        size and bullet patterns. Image blocks are classified as IMAGE. Blocks
        are assigned sequential 0-indexed reading orders and returned sorted by
        reading_order.

        Args:
            page: PyMuPDF Page instance to extract blocks from.

        Returns:
            List of ExtractedBlock instances sorted in sequential reading order.
        """
        if page is None:
            return []

        try:
            page_dict = page.get_text("dict")
        except Exception:
            return []

        if not isinstance(page_dict, dict):
            return []

        raw_blocks = page_dict.get("blocks")
        if not isinstance(raw_blocks, list) or not raw_blocks:
            return []

        extracted_blocks: List[ExtractedBlock] = []

        for block in raw_blocks:
            if not isinstance(block, dict):
                continue

            # Safely extract bounding box as list of 4 float coordinates [x0, y0, x1, y1]
            raw_bbox = block.get("bbox")
            if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
                try:
                    bbox = [
                        float(raw_bbox[0]),
                        float(raw_bbox[1]),
                        float(raw_bbox[2]),
                        float(raw_bbox[3]),
                    ]
                except (ValueError, TypeError):
                    bbox = [0.0, 0.0, 0.0, 0.0]
            else:
                bbox = [0.0, 0.0, 0.0, 0.0]

            block_type_code = block.get("type", 0)

            if block_type_code == 1:
                # Image block
                extracted_blocks.append(
                    ExtractedBlock(
                        block_type=cls.BLOCK_TYPE_IMAGE,
                        text="",
                        bbox=bbox,
                        reading_order=len(extracted_blocks),
                        confidence=0.0,
                    )
                )
            else:
                # Text block (type == 0 or fallback)
                lines = block.get("lines")
                line_texts: List[str] = []
                if isinstance(lines, list):
                    for line in lines:
                        if isinstance(line, dict):
                            spans = line.get("spans")
                            if isinstance(spans, list):
                                line_str = "".join(
                                    str(span.get("text", ""))
                                    for span in spans
                                    if isinstance(span, dict) and span.get("text") is not None
                                )
                                line_texts.append(line_str)

                text = "\n".join(line_texts).strip()

                avg_font_size = cls._average_font_size(block)

                # Classify block type
                if avg_font_size >= cls.HEADING_FONT_SIZE_THRESHOLD:
                    block_type = cls.BLOCK_TYPE_HEADING
                elif cls._is_list_item(text):
                    block_type = cls.BLOCK_TYPE_LIST_ITEM
                else:
                    block_type = cls.BLOCK_TYPE_PARAGRAPH

                extracted_blocks.append(
                    ExtractedBlock(
                        block_type=block_type,
                        text=text,
                        bbox=bbox,
                        reading_order=len(extracted_blocks),
                        confidence=1.0,
                    )
                )

        # Sort blocks by sequential reading order
        extracted_blocks.sort(key=lambda b: b.reading_order)
        return extracted_blocks

    @classmethod
    def _average_font_size(cls, block_dict: dict) -> float:
        """Calculate the average font size across all spans in a block dictionary.

        Traverses block_dict['lines'] -> line['spans'] -> span['size'].

        Args:
            block_dict: PyMuPDF block dictionary containing line and span structures.

        Returns:
            Average font size across spans, or 12.0 if no spans are found.
        """
        if not isinstance(block_dict, dict):
            return cls.DEFAULT_FONT_SIZE

        lines = block_dict.get("lines")
        if not isinstance(lines, list) or not lines:
            return cls.DEFAULT_FONT_SIZE

        font_sizes: List[float] = []
        for line in lines:
            if not isinstance(line, dict):
                continue
            spans = line.get("spans")
            if not isinstance(spans, list):
                continue
            for span in spans:
                if not isinstance(span, dict):
                    continue
                size = span.get("size")
                if size is not None:
                    try:
                        font_sizes.append(float(size))
                    except (ValueError, TypeError):
                        continue

        if not font_sizes:
            return cls.DEFAULT_FONT_SIZE

        return sum(font_sizes) / len(font_sizes)

    @classmethod
    def _is_list_item(cls, text: str) -> bool:
        """Check if text starts with a bullet or numbered list pattern.

        Recognizes symbols (•, -, *), Arabic and Devanagari numbering (1., (1)),
        Roman numerals ((i), (ii)), and Devanagari letters ((क), क.).

        Args:
            text: Text content of the block.

        Returns:
            True if text begins with a recognized list item marker, False otherwise.
        """
        if not text:
            return False
        return bool(cls.LIST_ITEM_PATTERN.match(text.strip()))


def resolve_block_citation(session, block_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a block ID to its original document, version, page, and bounding box coordinates.

    Satisfies Acceptance Criteria 3:
        'Citation links from chunks resolve to original version, page and highlighted coordinates.'

    Args:
        session: SQLAlchemy session.
        block_id: Primary key of the TextBlock.

    Returns:
        Dictionary with full coordinate and provenance resolution, or None if not found:
        - block_id: str
        - document_id: str
        - version_id: str
        - page_id: str
        - page_number: int
        - image_key: Optional[str]
        - bbox: List[float] [x0, y0, x1, y1]
        - block_type: str
        - text: str
        - reading_order: int
        - confidence: float
        - review_status: str
        - is_approved: bool
    """
    from adam.db.models import TextBlock, DocumentPage, DocumentVersion
    from adam.vocabularies import ReviewStatus

    block = session.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        return None

    page = block.page
    version = page.version if page else None
    document_id = version.document_id if version else None

    approved_statuses = {
        ReviewStatus.AUTO_APPROVED.value,
        ReviewStatus.REVIEWED.value,
        ReviewStatus.CORRECTED.value,
    }

    return {
        "block_id": block.id,
        "document_id": document_id,
        "version_id": page.version_id if page else None,
        "page_id": page.id if page else None,
        "page_number": page.page_number if page else None,
        "image_key": page.image_key if page else None,
        "bbox": list(block.bbox) if block.bbox else None,
        "block_type": block.block_type,
        "text": block.text,
        "reading_order": block.reading_order,
        "confidence": block.confidence,
        "review_status": page.review_status if page else None,
        "is_approved": (page.review_status in approved_statuses) if page else False,
    }


def get_approved_blocks(
    session,
    version_id: Optional[str] = None,
    document_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve approved content blocks for downstream consumption (e.g., Module 03 chunking/indexing).

    Satisfies Module 02 -> Module 03 dependency:
        'Module 03 consumes approved page blocks only.'

    Only blocks from pages with review_status in ('AUTO_APPROVED', 'REVIEWED', 'CORRECTED')
    and documents with ACTIVE lifecycle status are returned.

    Args:
        session: SQLAlchemy session.
        version_id: Optional filter for a specific document version.
        document_id: Optional filter for a specific document.

    Returns:
        List of resolved block metadata dictionaries ordered by page_number and reading_order.
    """
    from adam.db.models import TextBlock, DocumentPage, DocumentVersion, Document
    from adam.vocabularies import ReviewStatus, LifecycleStatus

    approved_statuses = [
        ReviewStatus.AUTO_APPROVED.value,
        ReviewStatus.REVIEWED.value,
        ReviewStatus.CORRECTED.value,
    ]

    query = (
        session.query(TextBlock, DocumentPage, DocumentVersion)
        .join(DocumentPage, TextBlock.page_id == DocumentPage.id)
        .join(DocumentVersion, DocumentPage.version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .filter(
            Document.lifecycle_status == LifecycleStatus.ACTIVE.value,
            DocumentPage.review_status.in_(approved_statuses),
        )
    )

    if version_id:
        query = query.filter(DocumentVersion.id == version_id)
    if document_id:
        query = query.filter(Document.id == document_id)

    query = query.order_by(DocumentPage.page_number, TextBlock.reading_order)

    results = []
    for blk, pg, ver in query.all():
        results.append({
            "block_id": blk.id,
            "document_id": ver.document_id,
            "version_id": ver.id,
            "page_id": pg.id,
            "page_number": pg.page_number,
            "image_key": pg.image_key,
            "bbox": list(blk.bbox) if blk.bbox else None,
            "block_type": blk.block_type,
            "text": blk.text,
            "reading_order": blk.reading_order,
            "confidence": blk.confidence,
            "review_status": pg.review_status,
            "is_approved": True,
        })

    return results

