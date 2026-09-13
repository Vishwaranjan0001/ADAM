"""Unit tests for Phase 04 Read-Only Tool Execution and Security Guardrails."""

import pytest
from adam.agent.tools import ReadOnlyToolRegistry, ForbiddenToolError
from adam.db.models import Document, DocumentVersion, DocumentPage, TextBlock, Source
from adam.rag.models import UserContext
from adam.vocabularies import (
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    SourceStatus,
)


@pytest.fixture
def populated_tool_db(db_session):
    """Seed test documents and sources for tool execution tests."""
    source = Source(
        id="src_tools_test",
        name="Finance Test Portal",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Test Owner",
        owner_contact="test@uk.gov.in",
        written_authority_ref="AUTH-TOOL-TEST",
        access_classification=Classification.PUBLIC.value,
        status=SourceStatus.APPROVED.value,
    )
    db_session.add(source)

    doc = Document(
        id="doc_tools_test_01",
        source_id="src_tools_test",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Finance Rules Implementation Order 2024",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    db_session.add(doc)

    ver = DocumentVersion(
        id="ver_tools_test_01",
        document_id="doc_tools_test_01",
        source_url="https://ekosh.uk.gov.in/orders/fin_rules_2024.pdf",
        sha256="hash_tools_test_sha256_full",
        mime_type="application/pdf",
        byte_size=20480,
        original_object_key="originals/fin_rules.pdf",
    )
    db_session.add(ver)

    page = DocumentPage(
        id="page_tools_test_01_1",
        version_id="ver_tools_test_01",
        page_number=1,
        selected_text="Treasury payments shall adhere to Rule 14 of Financial Handbook.",
    )
    db_session.add(page)

    blk = TextBlock(
        id="blk_tools_test_01_1_1",
        page_id="page_tools_test_01_1",
        block_type="PARAGRAPH",
        text="Treasury payments shall adhere to Rule 14 of Financial Handbook.",
        bbox=[50.0, 100.0, 500.0, 140.0],
        reading_order=0,
    )
    db_session.add(blk)
    db_session.commit()
    return db_session


def test_allowed_read_only_tools(populated_tool_db):
    """Verify execution of the 3 allowed read-only tools."""
    user = UserContext(
        user_id="officer_qa",
        roles=["OFFICER"],
        department_id=DepartmentId.FINANCE_TREASURY.value,
        clearance_level=Classification.PUBLIC.value,
    )

    # 1. Tool: search
    res_search = ReadOnlyToolRegistry.execute(
        tool_name="search",
        arguments={"query": "Finance Rules Implementation", "top_k": 5},
        user_context=user,
        session=populated_tool_db,
    )
    assert "query" in res_search
    assert "passages" in res_search

    # 2. Tool: open_cited_source
    res_open = ReadOnlyToolRegistry.execute(
        tool_name="open_cited_source",
        arguments={"document_id": "doc_tools_test_01", "page_number": 1},
        user_context=user,
        session=populated_tool_db,
    )
    assert res_open["document_id"] == "doc_tools_test_01"
    assert res_open["title"] == "Finance Rules Implementation Order 2024"
    assert res_open["pdf_page_link"] == "https://ekosh.uk.gov.in/orders/fin_rules_2024.pdf#page=1"
    assert len(res_open["blocks"]) > 0
    assert res_open["blocks"][0]["bbox"] == [50.0, 100.0, 500.0, 140.0]

    # 3. Tool: list_authorised_collections
    res_list = ReadOnlyToolRegistry.execute(
        tool_name="list_authorised_collections",
        arguments={},
        user_context=user,
        session=populated_tool_db,
    )
    assert res_list["total_accessible_collections"] >= 1
    assert "FINANCE_TREASURY" in res_list["accessible_departments"]


def test_forbidden_tools_interception(populated_tool_db):
    """Enforce: 'No web browsing, emailing, editing records, procurement action, or database write tool is available'."""
    user = UserContext(user_id="test_user", clearance_level=Classification.PUBLIC.value)

    forbidden_list = [
        "web_browse",
        "browse_web",
        "fetch_url",
        "curl",
        "send_email",
        "email",
        "edit_record",
        "update_record",
        "delete_record",
        "write_record",
        "db_write",
        "procure_action",
        "procurement_action",
        "sanction_release",
        "run_bash",
        "execute_command",
        "modify_document",
    ]

    for tool_name in forbidden_list:
        with pytest.raises(ForbiddenToolError) as exc_info:
            ReadOnlyToolRegistry.execute(
                tool_name=tool_name,
                arguments={"target": "anything"},
                user_context=user,
                session=populated_tool_db,
            )
        assert "strictly forbidden" in str(exc_info.value)
        assert "read-only tools" in str(exc_info.value)


def test_unregistered_arbitrary_tool_rejection(populated_tool_db):
    """Verify that any unapproved tool outside the whitelist is blocked."""
    user = UserContext(user_id="test_user", clearance_level=Classification.PUBLIC.value)
    with pytest.raises(ForbiddenToolError):
        ReadOnlyToolRegistry.execute(
            tool_name="arbitrary_unregistered_tool",
            arguments={},
            user_context=user,
            session=populated_tool_db,
        )


def test_tool_definitions_schema():
    """Verify that get_tool_definitions exposes strictly the 3 allowed read-only tools."""
    tools = ReadOnlyToolRegistry.get_tool_definitions()
    assert len(tools) == 3
    tool_names = {t["name"] for t in tools}
    assert tool_names == {"search", "open_cited_source", "list_authorised_collections"}


def test_tool_cross_tenant_acl_enforcement(populated_tool_db):
    """Verify that open_cited_source strictly blocks cross-tenant access to INTERNAL documents."""
    from adam.db.models import Document, DocumentVersion, AccessGrant
    from adam.vocabularies import AccessAction

    # Create internal finance document
    doc_internal = Document(
        id="doc_internal_fin_999",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Confidential Departmental Audit Plan",
        classification=Classification.INTERNAL.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    populated_tool_db.add(doc_internal)
    populated_tool_db.commit()

    # 1. User with INTERNAL clearance but NO department must be DENIED access
    unassigned_user = UserContext(
        user_id="unassigned_officer",
        clearance_level=Classification.INTERNAL.value,
        department_id=None,
    )
    res_denied_1 = ReadOnlyToolRegistry.execute(
        tool_name="open_cited_source",
        arguments={"document_id": "doc_internal_fin_999"},
        user_context=unassigned_user,
        session=populated_tool_db,
    )
    assert "error" in res_denied_1
    assert "Access Denied" in res_denied_1["error"]

    # 2. User from RURAL_DEVELOPMENT must be DENIED access to FINANCE_TREASURY internal document
    other_dept_user = UserContext(
        user_id="rd_officer",
        clearance_level=Classification.INTERNAL.value,
        department_id=DepartmentId.RURAL_DEVELOPMENT.value,
    )
    res_denied_2 = ReadOnlyToolRegistry.execute(
        tool_name="open_cited_source",
        arguments={"document_id": "doc_internal_fin_999"},
        user_context=other_dept_user,
        session=populated_tool_db,
    )
    assert "error" in res_denied_2
    assert "Access Denied" in res_denied_2["error"]

    # 3. User with explicit AccessGrant MUST be GRANTED access
    grant = AccessGrant(
        subject_id="external_auditor",
        document_id="doc_internal_fin_999",
        action=AccessAction.READ.value,
    )
    populated_tool_db.add(grant)
    populated_tool_db.commit()

    granted_user = UserContext(
        user_id="external_auditor",
        clearance_level=Classification.PUBLIC.value,
    )
    res_granted = ReadOnlyToolRegistry.execute(
        tool_name="open_cited_source",
        arguments={"document_id": "doc_internal_fin_999"},
        user_context=granted_user,
        session=populated_tool_db,
    )
    assert "error" not in res_granted
    assert res_granted["document_id"] == "doc_internal_fin_999"
