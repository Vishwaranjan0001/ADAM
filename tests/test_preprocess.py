"""Tests for image preprocessing and PDF rendering."""

import io
import fitz
import pytest
from PIL import Image

from adam.extract.preprocess import (
    render_page_image,
    detect_rotation,
    preprocess_for_ocr,
    StandardOCRPreprocessor,
)


def _create_sample_pdf(pages: int = 2) -> bytes:
    """Helper to generate a multi-page test PDF in-memory."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((50, 50), f"Test Page {i + 1}", fontsize=16)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _create_image_with_exif_orientation(orientation: int) -> bytes:
    """Helper to generate a JPEG image with an EXIF orientation tag."""
    im = Image.new("RGB", (20, 20), color=(120, 120, 120))
    exif = im.getexif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def test_render_page_image_valid():
    pdf_bytes = _create_sample_pdf(pages=2)

    # Render page 1 at 300 DPI
    png_bytes = render_page_image(pdf_bytes, page_number=1, dpi=300)
    assert isinstance(png_bytes, bytes)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # Verify rendered image dimensions and mode
    with Image.open(io.BytesIO(png_bytes)) as img:
        assert img.format == "PNG"
        assert img.width > 0
        assert img.height > 0

    # Render page 2 at 150 DPI
    png_150 = render_page_image(pdf_bytes, page_number=2, dpi=150)
    with Image.open(io.BytesIO(png_150)) as img_150:
        assert img_150.width < img.width  # Lower DPI results in fewer pixels


def test_render_page_image_invalid_page():
    pdf_bytes = _create_sample_pdf(pages=1)

    # Invalid page number < 1
    with pytest.raises(ValueError, match="1-indexed"):
        render_page_image(pdf_bytes, page_number=0)

    # Out of bounds page number
    with pytest.raises(IndexError, match="out of bounds"):
        render_page_image(pdf_bytes, page_number=2)


def test_render_page_image_corrupt_bytes():
    with pytest.raises(ValueError, match="Failed to open PDF"):
        render_page_image(b"not-a-valid-pdf", page_number=1)


def test_detect_rotation_exif():
    # Test orientation 1 -> 0 deg
    bytes_1 = _create_image_with_exif_orientation(1)
    assert detect_rotation(bytes_1) == 0

    # Test orientation 3 -> 180 deg
    bytes_3 = _create_image_with_exif_orientation(3)
    assert detect_rotation(bytes_3) == 180

    # Test orientation 6 -> 90 deg
    bytes_6 = _create_image_with_exif_orientation(6)
    assert detect_rotation(bytes_6) == 90

    # Test orientation 8 -> 270 deg
    bytes_8 = _create_image_with_exif_orientation(8)
    assert detect_rotation(bytes_8) == 270


def test_detect_rotation_no_exif_and_corrupt():
    # Plain PNG without EXIF
    im = Image.new("RGB", (10, 10), color=(255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    assert detect_rotation(buf.getvalue()) == 0

    # Empty bytes
    assert detect_rotation(b"") == 0

    # Corrupt bytes
    assert detect_rotation(b"corrupt-image-data") == 0


def test_preprocess_for_ocr_binarization():
    # Create an image with known grayscale gradients
    im = Image.new("RGB", (4, 4))
    # Pixels: some below 128, some >= 128
    pixels = [
        (50, 50, 50), (100, 100, 100), (127, 127, 127), (128, 128, 128),
        (129, 129, 129), (200, 200, 200), (0, 0, 0), (255, 255, 255),
        (10, 10, 10), (20, 20, 20), (30, 30, 30), (130, 130, 130),
        (140, 140, 140), (150, 150, 150), (250, 250, 250), (255, 255, 255),
    ]
    im.putdata(pixels)
    buf = io.BytesIO()
    im.save(buf, format="PNG")

    processed = preprocess_for_ocr(buf.getvalue())
    assert isinstance(processed, bytes)
    assert processed.startswith(b"\x89PNG\r\n\x1a\n")

    with Image.open(io.BytesIO(processed)) as out_img:
        assert out_img.mode == "L"
        # Check that values are strictly binarized to {0, 255}
        unique_vals = set(out_img.getdata())
        assert unique_vals.issubset({0, 255})


def test_preprocess_for_ocr_transparent_rgba():
    # RGBA image with transparent alpha
    im = Image.new("RGBA", (10, 10), color=(0, 0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, format="PNG")

    processed = preprocess_for_ocr(buf.getvalue())
    with Image.open(io.BytesIO(processed)) as out_img:
        # Transparent background should composite to white (255)
        assert set(out_img.getdata()) == {255}


def test_preprocess_for_ocr_deskew_option():
    # Test that force_deskew executes without error
    im = Image.new("RGB", (50, 50), color=(255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")

    processed = preprocess_for_ocr(buf.getvalue(), force_deskew=True)
    assert isinstance(processed, bytes)
    assert len(processed) > 0


def test_preprocess_for_ocr_empty_input():
    with pytest.raises(ValueError, match="Cannot preprocess empty image bytes"):
        preprocess_for_ocr(b"")


def test_standard_ocr_preprocessor_class():
    preprocessor = StandardOCRPreprocessor(threshold=128)
    im = Image.new("RGB", (10, 10), color=(200, 200, 200))
    buf = io.BytesIO()
    im.save(buf, format="PNG")

    out_bytes = preprocessor.preprocess(buf.getvalue())
    assert isinstance(out_bytes, bytes)
    assert out_bytes.startswith(b"\x89PNG\r\n\x1a\n")
