"""Unit tests for RAG Generator, Citation Contract, Currency Banners, and Hallucination Controls.

Tests:
1. Citation contract exposes all mandatory fields:
   - document title, department, GO/gazette number, version/hash, issue date, page,
     section, source URL, retrieval timestamp, link to original PDF page, bbox, and legal disclaimer.
2. Currency banner logic:
   - Shows "Applicable status not conclusively determined" unless corpus has an approved
     relationship and effective-date record.
   - Never infers supersession from similar language alone.
3. Hallucination controls:
   - 0 evidence -> exact refusal: "I could not establish this from the approved repository."
     followed by search suggestions.
   - High-risk prompts (legal advice, sanction approval, eligibility, disciplinary action)
     produce an administrative research brief with "human authority required," never a definitive determination.
   - Citation validator checks material claims (dates, money, rule numbers, authorities) against evidence packet.
"""

from datetime import date
import pytest
from sqlalchemy.orm import Session

from adam.rag.citation import CitationBuilder
from adam.rag.evidence import EvidencePacketBuilder
from adam.rag.generator import RagGenerator, CitationValidator
from adam.rag.models import (
    ParsedQuery,
    EvidencePassage,
    EvidencePacket,
    UserContext,
)
from adam.vocabularies import DepartmentId, DocType


def test_citation_contract_compliance():
    """Verify that every citation conforms to the exact Phase 03 citation contract."""
    passage = EvidencePassage(
        chunk_id="chk_101",
        document_id="doc_fin_101",
        version_id="ver_fin_101",
        title="Sanction of Dearness Allowance 2024",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        page_start=2,
        page_end=2,
        section_heading="Payment Mode",
        content="Payment shall be processed via eKosh portal.",
        go_number="UK/FIN/2024/101",
        gazette_number="GAZ/2024/01",
        order_date=date(2024, 1, 15),
        source_url="https://ekosh.uk.gov.in/orders/da2024.pdf",
        sha256="hash_sha256_full_64_characters_long_string_representing_the_file",
        bbox_list=[[50.0, 100.0, 500.0, 150.0]],
        currency_status="CURRENT",
    )

    citation = CitationBuilder.build_citation(passage)

    # 1. Verification of all mandatory contract fields
    assert citation.document_title == "Sanction of Dearness Allowance 2024"
    assert citation.department == DepartmentId.FINANCE_TREASURY.value
    assert citation.go_number == "UK/FIN/2024/101"
    assert citation.gazette_number == "GAZ/2024/01"
    assert citation.version_hash.startswith("hash_sha256")
    assert citation.issue_date == "2024-01-15"
    assert citation.page == 2
    assert citation.section == "Payment Mode"
    assert citation.source_url == "https://ekosh.uk.gov.in/orders/da2024.pdf"
    assert citation.retrieval_timestamp is not None
    assert citation.pdf_page_link == "https://ekosh.uk.gov.in/orders/da2024.pdf#page=2"
    assert citation.bbox == [50.0, 100.0, 500.0, 150.0]
    assert citation.disclaimer == "A citation is a source pointer, not a claim of legal validity."

    # 2. Formatted Markdown presentation
    md = CitationBuilder.format_citation_markdown(citation, index=1)
    assert "[1] **Sanction of Dearness Allowance 2024**" in md
    assert "Page 2" in md
    assert "[View Original PDF Page](https://ekosh.uk.gov.in/orders/da2024.pdf#page=2)" in md
    assert citation.disclaimer in md


