"""Image preprocessing and rendering utilities for OCR pipelines and page visualization."""

import io
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# EXIF Tag ID for Orientation is 274 (0x0112)
EXIF_ORIENTATION_TAG: int = 0x0112

# Standard EXIF orientation values mapped to rotation in clockwise degrees
# 1: Normal (0 deg)
# 2: Mirrored horizontal (0 deg)
# 3: Upside down (180 deg)
# 4: Mirrored vertical (180 deg)
# 5: Mirrored horizontal & rotated 270 deg CW (90 deg)
# 6: Rotated 90 deg CW (90 deg)
# 7: Mirrored horizontal & rotated 90 deg CW (270 deg)
# 8: Rotated 270 deg CW (270 deg)
EXIF_ORIENTATION_TO_DEGREES: Dict[int, int] = {
    1: 0,
    2: 0,
    3: 180,
    4: 180,
    5: 90,
    6: 90,
    7: 270,
    8: 270,
}

# Binary threshold boundary
DEFAULT_BINARIZATION_THRESHOLD: int = 128


@dataclass
class PageImageMetadata:
    """Metadata describing a rendered or preprocessed page image."""

    page_number: int
    width: int
    height: int
    dpi: int
    format: str = "PNG"
    rotation_degrees: int = 0
    size_bytes: int = 0


class BaseImagePreprocessor(ABC):
    """Abstract base class for document image preprocessors."""

    @abstractmethod
    def preprocess(self, image_bytes: bytes, **kwargs: Any) -> bytes:
        """Preprocess raw image bytes for downstream OCR extraction.

        Args:
            image_bytes: Raw image file bytes.
            **kwargs: Implementation-specific preprocessing parameters.

        Returns:
            Preprocessed PNG image bytes.
        """
        pass


def render_page_image(pdf_bytes: bytes, page_number: int, dpi: int = 300) -> bytes:
    """Render a specified PDF page as a high-resolution PNG image.

    Opens the PDF document in-memory using PyMuPDF (fitz), indexes the page
    (converting 1-indexed page_number to 0-indexed internal index), renders
    it to a pixmap at the specified DPI, and returns raw PNG bytes.

    Args:
        pdf_bytes: Raw bytes of the PDF document.
        page_number: 1-indexed page number to render.
        dpi: Target resolution in dots per inch (default: 300 DPI for OCR).

    Returns:
        PNG image bytes of the rendered page.

    Raises:
        ValueError: If page_number is < 1 or PDF bytes cannot be parsed.
        IndexError: If page_number exceeds the document's total page count.
        RuntimeError: If rendering fails.
    """
    if page_number < 1:
        logger.error("Invalid page_number %d: Page numbers are 1-indexed (must be >= 1)", page_number)
        raise ValueError(f"Invalid page_number {page_number}. Page numbers are 1-indexed and must be >= 1.")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.error("Failed to open PDF stream with PyMuPDF: %s", e)
        raise ValueError(f"Failed to open PDF document: {e}") from e

    try:
        total_pages = len(doc)
        page_idx = page_number - 1

        if page_idx >= total_pages:
            logger.error("Page number %d out of range (document contains %d pages)", page_number, total_pages)
            raise IndexError(f"Page number {page_number} is out of bounds for document with {total_pages} pages.")

        page = doc[page_idx]
        pixmap = page.get_pixmap(dpi=dpi)
        png_bytes = pixmap.tobytes("png")
        logger.debug(
            "Rendered page %d/%d at %d DPI (%dx%d, %d bytes)",
            page_number,
            total_pages,
            dpi,
            pixmap.width,
            pixmap.height,
            len(png_bytes),
        )
        return png_bytes
    except (ValueError, IndexError):
        raise
    except Exception as e:
        logger.error("Failed to render page %d at %d DPI: %s", page_number, dpi, e)
        raise RuntimeError(f"Failed to render page {page_number} as image: {e}") from e
    finally:
        doc.close()


def detect_rotation(image_bytes: bytes) -> int:
    """Detect image orientation and rotation in degrees from EXIF metadata.

    Loads the image with Pillow and inspects EXIF orientation tags.
    Returns rotation angle in clockwise degrees (0, 90, 180, 270).
    Defaults to 0 if orientation cannot be determined or on error.

    Args:
        image_bytes: Raw image file bytes (e.g. JPEG, TIFF, PNG).

    Returns:
        Detected rotation in degrees: 0, 90, 180, or 270.
    """
    if not image_bytes:
        return 0

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            orientation: Optional[int] = None

            # 1. Check modern Pillow getexif()
            if hasattr(img, "getexif"):
                exif = img.getexif()
                if exif:
                    orientation = exif.get(EXIF_ORIENTATION_TAG)

            # 2. Fallback to legacy _getexif() if orientation not found
            if orientation is None and hasattr(img, "_getexif"):
                raw_exif = img._getexif()
                if raw_exif and isinstance(raw_exif, dict):
                    orientation = raw_exif.get(EXIF_ORIENTATION_TAG)

            if orientation is not None:
                # Direct EXIF orientation tag mapping
                if orientation in EXIF_ORIENTATION_TO_DEGREES:
                    deg = EXIF_ORIENTATION_TO_DEGREES[orientation]
                    logger.debug("Detected EXIF orientation %d -> %d degrees", orientation, deg)
                    return deg

                # Direct degree value (0, 90, 180, 270)
                if orientation in (0, 90, 180, 270):
                    return int(orientation)

            return 0
    except Exception as e:
        logger.warning("Failed to detect rotation from image bytes: %s", e)
        return 0


