"""Tests for PyMuPDF text extraction, table extraction, and scan detection."""

import fitz  # PyMuPDF
import pytest

from adam.extract.pdf import PdfExtractor


def _generate_test_pdf_with_table() -> bytes:
    """Generate a valid in-memory PDF with text and a structured table annexure."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    # Add header and body text
    page.insert_text((50, 50), "Uttarakhand Government - Finance Department (Vitt Vibhag)", fontsize=14)
    page.insert_text((50, 80), "Order No: 101/XXVII(7)/2024", fontsize=11)
    page.insert_text((50, 110), "Subject: Revision of Dearness Allowance (Mahangai Bhatta).", fontsize=12)

    # Draw table border lines and cell texts
    # Header row
    page.draw_rect(fitz.Rect(50, 150, 500, 180), color=(0, 0, 0), width=1)
    page.insert_text((60, 170), "Designation / Post")
    page.insert_text((220, 170), "Current DA Rate")
    page.insert_text((380, 170), "Revised DA Rate")

    # Data row
    page.draw_rect(fitz.Rect(50, 180, 500, 210), color=(0, 0, 0), width=1)
    page.insert_text((60, 200), "Group A and B Officers")
    page.insert_text((220, 200), "46%")
    page.insert_text((380, 200), "50%")

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _generate_scanned_pdf() -> bytes:
    """Generate a PDF containing only an image and no text layer to simulate a scanned document."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Insert a dummy pixmap image onto the page
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 400), 1)
    pix.clear_with(255)  # white background
    page.insert_image(page.rect, pixmap=pix)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_pdf_extraction_digital_text():
    pdf_bytes = _generate_test_pdf_with_table()
    pages = PdfExtractor.extract_pages(pdf_bytes)

    assert len(pages) == 1
    page = pages[0]
    assert page.page_number == 1
    assert "Finance Department" in page.clean_text
    assert "Dearness Allowance" in page.clean_text
    assert page.is_scanned is False
    assert page.word_count > 5


def test_pdf_extraction_scanned_page_detection():
    pdf_bytes = _generate_scanned_pdf()
    pages = PdfExtractor.extract_pages(pdf_bytes)

    assert len(pages) == 1
    page = pages[0]
    # Scanned detection must flag true when text is absent/sparse and image exists
    assert page.is_scanned is True
    assert page.scan_quality_score is not None
    assert page.scan_quality_score > 0


def test_language_detection():
    hindi_text = "उत्तराखंड शासन द्वारा जारी महत्वपूर्ण शासनादेश एवं परिपत्र।"
    assert PdfExtractor.detect_language(hindi_text) == "hi"

    english_text = "Government of Uttarakhand Finance Department Notification and Guidelines."
    assert PdfExtractor.detect_language(english_text) == "en"

    bilingual_text = "उत्तराखंड शासन Finance Department Dehradun Order No 123"
    assert PdfExtractor.detect_language(bilingual_text) == "bilingual"
