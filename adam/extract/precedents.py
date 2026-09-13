"""Precedent citation parsing and cross-order relationship extraction."""

import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple, Set


HINDI_MONTHS = {
    "जनवरी": 1,
    "फरवरी": 2,
    "मार्च": 3,
    "अप्रैल": 4,
    "मई": 5,
    "जून": 6,
    "जुलाई": 7,
    "अगस्त": 8,
    "सितम्बर": 9,
    "सितंबर": 9,
    "अक्टूबर": 10,
    "अक्तूबर": 10,
    "नवम्बर": 11,
    "नवंबर": 11,
    "दिसम्बर": 12,
    "दिसंबर": 12,
}

ENGLISH_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


@dataclass
class ParsedCitation:
    """A cited legal/administrative precedent extracted from document text."""
    raw_citation_text: str
    cited_order_number: Optional[str] = None
    cited_date: Optional[date] = None
    cited_act_or_rule: Optional[str] = None
    relation_type: str = "REFERS_TO"  # IN_CONTINUATION_OF, SUPERSEDES, AMENDS, READ_WITH, REFERS_TO


class PrecedentCitationParser:
    """Parses bilingual Uttarakhand Government Orders for cited precedents and legal relationships."""

    # Patterns for order numbers in Uttarakhand GOs: e.g. "123/XXVII(7)/2022", "GO/2021/100", "45/1(2)/2021-TC"
    ORDER_NUM_REGEX = r"([0-9A-Za-z\u0900-\u097f\(\)\/\-\._]{3,60})"

    # Hindi precedent patterns
    HINDI_CONTINUATION = re.compile(
        rf"(?:शासनादेश\s+संख्या|संख्या|पत्र\s+संख्या)\s*[:\-]?\s*{ORDER_NUM_REGEX}"
        r"(?:\s*दिनांक\s*([0-9\.\-\/A-Za-z\u0900-\u097f\s,]+?))?"
        r"\s*(?:के\s*क्रम\s*में|के\s*अनुक्रम\s*में)",
        re.IGNORECASE,
    )

    HINDI_SUPERSEDES = re.compile(
        rf"(?:शासनादेश\s+संख्या|संख्या|पत्र\s+संख्या)\s*[:\-]?\s*{ORDER_NUM_REGEX}"
        r"(?:\s*दिनांक\s*([0-9\.\-\/A-Za-z\u0900-\u097f\s,]+?))?"
        r"\s*(?:को\s*अतिष्ठित|को\s*अधिक्रमित|के\s*अधिक्रमण\s*में|को\s*निरस्त\s*करते\s*हुए)",
        re.IGNORECASE,
    )

    HINDI_AMENDS = re.compile(
        rf"(?:शासनादेश\s+संख्या|संख्या)\s*[:\-]?\s*{ORDER_NUM_REGEX}"
        r"(?:\s*दिनांक\s*([0-9\.\-\/A-Za-z\u0900-\u097f\s,]+?))?"
        r"\s*(?:में\s*निम्नवत्\s*संशोधन|को\s*संशोधित\s*करते\s*हुए)",
        re.IGNORECASE,
    )

    HINDI_GENERAL_REF = re.compile(
        rf"(?:शासनादेश\s+संख्या|शासनादेश\s+सं०|संख्या\s*[:\-])\s*{ORDER_NUM_REGEX}"
        r"(?:\s*दिनांक\s*([0-9\.\-\/A-Za-z\u0900-\u097f\s,]+?))?",
        re.IGNORECASE,
    )

    # English precedent patterns
    ENG_CONTINUATION = re.compile(
        rf"(?:in\s+continuation\s+of\s+(?:government\s+order|go|order|office\s+memorandum|om)\s*(?:no\.?|number)?\s*[:\-]?\s*)"
        rf"{ORDER_NUM_REGEX}"
        rf"(?:\s*(?:dated|dt\.?)\s*([0-9a-zA-Z\.\-\/\s]+?))?(?:,|\.|\n|$)",
        re.IGNORECASE,
    )

    ENG_SUPERSEDES = re.compile(
        rf"(?:in\s+supersession\s+of\s+(?:government\s+order|go|order|om)\s*(?:no\.?|number)?\s*[:\-]?\s*)"
        rf"{ORDER_NUM_REGEX}"
        rf"(?:\s*(?:dated|dt\.?)\s*([0-9a-zA-Z\.\-\/\s]+?))?(?:,|\.|\n|$)",
        re.IGNORECASE,
    )

    ENG_AMENDS = re.compile(
        rf"(?:order\s+no\.?\s*{ORDER_NUM_REGEX}\s*(?:dated\s*([0-9a-zA-Z\.\-\/\s]+?))?\s*is\s+hereby\s+amended)",
        re.IGNORECASE,
    )

    ENG_READ_WITH = re.compile(
        r"(?:read\s+with\s+(?:the\s+)?([A-Za-z0-9\s,\-–\(\)]+?(?:Act|Rules|Regulations|Manual|Code)(?:\s*,?\s*[0-9]{4})?))",
        re.IGNORECASE,
    )

    @classmethod
    def extract_citations(cls, text: str) -> List[ParsedCitation]:
        """Extract all cited government orders, rules, and precedents from document text."""
        citations: List[ParsedCitation] = []
        seen_keys: Set[Tuple[str, Optional[str]]] = set()

        # 1. English Supersessions
        for match in cls.ENG_SUPERSEDES.finditer(text):
            raw = match.group(0).strip()
            num = cls._clean_order_num(match.group(1))
            dt = cls._parse_date_string(match.group(2)) if match.group(2) else None
            key = ("SUPERSEDES", num)
            if num and key not in seen_keys:
                seen_keys.add(key)
                citations.append(ParsedCitation(
                    raw_citation_text=raw,
                    cited_order_number=num,
                    cited_date=dt,
                    relation_type="SUPERSEDES",
                ))

        # 2. Hindi Supersessions
        for match in cls.HINDI_SUPERSEDES.finditer(text):
            raw = match.group(0).strip()
            num = cls._clean_order_num(match.group(1))
            dt = cls._parse_date_string(match.group(2)) if match.group(2) else None
            key = ("SUPERSEDES", num)
            if num and key not in seen_keys:
                seen_keys.add(key)
                citations.append(ParsedCitation(
                    raw_citation_text=raw,
                    cited_order_number=num,
                    cited_date=dt,
                    relation_type="SUPERSEDES",
                ))

        # 3. English Continuations
        for match in cls.ENG_CONTINUATION.finditer(text):
            raw = match.group(0).strip()
            num = cls._clean_order_num(match.group(1))
            dt = cls._parse_date_string(match.group(2)) if match.group(2) else None
            key = ("IN_CONTINUATION_OF", num)
            if num and key not in seen_keys:
                seen_keys.add(key)
                citations.append(ParsedCitation(
                    raw_citation_text=raw,
                    cited_order_number=num,
                    cited_date=dt,
                    relation_type="IN_CONTINUATION_OF",
                ))

        # 4. Hindi Continuations
        for match in cls.HINDI_CONTINUATION.finditer(text):
            raw = match.group(0).strip()
            num = cls._clean_order_num(match.group(1))
            dt = cls._parse_date_string(match.group(2)) if match.group(2) else None
            key = ("IN_CONTINUATION_OF", num)
            if num and key not in seen_keys:
                seen_keys.add(key)
                citations.append(ParsedCitation(
                    raw_citation_text=raw,
                    cited_order_number=num,
                    cited_date=dt,
                    relation_type="IN_CONTINUATION_OF",
                ))

        # 5. Amendments
        for match in cls.HINDI_AMENDS.finditer(text):
            raw = match.group(0).strip()
            num = cls._clean_order_num(match.group(1))
            dt = cls._parse_date_string(match.group(2)) if match.group(2) else None
            key = ("AMENDS", num)
            if num and key not in seen_keys:
                seen_keys.add(key)
                citations.append(ParsedCitation(
                    raw_citation_text=raw,
                    cited_order_number=num,
                    cited_date=dt,
                    relation_type="AMENDS",
                ))

        for match in cls.ENG_AMENDS.finditer(text):
            raw = match.group(0).strip()
            num = cls._clean_order_num(match.group(1))
            dt = cls._parse_date_string(match.group(2)) if match.group(2) else None
            key = ("AMENDS", num)
            if num and key not in seen_keys:
                seen_keys.add(key)
                citations.append(ParsedCitation(
                    raw_citation_text=raw,
                    cited_order_number=num,
                    cited_date=dt,
                    relation_type="AMENDS",
                ))

        # 6. Read with statutory Act / Rule
        for match in cls.ENG_READ_WITH.finditer(text):
            raw = match.group(0).strip()
            act_name = match.group(1).strip()
            key = ("READ_WITH", act_name)
            if key not in seen_keys:
                seen_keys.add(key)
                citations.append(ParsedCitation(
                    raw_citation_text=raw,
                    cited_act_or_rule=act_name,
                    relation_type="READ_WITH",
                ))

        # 7. General References (fall-through for other cited GO numbers)
        for match in cls.HINDI_GENERAL_REF.finditer(text):
            raw = match.group(0).strip()
            num = cls._clean_order_num(match.group(1))
            dt = cls._parse_date_string(match.group(2)) if match.group(2) else None
            # Only add if not already captured by supersedes / continuation
            existing_matches = [k for k in seen_keys if k[1] == num]
            if num and not existing_matches:
                seen_keys.add(("REFERS_TO", num))
                citations.append(ParsedCitation(
                    raw_citation_text=raw,
                    cited_order_number=num,
                    cited_date=dt,
                    relation_type="REFERS_TO",
                ))

        return citations

    @staticmethod
    def _clean_order_num(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        clean = raw.strip().strip(",.;:")
        if len(clean) < 3 or not any(c.isdigit() for c in clean):
            return None
        return clean

    @classmethod
    def _parse_date_string(cls, text: Optional[str]) -> Optional[date]:
        if not text:
            return None
        t = text.strip().lower()

        # Check numeric format: DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
        num_m = re.search(r"\b(\d{1,2})[\.\-\/](\d{1,2})[\.\-\/](\d{4})\b", t)
        if num_m:
            try:
                return date(int(num_m.group(3)), int(num_m.group(2)), int(num_m.group(1)))
            except ValueError:
                pass

        # Check Hindi text format: e.g. "15 मार्च 2022" or "10 जनवरी, 2021"
        for h_month, m_num in HINDI_MONTHS.items():
            if h_month in text:
                m = re.search(rf"\b(\d{{1,2}})\s*{h_month},?\s*(\d{{4}})\b", text)
                if m:
                    try:
                        return date(int(m.group(2)), m_num, int(m.group(1)))
                    except ValueError:
                        pass

        # Check English text format: e.g. "15th March 2022" or "January 10, 2021"
        for e_month, m_num in ENGLISH_MONTHS.items():
            if e_month in t:
                m1 = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{e_month},?\s+(\d{{4}})\b", t)
                if m1:
                    try:
                        return date(int(m1.group(2)), m_num, int(m1.group(1)))
                    except ValueError:
                        pass
                m2 = re.search(rf"\b{e_month}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", t)
                if m2:
                    try:
                        return date(int(m2.group(2)), m_num, int(m2.group(1)))
                    except ValueError:
                        pass

        return None