def _estimate_skew_angle(image: Image.Image) -> float:
    """Estimate skew angle of text lines using horizontal projection profile variance.

    Scans angles between -10.0 and +10.0 degrees. Finds the rotation angle that
    maximizes the variance of horizontal line projections.

    Args:
        image: Pillow Image instance.

    Returns:
        Estimated skew angle in degrees.
    """
    try:
        import numpy as np
    except ImportError:
        logger.debug("NumPy not installed; skipping projection profile deskew estimation.")
        return 0.0

    try:
        w, h = image.size
        # Downsample large images for rapid variance calculation
        max_dim = 600
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            img_small = image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR)
        else:
            img_small = image

        if img_small.mode != "L":
            img_small = img_small.convert("L")

        arr = np.array(img_small) < DEFAULT_BINARIZATION_THRESHOLD
        if not np.any(arr):
            return 0.0

        best_score = -1.0
        best_angle = 0.0

        # Scan angles in 0.5 degree steps
        for angle in np.arange(-10.0, 10.5, 0.5):
            rotated = img_small.rotate(float(angle), resample=Image.Resampling.NEAREST, expand=False, fillcolor=255)
            rot_arr = np.array(rotated) < DEFAULT_BINARIZATION_THRESHOLD
            row_sums = np.sum(rot_arr, axis=1)
            score = float(np.var(row_sums))
            if score > best_score:
                best_score = score
                best_angle = float(angle)

        return best_angle
    except Exception as e:
        logger.warning("Error during skew angle estimation: %s", e)
        return 0.0


def preprocess_for_ocr(
    image_bytes: bytes,
    force_deskew: bool = False,
    threshold: int = DEFAULT_BINARIZATION_THRESHOLD,
) -> bytes:
    """Preprocess image for OCR extraction and text recognition.

    Performs image orientation correction, optional deskewing, grayscale conversion,
    and binarization at the specified threshold (default: 128), returning PNG bytes.

    Args:
        image_bytes: Raw image file bytes.
        force_deskew: If True, detects text skew angle and rotates the image upright.
        threshold: Threshold intensity in range [0, 255] for binarization (default: 128).

    Returns:
        Preprocessed binarized PNG image bytes.

    Raises:
        ValueError: If image_bytes is invalid or cannot be loaded with Pillow.
    """
    if not image_bytes:
        logger.error("Received empty image_bytes for preprocessing")
        raise ValueError("Cannot preprocess empty image bytes.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # 1. Normalize orientation via EXIF transposition
            img = ImageOps.exif_transpose(img)

            # 2. Composite transparency over white background if alpha channel exists
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                # Paste using alpha channel mask
                mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
                bg.paste(img, mask=mask)
                img = bg

            # 3. Optional deskewing
            if force_deskew:
                skew_angle = _estimate_skew_angle(img)
                if abs(skew_angle) >= 0.5:
                    logger.debug("Applying deskew rotation of %.1f degrees", skew_angle)
                    fill_color = 255 if img.mode == "L" else (255, 255, 255)
                    img = img.rotate(skew_angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=fill_color)

            # 4. Convert to grayscale ('L' mode)
            gray = img.convert("L")

            # 5. Apply threshold for binarization (0 if < threshold, 255 if >= threshold)
            lut = [0 if i < threshold else 255 for i in range(256)]
            binarized = gray.point(lut, mode="L")

            # 6. Save as PNG bytes
            output = io.BytesIO()
            binarized.save(output, format="PNG")
            return output.getvalue()
    except ValueError:
        raise
    except Exception as e:
        logger.error("Failed to preprocess image for OCR: %s", e)
        raise ValueError(f"Failed to preprocess image for OCR: {e}") from e


class StandardOCRPreprocessor(BaseImagePreprocessor):
    """Standard OCR preprocessor providing binarization and optional deskewing."""

    def __init__(self, threshold: int = DEFAULT_BINARIZATION_THRESHOLD):
        self.threshold = threshold

    def preprocess(self, image_bytes: bytes, **kwargs: Any) -> bytes:
        force_deskew = kwargs.get("force_deskew", False)
        return preprocess_for_ocr(image_bytes, force_deskew=force_deskew, threshold=self.threshold)
