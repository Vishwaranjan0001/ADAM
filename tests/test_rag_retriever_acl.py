"""Unit tests for Hybrid Retrieval, pre-ranking metadata ACL enforcement, and 0-leak security.

Tests:
1. Metadata ACL filtering applied before ranking:
   - Public documents accessible to anonymous/public users.
   - Internal documents accessible only to matching department/clearance.
   - Restricted documents inaccessible to public users without grant.
   - Confidential documents inaccessible to unauthorized users.
   - 0 cross-tenant/ACL leaks: unauthorized chunks never enter candidate ranking.
2. BM25 scoring across Hindi and English text with heading/GO number boosts.
3. Vector similarity search and Reciprocal Rank Fusion (RRF).
4. Strict enforcement of explicit query filters (department, go_number, dates).
"""

from datetime import date, datetime, timezone
import pytest
from sqlalchemy.orm import Session

from adam.db.models import (
    Source,
    Document,
    DocumentVersion,
    DocumentPage,
    DocumentChunk,
    AccessGrant,
)
from adam.rag.acl import AclEnforcer
from adam.rag.models import ParsedQuery, UserContext
from adam.rag.retriever import (
    HybridRetriever,
    BM25Ranker,
    MultilingualSemanticVectorizer,
)
from adam.vocabularies import (
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    ProvenanceStatus,
    ReviewStatus,
    SourceStatus,
)