def test_currency_banner_uncertainty_requirement():
    """Verify currency banner requirement for amendments/repeals:
    'For amendments/repeals, show a currency banner: "Applicable status not conclusively determined"
    unless the corpus has an approved relationship and effective-date record. Never infer supersession
    from similar language alone.'
    """
    # Case A: Uncertain relationship (missing effective date or unapproved relationship)
    passage_uncertain = EvidencePassage(
        chunk_id="chk_old",
        document_id="doc_old",
        version_id="ver_old",
        title="Earlier Allowance Order 2021",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        page_start=1,
        page_end=1,
        section_heading="General",
        content="Dearness allowance is 28%.",
        currency_status="UNCERTAIN",
    )
    packet_uncertain = EvidencePacket(
        query=ParsedQuery(raw_query="DA rate", clean_query="DA rate"),
        passages=[passage_uncertain],
        currency_status="UNCERTAIN",
        currency_banner="Applicable status not conclusively determined",
    )
    citations = CitationBuilder.build_citations_from_packet(packet_uncertain)
    assert len(citations) == 1
    assert citations[0].currency_banner == "Applicable status not conclusively determined"

    # Case B: Approved relationship and effective-date record
    packet_approved = EvidencePacket(
        query=ParsedQuery(raw_query="DA rate", clean_query="DA rate"),
        passages=[passage_uncertain],
        currency_status="AMENDED",
        currency_banner="Approved amendment by GO UK/FIN/2024/101 effective 2024-01-01.",
    )
    citations_approved = CitationBuilder.build_citations_from_packet(packet_approved)
    assert citations_approved[0].currency_banner == "Approved amendment by GO UK/FIN/2024/101 effective 2024-01-01."


def test_zero_evidence_refusal_and_suggestions():
    """Verify hallucination control: 0 evidence produces exact refusal text and search suggestions."""
    generator = RagGenerator()

    empty_packet = EvidencePacket(
        query=ParsedQuery(raw_query="Nonexistent policy in Himachal", clean_query="Nonexistent policy in Himachal"),
        passages=[],
    )

    response = generator.generate(empty_packet)
    assert response.is_no_answer is True
    assert response.answer == "I could not establish this from the approved repository."
    assert len(response.citations) == 0
    assert len(response.search_suggestions) >= 3
    assert any("Uttarakhand" in s for s in response.search_suggestions)


def test_high_risk_research_brief():
    """Verify high-risk prompts produce research brief with 'human authority required'."""
    generator = RagGenerator()

    passage = EvidencePassage(
        chunk_id="chk_201",
        document_id="doc_201",
        version_id="ver_201",
        title="Sanction Powers of Departmental Heads",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.RULES.value,
        page_start=1,
        page_end=1,
        section_heading="Financial Limits",
        content="Head of Department may sanction expenditure up to Rs 25 Lakh for civil repair works.",
        go_number="UK/FIN/2023/50",
    )

    packet_high_risk = EvidencePacket(
        query=ParsedQuery(
            raw_query="Approve financial sanction of Rs 25 Lakh for repair work immediately.",
            clean_query="Approve financial sanction of Rs 25 Lakh for repair work immediately.",
            is_high_risk=True,
            high_risk_category="SANCTION_APPROVAL",
        ),
        passages=[passage],
    )

    response = generator.generate(packet_high_risk)
    assert response.is_high_risk is True
    assert response.is_research_brief is True
    # Mandatory notice: "human authority required"
    assert "human authority required" in response.answer.lower()
    assert "Research Brief" in response.answer
    assert "not a definitive legal or executive determination" in response.answer
    assert len(response.citations) == 1


def test_citation_validator_detects_hallucinations():
    """Verify that CitationValidator catches material claims (dates, amounts, rule numbers) not in evidence."""
    passage = EvidencePassage(
        chunk_id="chk_val",
        document_id="doc_val",
        version_id="ver_val",
        title="Sanction of Travel Allowance",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        page_start=1,
        page_end=1,
        section_heading="Rates",
        content="Daily allowance is fixed at Rs 500 per day for Group B officers effective 01/04/2023.",
        go_number="UK/FIN/2023/100",
    )
    packet = EvidencePacket(
        query=ParsedQuery(raw_query="TA rates", clean_query="TA rates"),
        passages=[passage],
    )

    # Valid grounded answer
    valid_answer = "Daily allowance is fixed at Rs 500 per day effective 01/04/2023 under UK/FIN/2023/100."
    passed_valid, errors_valid = CitationValidator.validate(valid_answer, packet)
    assert passed_valid is True
    assert len(errors_valid) == 0

    # Hallucinated answer with invented amounts and date
    hallucinated_answer = "Daily allowance is fixed at Rs 5,000 per day effective 15/08/2025 by the Governor."
    passed_fake, errors_fake = CitationValidator.validate(hallucinated_answer, packet)
    assert passed_fake is False
    assert len(errors_fake) >= 1
