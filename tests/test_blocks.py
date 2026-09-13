"""Tests for block-level text extraction with bounding boxes and layout classification."""

from unittest.mock import MagicMock
import fitz
import pytest

from adam.extract.blocks import (
    BlockExtractor,
    ExtractedBlock,
    BLOCK_TYPE_PARAGRAPH,
    BLOCK_TYPE_HEADING,
    BLOCK_TYPE_LIST_ITEM,
    BLOCK_TYPE_IMAGE,
    BLOCK_TYPE_TABLE,
)


def test_extracted_block_dataclass_fields():
    """Verify ExtractedBlock has required fields and proper defaults."""
    block = ExtractedBlock(
        block_type=BLOCK_TYPE_PARAGRAPH,
        text="Sample paragraph text.",
        bbox=[10.0, 20.0, 200.0, 50.0],
        reading_order=0,
        confidence=1.0,
    )
    assert block.block_type == "PARAGRAPH"
    assert block.text == "Sample paragraph text."
    assert block.bbox == [10.0, 20.0, 200.0, 50.0]
    assert isinstance(block.bbox, list)
    assert block.reading_order == 0
    assert block.confidence == 1.0

    d = block.to_dict()
    assert d["block_type"] == "PARAGRAPH"
    assert d["text"] == "Sample paragraph text."
    assert d["bbox"] == [10.0, 20.0, 200.0, 50.0]
    assert d["reading_order"] == 0
    assert d["confidence"] == 1.0


def test_extracted_block_table_type():
    """Ensure TABLE is a valid block type."""
    block = ExtractedBlock(
        block_type=BLOCK_TYPE_TABLE,
        text="Col1 | Col2",
        bbox=[0.0, 0.0, 100.0, 100.0],
        reading_order=1,
        confidence=0.9,
    )
    assert block.block_type == "TABLE"


def test_average_font_size_standard():
    """Verify average font size calculation across lines and spans."""
    block_dict = {
        "type": 0,
        "lines": [
            {
                "spans": [
                    {"size": 14.0, "text": "Part A "},
                    {"size": 16.0, "text": "Part B"},
                ]
            },
            {
                "spans": [
                    {"size": 15.0, "text": "Part C"},
                ]
            },
        ],
    }
    avg = BlockExtractor._average_font_size(block_dict)
    assert avg == 15.0


def test_average_font_size_empty_or_missing():
    """Verify fallback to 12.0 when spans are empty, invalid, or missing."""
    assert BlockExtractor._average_font_size({}) == 12.0
    assert BlockExtractor._average_font_size({"lines": []}) == 12.0
    assert BlockExtractor._average_font_size({"lines": [{"spans": []}]}) == 12.0
    assert BlockExtractor._average_font_size({"lines": [{"spans": [{"size": None}]}]}) == 12.0
    assert BlockExtractor._average_font_size({"lines": [{"spans": [{"size": "invalid"}]}]}) == 12.0
    assert BlockExtractor._average_font_size(None) == 12.0


@pytest.mark.parametrize(
    "bullet_text",
    [
        "• First bullet item",
        "· Middle dot bullet",
        "- Dash bullet item",
        "* Asterisk bullet item",
        "1. Arabic numbered item",
        "1) Arabic numbered with parenthesis",
        "(1) Enclosed arabic numeral",
        "(i) Lowercase roman numeral",
        "(ii) Lowercase roman numeral 2",
        "(iv) Lowercase roman numeral 4",
        "(I) Uppercase roman numeral",
        "i. Roman numeral with period",
        "(a) Alphabetic item",
        "a. Alphabetic item with period",
        "(क) Devanagari item",
        "(ख) Devanagari item 2",
        "क. Devanagari item with period",
        "१. Devanagari numeral item",
        "(१) Devanagari numeral in parenthesis",
    ],
)
def test_list_item_pattern_matches(bullet_text: str):
    """Verify list item bullet and numbering patterns are correctly detected."""
    assert BlockExtractor._is_list_item(bullet_text) is True