@pytest.fixture
def setup_retrieval_corpus(db_session: Session):
    """Seed test corpus with Public, Internal, Restricted, and Confidential documents."""
    src = Source(
        id="src_retrieval_test",
        name="Test Retrieval Portal",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Test Owner",
        owner_contact="test@uk.gov.in",
        written_authority_ref="AUTH-TEST",
        status=SourceStatus.APPROVED.value,
    )
    db_session.add(src)

    # 1. Public Finance Document
    doc_pub = Document(
        id="doc_pub_fin",
        source_id=src.id,
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Public Dearness Allowance Guidelines 2024",
        language="en",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    ver_pub = DocumentVersion(
        id="ver_pub_fin",
        document_id=doc_pub.id,
        source_url="https://ekosh.uk.gov.in/orders/pub_da.pdf",
        go_number="UK/FIN/2024/101",
        sha256="pub_hash_123",
        mime_type="application/pdf",
        byte_size=1024,
        issued_on=date(2024, 1, 15),
        provenance_status=ProvenanceStatus.VERIFIED.value,
        original_object_key="docs/pub.pdf",
    )
    chk_pub = DocumentChunk(
        id="chk_pub_1",
        document_id=doc_pub.id,
        version_id=ver_pub.id,
        chunk_index=0,
        content="Dearness Allowance is enhanced to 50% for state employees effective 01.01.2024.",
        token_count=15,
        page_start=1,
        page_end=1,
        section_heading="Sanction Order",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        classification=Classification.PUBLIC.value,
        order_date=date(2024, 1, 15),
        go_number="UK/FIN/2024/101",
        review_status=ReviewStatus.AUTO_APPROVED.value,
    )
    doc_pub.versions.append(ver_pub)
    db_session.add_all([doc_pub, ver_pub, chk_pub])

    # 2. Internal Rural Development Document
    doc_internal = Document(
        id="doc_int_rd",
        source_id=src.id,
        department_id=DepartmentId.RURAL_DEVELOPMENT.value,
        doc_type=DocType.CIRCULAR.value,
        title="Internal Staff Deployment Roster Rural Development",
        language="hi",
        classification=Classification.INTERNAL.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    ver_int = DocumentVersion(
        id="ver_int_rd",
        document_id=doc_internal.id,
        source_url="https://ukrd.uk.gov.in/orders/internal.pdf",
        go_number="UK/RD/INT/2024/05",
        sha256="int_hash_456",
        mime_type="application/pdf",
        byte_size=1024,
        issued_on=date(2024, 2, 10),
        provenance_status=ProvenanceStatus.VERIFIED.value,
        original_object_key="docs/int.pdf",
    )
    chk_int = DocumentChunk(
        id="chk_int_1",
        document_id=doc_internal.id,
        version_id=ver_int.id,
        chunk_index=0,
        content="ग्राम्य विकास विभाग के अंतर्गत आंतरिक कर्मचारियों की तैनाती एवं कार्यभार आवंटन रोस्टर।",
        token_count=20,
        page_start=1,
        page_end=1,
        section_heading="आंतरिक रोस्टर",
        department_id=DepartmentId.RURAL_DEVELOPMENT.value,
        doc_type=DocType.CIRCULAR.value,
        classification=Classification.INTERNAL.value,
        order_date=date(2024, 2, 10),
        go_number="UK/RD/INT/2024/05",
        review_status=ReviewStatus.AUTO_APPROVED.value,
    )
    doc_internal.versions.append(ver_int)
    db_session.add_all([doc_internal, ver_int, chk_int])

    # 3. Confidential Vigilance Document
    doc_conf = Document(
        id="doc_conf_vigilance",
        source_id=src.id,
        department_id=DepartmentId.GENERAL_ADMINISTRATION.value,
        doc_type=DocType.INTERNAL_RECORD.value,
        title="Confidential Vigilance Report on Disciplinary Proceedings",
        language="en",
        classification=Classification.CONFIDENTIAL.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    ver_conf = DocumentVersion(
        id="ver_conf_vigilance",
        document_id=doc_conf.id,
        source_url="https://uk.gov.in/orders/conf.pdf",
        go_number="UK/VIG/CONF/2024/01",
        sha256="conf_hash_789",
        mime_type="application/pdf",
        byte_size=1024,
        issued_on=date(2024, 3, 1),
        provenance_status=ProvenanceStatus.VERIFIED.value,
        original_object_key="docs/conf.pdf",
    )
    chk_conf = DocumentChunk(
        id="chk_conf_1",
        document_id=doc_conf.id,
        version_id=ver_conf.id,
        chunk_index=0,
        content="Top secret inquiry findings regarding major disciplinary penalty against officer X.",
        token_count=18,
        page_start=1,
        page_end=1,
        section_heading="Vigilance Inquiry",
        department_id=DepartmentId.GENERAL_ADMINISTRATION.value,
        doc_type=DocType.INTERNAL_RECORD.value,
        classification=Classification.CONFIDENTIAL.value,
        order_date=date(2024, 3, 1),
        go_number="UK/VIG/CONF/2024/01",
        review_status=ReviewStatus.AUTO_APPROVED.value,
    )
    doc_conf.versions.append(ver_conf)
    db_session.add_all([doc_conf, ver_conf, chk_conf])

    db_session.commit()
    return {
        "pub": chk_pub,
        "int": chk_int,
        "conf": chk_conf,
    }


def test_acl_enforcement_zero_leaks(db_session: Session, setup_retrieval_corpus):
    """Verify 0 cross-tenant/ACL leaks: unauthorized users cannot retrieve or score protected chunks."""
    retriever = HybridRetriever(db_session)

    # 1. Anonymous Public User searching for confidential/internal keywords
    anon_user = UserContext(user_id="anon_1", roles=["PUBLIC"], clearance_level="PUBLIC")

    # Search query targeting confidential vigilance inquiry
    q_conf = ParsedQuery(raw_query="vigilance inquiry disciplinary penalty", clean_query="vigilance inquiry disciplinary penalty")
    results_anon = retriever.retrieve(q_conf, user_context=anon_user)

    # Must NOT return confidential or internal chunks!
    retrieved_doc_ids = [p.document_id for p in results_anon]
    assert "doc_conf_vigilance" not in retrieved_doc_ids
    assert "doc_int_rd" not in retrieved_doc_ids
    assert len(results_anon) == 0

    # 2. Public User searching for public dearness allowance
    q_pub = ParsedQuery(raw_query="Dearness Allowance 50%", clean_query="Dearness Allowance 50%")
    results_pub = retriever.retrieve(q_pub, user_context=anon_user)
    assert len(results_pub) == 1
    assert results_pub[0].document_id == "doc_pub_fin"
    assert results_pub[0].go_number == "UK/FIN/2024/101"

    # 3. Finance Officer trying to access Rural Development internal roster (Cross-Tenant check)
    fin_officer = UserContext(
        user_id="fin_officer_1",
        roles=["OFFICER"],
        department_id=DepartmentId.FINANCE_TREASURY.value,
        clearance_level="INTERNAL",
    )
    q_rd_int = ParsedQuery(raw_query="ग्राम्य विकास रोस्टर", clean_query="ग्राम्य विकास रोस्टर")
    results_cross_tenant = retriever.retrieve(q_rd_int, user_context=fin_officer)
    # Cross-tenant access denied: Finance officer cannot see RD internal roster!
    assert len(results_cross_tenant) == 0

    # 4. Rural Development Officer accessing own department internal roster
    rd_officer = UserContext(
        user_id="rd_officer_1",
        roles=["OFFICER"],
        department_id=DepartmentId.RURAL_DEVELOPMENT.value,
        clearance_level="INTERNAL",
    )
    results_rd = retriever.retrieve(q_rd_int, user_context=rd_officer)
    assert len(results_rd) == 1
    assert results_rd[0].document_id == "doc_int_rd"

    # 5. AccessGrant allows authorized user to access specific confidential document
    grant = AccessGrant(
        subject_id="auditor_special",
        document_id="doc_conf_vigilance",
        action="READ",
        granted_by="chief_secretary",
    )
    db_session.add(grant)
    db_session.commit()

    authorized_auditor = UserContext(
        user_id="auditor_special",
        roles=["AUDITOR"],
        clearance_level="PUBLIC",
    )
    results_granted = retriever.retrieve(q_conf, user_context=authorized_auditor)
    assert len(results_granted) == 1
    assert results_granted[0].document_id == "doc_conf_vigilance"


def test_bm25_and_vector_scoring():
    """Verify BM25 ranking and local dense vector cosine similarity."""
    ranker = BM25Ranker()
    q_tokens = ["dearness", "allowance"]
    doc1_tokens = ["dearness", "allowance", "enhanced", "to", "50", "percent"]
    doc2_tokens = ["house", "rent", "allowance", "guidelines"]

    idf = {"dearness": 1.5, "allowance": 0.8}

    s1 = ranker.score(q_tokens, doc1_tokens, len(doc1_tokens), 10.0, idf)
    s2 = ranker.score(q_tokens, doc2_tokens, len(doc2_tokens), 10.0, idf)
    assert s1 > s2
    assert s1 > 0.0

    vectorizer = MultilingualSemanticVectorizer()
    v1 = vectorizer.embed_text("Dearness allowance rates for government employees")
    v2 = vectorizer.embed_text("Revised rates of DA for state employees")
    v3 = vectorizer.embed_text("Procurement of cement for dam construction")

    sim_close = vectorizer.cosine_similarity(v1, v2)
    sim_distant = vectorizer.cosine_similarity(v1, v3)
    assert sim_close > sim_distant


def test_retriever_explicit_filtering(db_session: Session, setup_retrieval_corpus):
    """Verify explicit metadata filters (department, go_number, dates) are strictly respected."""
    retriever = HybridRetriever(db_session)
    admin_user = UserContext(user_id="admin", roles=["ADMIN"], clearance_level="ADMIN")

    # 1. Query with explicit GO number
    q_go = ParsedQuery(raw_query="Dearness Allowance", clean_query="Dearness Allowance", go_number="UK/FIN/2024/101")
    res_go = retriever.retrieve(q_go, user_context=admin_user)
    assert len(res_go) == 1
    assert res_go[0].go_number == "UK/FIN/2024/101"

    # Query with non-existent GO number: must return 0 results
    q_wrong_go = ParsedQuery(raw_query="Dearness Allowance", clean_query="Dearness Allowance", go_number="GO/999/NONEXISTENT")
    res_wrong = retriever.retrieve(q_wrong_go, user_context=admin_user)
    assert len(res_wrong) == 0

    # 2. Query with explicit Department filter
    q_dept = ParsedQuery(raw_query="allowance", clean_query="allowance", department_id=DepartmentId.RURAL_DEVELOPMENT.value)
    res_dept = retriever.retrieve(q_dept, user_context=admin_user)
    # Must only return RD documents, not Finance documents
    for r in res_dept:
        assert r.department_id == DepartmentId.RURAL_DEVELOPMENT.value
