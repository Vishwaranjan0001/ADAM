# 02 — Document Processing and OCR

## Pipeline

`original bytes → virus/type validation → born-digital extraction → page render/OCR → layout & language detection → normalized text + coordinates → human QA → immutable chunks`

Keep originals unchanged. PDF text extraction is preferred; OCR only pages without reliable embedded text. Preserve page images and bounding boxes so a citation can open the exact original page.

## Technology and Mac profile

- Start with `pypdf`/PDF text extraction and `OCRmyPDF`/Tesseract for modest batches. Tesseract supports Devanagari with the correct language data.
- Evaluate [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) for difficult Hindi/English scans and layout output; its own documentation describes structured JSON/Markdown and multilingual support. Run it as a queued worker, one document at a time on the 8GB Mac—not inside the chat request path.
- Use image preprocessing (deskew, rotate, 300dpi render) only when quality gates fail. Do not use a large vision-language model as the sole transcription source.

## Output and quality schema

`pages(version_id, page_no, image_key, extracted_text, ocr_text, selected_text, language, text_confidence, rotation, review_status)`

`blocks(id, page_id, block_type, text, bbox, reading_order, confidence)`; `tables(id, page_id, html_or_csv_key, bbox, extraction_method, review_status)`; `processing_runs(version_id, parser_version, ocr_engine, model_version, config_hash, started_at, result)`.

Store text normalized to Unicode NFC plus a page-faithful original transcript. Never silently correct GO numbers, dates, amounts or names.

## Quality gates

- Flag scanned pages with low confidence, very low character yield, mixed-script uncertainty, tables, seals/signatures, handwritten material, or contradictory extracted/OCR text.
- Human review required for all pilot legal/financial rules, all numeric tables used in answers, and any citation candidate with a low-confidence page.
- Reviewer corrects the transcript against the page image; corrections become versioned annotations, not changes to original bytes.

## Acceptance criteria

- 100% pages accounted for; page count matches the original PDF.
- ≥98% exact match on a labelled clean Hindi/English sample; report character error rate separately for scans. Threshold failure blocks publication.
- Citation links from chunks resolve to original version, page and highlighted coordinates.

## Dependencies

Module 01 originals/metadata; module 03 consumes approved page blocks only.