@pytest.mark.parametrize(
    "non_bullet_text",
    [
        "Regular paragraph without bullets.",
        "3.14 is the value of pi.",
        "-5 degrees Celsius was recorded.",
        "The meeting took place on 12/05/2024.",
        "In accordance with government norms.",
        "(Note: Important caveat)",
        "",
    ],
)
def test_non_list_item_patterns(non_bullet_text: str):
    """Verify regular paragraphs and numbers are not falsely classified as list items."""
    assert BlockExtractor._is_list_item(non_bullet_text) is False


def test_extract_blocks_mock_page():
    """Test extract_blocks logic with mock PyMuPDF page structure."""
    mock_page = MagicMock(spec=fitz.Page)
    mock_page.get_text.return_value = {
        "blocks": [
            # 1. Heading block (avg font >= 14.0)
            {
                "type": 0,
                "bbox": (50.0, 50.0, 300.0, 75.0),
                "lines": [
                    {
                        "spans": [
                            {"size": 16.0, "text": "GOVERNMENT OF UTTARAKHAND"},
                        ]
                    }
                ],
            },
            # 2. Paragraph block (avg font < 14.0)
            {
                "type": 0,
                "bbox": (50.0, 80.0, 400.0, 110.0),
                "lines": [
                    {
                        "spans": [
                            {"size": 11.0, "text": "This is an official notification "},
                            {"size": 11.0, "text": "regarding service rules."},
                        ]
                    }
                ],
            },
            # 3. List item block (avg font < 14.0, starts with bullet)
            {
                "type": 0,
                "bbox": (50.0, 120.0, 350.0, 140.0),
                "lines": [
                    {
                        "spans": [
                            {"size": 11.0, "text": "1. All departments must comply."},
                        ]
                    }
                ],
            },
            # 4. Heading with bullet (font >= 14.0 takes precedence over list item)
            {
                "type": 0,
                "bbox": (50.0, 150.0, 350.0, 170.0),
                "lines": [
                    {
                        "spans": [
                            {"size": 14.5, "text": "1. Introduction and Scope"},
                        ]
                    }
                ],
            },
            # 5. Image block (type = 1)
            {
                "type": 1,
                "bbox": (50.0, 200.0, 250.0, 350.0),
            },
        ]
    }

    blocks = BlockExtractor.extract_blocks(mock_page)

    assert len(blocks) == 5

    # Block 0: HEADING
    b0 = blocks[0]
    assert b0.block_type == BLOCK_TYPE_HEADING
    assert b0.text == "GOVERNMENT OF UTTARAKHAND"
    assert b0.reading_order == 0
    assert b0.confidence == 1.0
    assert b0.bbox == [50.0, 50.0, 300.0, 75.0]

    # Block 1: PARAGRAPH
    b1 = blocks[1]
    assert b1.block_type == BLOCK_TYPE_PARAGRAPH
    assert "official notification regarding service rules." in b1.text
    assert b1.reading_order == 1
    assert b1.confidence == 1.0

    # Block 2: LIST_ITEM
    b2 = blocks[2]
    assert b2.block_type == BLOCK_TYPE_LIST_ITEM
    assert b2.text == "1. All departments must comply."
    assert b2.reading_order == 2
    assert b2.confidence == 1.0

    # Block 3: HEADING (precedence over list item due to font size >= 14.0)
    b3 = blocks[3]
    assert b3.block_type == BLOCK_TYPE_HEADING
    assert b3.text == "1. Introduction and Scope"
    assert b3.reading_order == 3
    assert b3.confidence == 1.0

    # Block 4: IMAGE
    b4 = blocks[4]
    assert b4.block_type == BLOCK_TYPE_IMAGE
    assert b4.text == ""
    assert b4.reading_order == 4
    assert b4.confidence == 0.0
    assert b4.bbox == [50.0, 200.0, 250.0, 350.0]


