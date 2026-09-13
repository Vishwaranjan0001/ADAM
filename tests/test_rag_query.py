"""Unit tests for Query Understanding, explicit filter extraction, and high-risk intent detection.

Tests:
1. Extracts filters only when explicit (department, date, GO number, doc type).
2. Never hallucinates or assumes filters for generic queries.
3. Accurate date parsing: numeric DD/MM/YYYY, Hindi month names, English month names, financial years.
4. Detects high-risk categories:
   - LEGAL_ADVICE
   - SANCTION_APPROVAL
   - ELIGIBILITY
   - DISCIPLINARY_ACTION
5. Language detection (Hindi vs English).
"""

from datetime import date
from adam.rag.query import QueryUnderstanding
from adam.vocabularies import DepartmentId, DocType


def test_explicit_department_extraction():
    """Verify department filter is extracted ONLY when explicitly stated."""
    # Explicit Finance
    q1 = QueryUnderstanding.parse("What is the Finance Department guideline for travel allowance?")
    assert q1.department_id == DepartmentId.FINANCE_TREASURY.value

    # Explicit Rural Development (Hindi)
    q2 = QueryUnderstanding.parse("ग्राम्य विकास विभाग द्वारा मनरेगा की मजदूरी दर क्या निर्धारित की गई है?")
    assert q2.department_id == DepartmentId.RURAL_DEVELOPMENT.value

    # Explicit Audit Directorate
    q3 = QueryUnderstanding.parse("Directorate of Audit inspection schedule for Zila Panchayats.")
    assert q3.department_id == DepartmentId.AUDIT_DIRECTORATE.value

    # Explicit Board of Revenue
    q4 = QueryUnderstanding.parse("राजस्व परिषद द्वारा निर्विवाद दाखिल खारिज के निर्देश।")
    assert q4.department_id == DepartmentId.BOARD_OF_REVENUE.value

    # Generic query without explicit department: department_id MUST be None!
    q_generic = QueryUnderstanding.parse("What are the allowances sanctioned for government employees?")
    assert q_generic.department_id is None

    q_generic_hi = QueryUnderstanding.parse("कर्मचारियों हेतु अवकाश के सामान्य नियम क्या हैं?")
    assert q_generic_hi.department_id is None


def test_explicit_date_extraction():
    """Verify explicit date parsing across formats."""
    # Numeric date
    q1 = QueryUnderstanding.parse("Orders issued on 15/01/2024 regarding pension.")
    assert q1.exact_date == date(2024, 1, 15)

    # Hindi text date
    q2 = QueryUnderstanding.parse("दिनांक 25 मार्च 2024 को जारी शासनादेश दिखाइए।")
    assert q2.exact_date == date(2024, 3, 25)

    # English text date
    q3 = QueryUnderstanding.parse("Notifications published on 18th May 2023.")
    assert q3.exact_date == date(2023, 5, 18)

    # Financial year
    q4 = QueryUnderstanding.parse("Budget allocations for financial year 2023-24.")
    assert q4.date_from == date(2023, 4, 1)
    assert q4.date_to == date(2024, 3, 31)

    # Calendar year
    q5 = QueryUnderstanding.parse("Government orders issued in 2022.")
    assert q5.date_from == date(2022, 1, 1)
    assert q5.date_to == date(2022, 12, 31)

    # Generic query: no date
    q6 = QueryUnderstanding.parse("Guidelines for office staff attendance.")
    assert q6.exact_date is None
    assert q6.date_from is None
    assert q6.date_to is None


def test_explicit_go_number_extraction():
    """Verify explicit GO / order number filter extraction."""
    q1 = QueryUnderstanding.parse("What are the provisions in GO UK/FIN/2024/789?")
    assert q1.go_number == "UK/FIN/2024/789"

    q2 = QueryUnderstanding.parse("शासनादेश संख्या 101/2024 के अनुसार डीए की दर क्या है?")
    assert q2.go_number == "101/2024"

    q3 = QueryUnderstanding.parse("Details of Order No: UK/RD/2023/150.")
    assert q3.go_number == "UK/RD/2023/150"


