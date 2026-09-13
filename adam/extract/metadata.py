"""Administrative metadata extraction from Uttarakhand Government Orders."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Any, List, Tuple

from adam.extract.precedents import PrecedentCitationParser


@dataclass
class ExtractedMetadata:
    """Structured administrative metadata extracted from document body and headers."""
    subject: Optional[str] = None
    issuing_authority_title: Optional[str] = None
    signatory_name: Optional[str] = None
    order_number: Optional[str] = None
    order_date: Optional[date] = None
    department_name: Optional[str] = None
    language_distribution: Dict[str, int] = None  # {"hi_pct": 80, "en_pct": 20}


class AdministrativeMetadataExtractor:
    """Extracts Subject (विषय), issuing authority, signatory, and dates from official texts."""

    SUBJECT_PATTERNS = [
        re.compile(r"(?:विषय\s*[:\-]\s*)([^\n]+(?:\n\s*[^\n]+){0,3})", re.IGNORECASE),
        re.compile(r"(?:subject\s*[:\-]\s*)([^\n]+(?:\n\s*[^\n]+){0,3})", re.IGNORECASE),
    ]

    AUTHORITY_TITLES = [
        "अपर मुख्य सचिव",
        "प्रमुख सचिव",
        "सचिव",
        "विशेष सचिव",
        "अपर सचिव",
        "संयुक्त सचिव",
        "उप सचिव",
        "निदेशक",
        "संयुक्त निदेशक",
        "आयुक्त",
        "जिलाधिकारी",
        "Additional Chief Secretary",
        "Principal Secretary",
        "Secretary",
        "Special Secretary",
        "Additional Secretary",
        "Joint Secretary",
        "Director",
        "Commissioner",
    ]

    ORDER_NUMBER_PATTERNS = [
        re.compile(r"(?:संख्या|शासनादेश\s+संख्या|सं०|no\.?)\s*[:\-]?\s*([0-9]+[0-9A-Za-z\(\)\/\-\._]{3,60}(?:\/[^\n,\s]+)?)", re.IGNORECASE),
        re.compile(r"(?:order\s+no\.?|office\s+memorandum\s+no\.?)\s*[:\-]?\s*([0-9]+[0-9A-Za-z\(\)\/\-\._]{3,60})", re.IGNORECASE),
    ]

    DATE_PATTERNS = [
        re.compile(r"(?:देहरादून\s*[:\s,]+दिनांक\s*[:\s]?\s*([0-9\.\-\/A-Za-z\u0900-\u097f\s,]+))", re.IGNORECASE),
        re.compile(r"(?:दिनांक\s*[:\s]\s*([0-9\.\-\/A-Za-z\u0900-\u097f\s,]+?)(?:\s*ई०|\s*\.|\n|$))", re.IGNORECASE),
        re.compile(r"(?:dated\s*[:\s]\s*([0-9a-zA-Z\.\-\/\s,]+?)(?:\.|\n|$))", re.IGNORECASE),
    ]

    @classmethod
    def extract(cls, full_text: str) -> ExtractedMetadata:
        """Extract administrative metadata from clean text."""
        subject = cls._extract_subject(full_text)
        auth_title, signatory = cls._extract_authority_and_signatory(full_text)
        order_num = cls._extract_order_number(full_text)
        order_dt = cls._extract_date(full_text)
        lang_dist = cls._compute_language_distribution(full_text)

        return ExtractedMetadata(
            subject=subject,
            issuing_authority_title=auth_title,
            signatory_name=signatory,
            order_number=order_num,
            order_date=order_dt,
            language_distribution=lang_dist,
        )

    @classmethod
    def _extract_subject(cls, text: str) -> Optional[str]:
        for pattern in cls.SUBJECT_PATTERNS:
            match = pattern.search(text)
            if match:
                raw_subj = match.group(1).strip()
                # Clean multiple spaces and line breaks
                clean_subj = " ".join(raw_subj.split())
                # Truncate at common closing cues (महोदय, etc.)
                clean_subj = re.split(r"(?:महोदय|sir|संदर्भ\s*[:\-])", clean_subj, flags=re.IGNORECASE)[0].strip()
                if len(clean_subj) >= 5:
                    return clean_subj
        return None

    @classmethod
    def _extract_authority_and_signatory(cls, text: str) -> Tuple[Optional[str], Optional[str]]:
        # Check from bottom up (signature block typically at end of document)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        last_lines = lines[-25:] if len(lines) > 25 else lines

        found_title = None
        found_name = None

        for title in cls.AUTHORITY_TITLES:
            for i, line in enumerate(last_lines):
                if title in line:
                    found_title = title
                    # Check preceding or following line for signatory name in parentheses: e.g. (आनन्द बर्द्धन)
                    for offset in (-2, -1, 1, 2):
                        idx = i + offset
                        if 0 <= idx < len(last_lines):
                            candidate = last_lines[idx]
                            m = re.search(r"\(([A-Za-z\u0900-\u097f\s\.\-–]+)\)", candidate)
                            if m and len(m.group(1).strip()) >= 3:
                                found_name = m.group(1).strip()
                                break
                    break
            if found_title:
                break

        return found_title, found_name

    @classmethod
    def _extract_order_number(cls, text: str) -> Optional[str]:
        # Typically in top 20 lines of document
        lines = text.splitlines()[:30]
        header_text = "\n".join(lines)
        for pattern in cls.ORDER_NUMBER_PATTERNS:
            match = pattern.search(header_text)
            if match:
                cand = match.group(1).strip().strip(".,;")
                if any(c.isdigit() for c in cand):
                    return cand
        return None

    @classmethod
    def _extract_date(cls, text: str) -> Optional[date]:
        # Look in header and footer
        lines = text.splitlines()
        sample = "\n".join(lines[:25] + lines[-15:])
        for pattern in cls.DATE_PATTERNS:
            match = pattern.search(sample)
            if match:
                raw_dt_str = match.group(1).strip()
                parsed = PrecedentCitationParser._parse_date_string(raw_dt_str)
                if parsed:
                    return parsed
        return None

    @classmethod
    def _compute_language_distribution(cls, text: str) -> Dict[str, int]:
        devanagari_chars = sum(1 for c in text if "\u0900" <= c <= "\u097f")
        latin_chars = sum(1 for c in text if ("a" <= c <= "z") or ("A" <= c <= "Z"))
        total = devanagari_chars + latin_chars
        if total == 0:
            return {"hi_pct": 100, "en_pct": 0}
        hi_pct = int((devanagari_chars / total) * 100)
        en_pct = 100 - hi_pct
        return {"hi_pct": hi_pct, "en_pct": en_pct}