def test_extract_blocks_edge_cases():
    """Verify edge cases like None page, empty dict, missing keys, and invalid formats."""
    # None page
    assert BlockExtractor.extract_blocks(None) == []

    # Mock page returning empty dict
    mock_empty = MagicMock(spec=fitz.Page)
    mock_empty.get_text.return_value = {}
    assert BlockExtractor.extract_blocks(mock_empty) == []

    # Mock page raising exception
    mock_err = MagicMock(spec=fitz.Page)
    mock_err.get_text.side_effect = RuntimeError("Failed to read page")
    assert BlockExtractor.extract_blocks(mock_err) == []

    # Mock page with malformed blocks
    mock_malformed = MagicMock(spec=fitz.Page)
    mock_malformed.get_text.return_value = {
        "blocks": [
            None,  # non-dict
            {},  # empty block
            {"type": 0},  # missing bbox and lines
            {"type": 1, "bbox": "invalid_bbox"},  # invalid bbox format
        ]
    }
    extracted = BlockExtractor.extract_blocks(mock_malformed)
    assert len(extracted) == 3

    # Empty block
    assert extracted[0].block_type == BLOCK_TYPE_PARAGRAPH
    assert extracted[0].text == ""
    assert extracted[0].bbox == [0.0, 0.0, 0.0, 0.0]
    assert extracted[0].reading_order == 0

    # Block with only type 0
    assert extracted[1].block_type == BLOCK_TYPE_PARAGRAPH
    assert extracted[1].reading_order == 1

    # Image block with invalid bbox
    assert extracted[2].block_type == BLOCK_TYPE_IMAGE
    assert extracted[2].bbox == [0.0, 0.0, 0.0, 0.0]
    assert extracted[2].reading_order == 2