def test_explicit_doc_type_extraction():
    """Verify explicit document type filter extraction."""
    q1 = QueryUnderstanding.parse("Find government order regarding house rent.")
    assert q1.doc_type == DocType.GO.value

    q2 = QueryUnderstanding.parse("उत्तराखण्ड पंचायती राज अधिनियम के नियम।")
    assert q2.doc_type == DocType.ACT.value

    q3 = QueryUnderstanding.parse("Service rules for secretariat assistants.")
    assert q3.doc_type == DocType.RULES.value

    q4 = QueryUnderstanding.parse("Office memorandum for holiday schedule.")
    assert q4.doc_type == DocType.CIRCULAR.value

    q5 = QueryUnderstanding.parse("Extraordinary gazette notification on land acquisition.")
    assert q5.doc_type == DocType.NOTIFICATION.value or q5.doc_type == DocType.GAZETTE.value


def test_high_risk_intent_detection():
    """Verify high-risk prompts trigger research brief flag and appropriate category."""
    # Legal Advice
    q_legal_1 = QueryUnderstanding.parse("Can I file a writ petition in court to challenge this seniority list?")
    assert q_legal_1.is_high_risk is True
    assert q_legal_1.high_risk_category == "LEGAL_ADVICE"

    q_legal_2 = QueryUnderstanding.parse("क्या मैं इस आदेश के विरुद्ध उच्च न्यायालय में रिट दायर कर सकता हूँ? विधिक राय दें।")
    assert q_legal_2.is_high_risk is True
    assert q_legal_2.high_risk_category == "LEGAL_ADVICE"

    # Sanction Approval
    q_sanc_1 = QueryUnderstanding.parse("Please approve financial sanction of Rs 50 Lakh for road repair.")
    assert q_sanc_1.is_high_risk is True
    assert q_sanc_1.high_risk_category == "SANCTION_APPROVAL"

    q_sanc_2 = QueryUnderstanding.parse("इस कार्य हेतु तत्काल वित्तीय स्वीकृति जारी करें।")
    assert q_sanc_2.is_high_risk is True
    assert q_sanc_2.high_risk_category == "SANCTION_APPROVAL"

    # Eligibility Determination
    q_elig_1 = QueryUnderstanding.parse("Am I eligible for family pension after 10 years of service?")
    assert q_elig_1.is_high_risk is True
    assert q_elig_1.high_risk_category == "ELIGIBILITY"

    q_elig_2 = QueryUnderstanding.parse("क्या संबंधित आवेदक इस पद हेतु पात्र है या नहीं, पात्रता निर्धारित करें?")
    assert q_elig_2.is_high_risk is True
    assert q_elig_2.high_risk_category == "ELIGIBILITY"

    # Disciplinary Action
    q_disc_1 = QueryUnderstanding.parse("Should the assistant engineer be suspended for procurement irregularities?")
    assert q_disc_1.is_high_risk is True
    assert q_disc_1.high_risk_category == "DISCIPLINARY_ACTION"

    q_disc_2 = QueryUnderstanding.parse("दोषी कर्मचारी को क्या दण्डित किया जाए एवं निलम्बित किया जाए?")
    assert q_disc_2.is_high_risk is True
    assert q_disc_2.high_risk_category == "DISCIPLINARY_ACTION"

    # Standard benign query
    q_normal = QueryUnderstanding.parse("What is the Dearness Allowance rate for state employees in 2024?")
    assert q_normal.is_high_risk is False
    assert q_normal.high_risk_category is None


def test_language_detection():
    """Verify language detection distinguishing English and Devanagari Hindi."""
    q_en = QueryUnderstanding.parse("Guidelines for submission of monthly expenditure reports.")
    assert q_en.detected_language == "en"

    q_hi = QueryUnderstanding.parse("राज्य कर्मचारियों हेतु महंगाई भत्ते की दर क्या है?")
    assert q_hi.detected_language == "hi"