def test_extract_blocks_real_fitz_page():
    """End-to-end integration test with a live PyMuPDF document."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # 1. Heading (fontsize 16 >= 14)
    page.insert_text((50, 50), "Uttarakhand Administration Order", fontsize=16)

    # 2. Normal paragraph (fontsize 11 < 14)
    page.insert_text((50, 90), "This order takes effect immediately upon publication.", fontsize=11)

    # 3. List items (fontsize 11 < 14)
    page.insert_text((50, 130), "1. Subordinate offices must report compliance within 15 days.", fontsize=11)
    page.insert_text((50, 160), "- Regional divisions must maintain digital records.", fontsize=11)

    # 4. Image
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50), 1)
    page.insert_image(fitz.Rect(50, 200, 100, 250), pixmap=pix)

    blocks = BlockExtractor.extract_blocks(page)
    doc.close()

    assert len(blocks) >= 4

    # Verify heading
    heading_blocks = [b for b in blocks if b.block_type == BLOCK_TYPE_HEADING]
    assert len(heading_blocks) >= 1
    assert "Uttarakhand Administration Order" in heading_blocks[0].text
    assert heading_blocks[0].confidence == 1.0

    # Verify paragraph
    para_blocks = [b for b in blocks if b.block_type == BLOCK_TYPE_PARAGRAPH]
    assert any("takes effect immediately" in b.text for b in para_blocks)

    # Verify list items
    list_blocks = [b for b in blocks if b.block_type == BLOCK_TYPE_LIST_ITEM]
    assert len(list_blocks) >= 1
    assert any("1." in b.text or "Subordinate offices" in b.text for b in list_blocks)

    # Verify image
    img_blocks = [b for b in blocks if b.block_type == BLOCK_TYPE_IMAGE]
    assert len(img_blocks) == 1
    assert img_blocks[0].text == ""
    assert img_blocks[0].confidence == 0.0

    # Verify reading orders are sequential and sorted
    orders = [b.reading_order for b in blocks]
    assert orders == list(range(len(blocks)))


def test_resolve_block_citation(db_session):
    """Test Acceptance Criteria 3: Citation links from chunks resolve to original version, page, and coordinates."""
    from adam.db.models import Source, Document, DocumentVersion, DocumentPage, TextBlock
    from adam.vocabularies import ReviewStatus, LifecycleStatus
    from adam.extract.blocks import resolve_block_citation

    # Setup database records
    source = Source(
        id="src_cite_test",
        name="Citation Test Source",
        owner_name="Owner",
        owner_contact="contact@uk.gov.in",
        written_authority_ref="AUTH/CITE/001",
        status="APPROVED",
    )
    doc = Document(
        id="doc_cite_test",
        source_id=source.id,
        title="Service Rules 2024",
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    ver = DocumentVersion(
        id="ver_cite_test",
        document_id=doc.id,
        source_url="https://finance.uk.gov.in/rules2024.pdf",
        sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        mime_type="application/pdf",
        byte_size=1024,
        original_object_key="originals/test.pdf",
    )
    page = DocumentPage(
        id="page_cite_test",
        version_id=ver.id,
        page_number=3,
        clean_text="Clean page text",
        image_key="pages/ver_cite_test/page_0003.png",
        review_status=ReviewStatus.AUTO_APPROVED.value,
    )
    block = TextBlock(
        id="blk_cite_test",
        page_id=page.id,
        block_type="PARAGRAPH",
        text="Section 4(1): Vehicle advance eligibility criteria.",
        bbox=[72.0, 144.0, 500.0, 180.0],
        reading_order=2,
        confidence=0.98,
    )

    db_session.add_all([source, doc, ver, page, block])
    db_session.commit()

    # Resolve citation
    resolved = resolve_block_citation(db_session, "blk_cite_test")
    assert resolved is not None
    assert resolved["block_id"] == "blk_cite_test"
    assert resolved["document_id"] == "doc_cite_test"
    assert resolved["version_id"] == "ver_cite_test"
    assert resolved["page_id"] == "page_cite_test"
    assert resolved["page_number"] == 3
    assert resolved["image_key"] == "pages/ver_cite_test/page_0003.png"
    assert resolved["bbox"] == [72.0, 144.0, 500.0, 180.0]
    assert resolved["text"] == "Section 4(1): Vehicle advance eligibility criteria."
    assert resolved["reading_order"] == 2
    assert resolved["confidence"] == 0.98
    assert resolved["review_status"] == ReviewStatus.AUTO_APPROVED.value
    assert resolved["is_approved"] is True

    # Non-existent block returns None
    assert resolve_block_citation(db_session, "blk_nonexistent") is None


def test_get_approved_blocks_filter(db_session):
    """Test Module 02 -> Module 03 dependency: Module 03 consumes approved page blocks only."""
    from adam.db.models import Source, Document, DocumentVersion, DocumentPage, TextBlock
    from adam.vocabularies import ReviewStatus, LifecycleStatus
    from adam.extract.blocks import get_approved_blocks

    source = Source(
        id="src_appr_test",
        name="Approved Source",
        owner_name="Owner",
        owner_contact="contact@uk.gov.in",
        written_authority_ref="AUTH/001",
        status="APPROVED",
    )
    doc = Document(
        id="doc_appr_test",
        source_id=source.id,
        title="Test Document",
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    ver = DocumentVersion(
        id="ver_appr_test",
        document_id=doc.id,
        source_url="https://example.com/test.pdf",
        sha256="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        mime_type="application/pdf",
        byte_size=1024,
        original_object_key="originals/test.pdf",
    )

    # Page 1: AUTO_APPROVED
    page1 = DocumentPage(
        id="page_appr_1",
        version_id=ver.id,
        page_number=1,
        review_status=ReviewStatus.AUTO_APPROVED.value,
    )
    blk1 = TextBlock(
        id="blk_appr_1",
        page_id=page1.id,
        block_type="PARAGRAPH",
        text="Approved block 1",
        reading_order=0,
    )

    # Page 2: FLAGGED (should be excluded)
    page2 = DocumentPage(
        id="page_appr_2",
        version_id=ver.id,
        page_number=2,
        review_status=ReviewStatus.FLAGGED.value,
    )
    blk2 = TextBlock(
        id="blk_appr_2",
        page_id=page2.id,
        block_type="PARAGRAPH",
        text="Flagged block 2",
        reading_order=0,
    )

    # Page 3: REVIEWED (human approved, should be included)
    page3 = DocumentPage(
        id="page_appr_3",
        version_id=ver.id,
        page_number=3,
        review_status=ReviewStatus.REVIEWED.value,
    )
    blk3 = TextBlock(
        id="blk_appr_3",
        page_id=page3.id,
        block_type="PARAGRAPH",
        text="Reviewed block 3",
        reading_order=0,
    )

    db_session.add_all([source, doc, ver, page1, blk1, page2, blk2, page3, blk3])
    db_session.commit()

    approved = get_approved_blocks(db_session, version_id="ver_appr_test")
    approved_ids = [b["block_id"] for b in approved]

    # Must contain blk_appr_1 (AUTO_APPROVED) and blk_appr_3 (REVIEWED), but NOT blk_appr_2 (FLAGGED)
    assert "blk_appr_1" in approved_ids
    assert "blk_appr_3" in approved_ids
    assert "blk_appr_2" not in approved_ids
    assert len(approved) == 2

