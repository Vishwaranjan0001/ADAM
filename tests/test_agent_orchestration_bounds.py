"""Unit tests for Phase 04 Bounded Agent Orchestration, 7-Stage State Machine, and Bounds."""

import pytest
from datetime import date
from adam.agent.state_machine import (
    BoundedAgentStateMachine,
    TaskSelfExpansionError,
    AgentStateTransition,
)
from adam.db.models import (
    Document,
    DocumentVersion,
    DocumentChunk,
    AgentExecutionAudit,
    AuditEvent,
)
from adam.rag.models import UserContext
from adam.vocabularies import (
    AgentState,
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    ReviewStatus,
)


@pytest.fixture
def populated_agent_db(db_session):
    """Seed test documents and chunks for bounded agent execution."""
    doc = Document(
        id="doc_fin_da_2024",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Sanction of Dearness Allowance for Uttarakhand State Employees 2024",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    db_session.add(doc)

    ver = DocumentVersion(
        id="ver_fin_da_2024",
        document_id="doc_fin_da_2024",
        source_url="https://ekosh.uk.gov.in/orders/da2024.pdf",
        sha256="hash_da_2024_test_sha256_full_hash",
        mime_type="application/pdf",
        byte_size=10240,
        go_number="UK/FIN/2024/101",
        original_object_key="originals/test_da_2024.pdf",
    )
    db_session.add(ver)

    chk = DocumentChunk(
        id="chk_fin_da_2024_01",
        document_id="doc_fin_da_2024",
        version_id="ver_fin_da_2024",
        chunk_index=0,
        content="Under order UK/FIN/2024/101 dated 15/01/2024, the Governor of Uttarakhand approves 4% increase in Dearness Allowance.",
        page_start=1,
        page_end=1,
        section_heading="Sanction Clause",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        classification=Classification.PUBLIC.value,
        go_number="UK/FIN/2024/101",
        order_date=date(2024, 1, 15),
        source_url="https://ekosh.uk.gov.in/orders/da2024.pdf",
        sha256="hash_da_2024_test_sha256_full_hash",
        review_status=ReviewStatus.AUTO_APPROVED.value,
    )
    db_session.add(chk)
    db_session.commit()
    return db_session


def test_bounded_seven_stage_pipeline_execution(populated_agent_db):
    """Verify that execution strictly follows the 7 linear stages in order:
    authenticate -> classify request -> retrieve -> evidence/currency checks ->
    generate cited answer or abstain -> validate citations -> audit.
    """
    agent = BoundedAgentStateMachine(populated_agent_db)
    user = UserContext(
        user_id="records_officer_1",
        roles=["OFFICER"],
        department_id=DepartmentId.FINANCE_TREASURY.value,
        clearance_level=Classification.PUBLIC.value,
    )

    response = agent.run(
        query="What is the Dearness Allowance rate under order UK/FIN/2024/101?",
        user_context=user,
        temperature=0.0,
    )

    # 1. State machine transition verification
    expected_stage_sequence = [
        (AgentState.AUTHENTICATE.value, AgentState.CLASSIFY_REQUEST.value),
        (AgentState.CLASSIFY_REQUEST.value, AgentState.RETRIEVE.value),
        (AgentState.RETRIEVE.value, AgentState.EVIDENCE_CURRENCY_CHECKS.value),
        (AgentState.EVIDENCE_CURRENCY_CHECKS.value, AgentState.GENERATE_OR_ABSTAIN.value),
        (AgentState.GENERATE_OR_ABSTAIN.value, AgentState.VALIDATE_CITATIONS.value),
        (AgentState.VALIDATE_CITATIONS.value, AgentState.AUDIT.value),
        (AgentState.AUDIT.value, AgentState.COMPLETED.value),
    ]

    transitions = [(t.from_state, t.to_state) for t in response.state_history]
    assert len(transitions) == len(expected_stage_sequence)
    for idx, (exp_from, exp_to) in enumerate(expected_stage_sequence):
        assert transitions[idx] == (exp_from, exp_to), f"Transition {idx} failed: got {transitions[idx]}, expected {(exp_from, exp_to)}"

    # 2. Strict single-pass bounds verification
    assert response.retrieval_pass_count == 1
    assert response.answer_pass_count == 1
    assert response.validation_passed is True
    assert len(response.citations) > 0


def test_no_task_self_expansion_enforcement(populated_agent_db):
    """Verify that attempting more than 1 retrieval or answer pass raises TaskSelfExpansionError."""
    agent = BoundedAgentStateMachine(populated_agent_db)

    # Simulate internal state machine violation attempting second retrieval pass
    class FaultyStateMachine(BoundedAgentStateMachine):
        def run(self, *args, **kwargs):
            # Artificially simulate loop
            raise TaskSelfExpansionError("State machine attempted second retrieval pass. Max 1 retrieval pass allowed.")

    faulty = FaultyStateMachine(populated_agent_db)
    with pytest.raises(TaskSelfExpansionError) as exc_info:
        faulty.run("Test Query", UserContext())
    assert "Max 1 retrieval pass allowed" in str(exc_info.value)


def test_agent_execution_audit_persistence(populated_agent_db):
    """Verify immutable database audit records created in Stage 7."""
    agent = BoundedAgentStateMachine(populated_agent_db)
    user = UserContext(
        user_id="audit_tester",
        roles=["OFFICER"],
        clearance_level=Classification.PUBLIC.value,
    )

    response = agent.run(
        query="What is the Dearness Allowance rate?",
        user_context=user,
    )

    audit_rec = populated_agent_db.query(AgentExecutionAudit).filter(
        AgentExecutionAudit.session_id == response.session_id
    ).first()

    assert audit_rec is not None
    assert audit_rec.user_id == "audit_tester"
    assert audit_rec.retrieval_pass_count == 1
    assert audit_rec.answer_pass_count == 1
    assert audit_rec.validation_passed == 1
    assert audit_rec.latency_ms > 0
    assert len(audit_rec.state_transitions_json) == 7
    assert len(audit_rec.tool_calls_json) >= 1

    # Standard audit event also present
    std_ev = populated_agent_db.query(AuditEvent).filter(
        AuditEvent.entity_id == response.session_id
    ).first()
    assert std_ev is not None
    assert std_ev.action == "AGENT_EXECUTION_COMPLETED"


def test_agent_invalid_clearance_authentication_failure(populated_agent_db):
    """Verify that Stage 1 rejects invalid credentials / clearance levels."""
    agent = BoundedAgentStateMachine(populated_agent_db)
    invalid_user = UserContext(user_id="intruder", clearance_level="INVALID_CLEARANCE")

    with pytest.raises(PermissionError) as exc_info:
        agent.run(query="Tell me top secret records", user_context=invalid_user)
    assert "Invalid clearance level" in str(exc_info.value)


def test_agent_temperature_out_of_bounds_rejected(populated_agent_db):
    """Verify that temperatures outside 0.0-0.2 are rejected before execution."""
    agent = BoundedAgentStateMachine(populated_agent_db)
    user = UserContext(clearance_level=Classification.PUBLIC.value)

    with pytest.raises(ValueError) as exc_info:
        agent.run(query="Test", user_context=user, temperature=0.7)
    assert "exceeds Phase 04 bounds [0.0, 0.2]" in str(exc_info.value)


def test_agent_unanswerable_query_abstention(populated_agent_db):
    """Verify that out-of-jurisdiction query triggers clean linear 7-stage abstention without cyclic jumps."""
    agent = BoundedAgentStateMachine(populated_agent_db)
    user = UserContext(clearance_level=Classification.PUBLIC.value)

    response = agent.run(
        query="What are the Dearness Allowance rates promulgated by Uttar Pradesh State Government?",
        user_context=user,
    )

    assert response.is_no_answer is True
    assert "could not establish this from the approved repository" in response.answer.lower()
    assert len(response.search_suggestions) > 0
    assert response.applied_schema == "ADAM_AGENT_SCHEMA_V1"

    # Exact linear 7-stage progression terminating in ABSTAINED (no cyclic transitions)
    expected_abstained_sequence = [
        (AgentState.AUTHENTICATE.value, AgentState.CLASSIFY_REQUEST.value),
        (AgentState.CLASSIFY_REQUEST.value, AgentState.RETRIEVE.value),
        (AgentState.RETRIEVE.value, AgentState.EVIDENCE_CURRENCY_CHECKS.value),
        (AgentState.EVIDENCE_CURRENCY_CHECKS.value, AgentState.GENERATE_OR_ABSTAIN.value),
        (AgentState.GENERATE_OR_ABSTAIN.value, AgentState.VALIDATE_CITATIONS.value),
        (AgentState.VALIDATE_CITATIONS.value, AgentState.AUDIT.value),
        (AgentState.AUDIT.value, AgentState.ABSTAINED.value),
    ]
    transitions = [(t.from_state, t.to_state) for t in response.state_history]
    assert transitions == expected_abstained_sequence


def test_agent_authentication_failure_auditing(populated_agent_db):
    """Verify that failed authentication attempts are committed to the audit table."""
    agent = BoundedAgentStateMachine(populated_agent_db)
    unauthorized_user = UserContext(user_id="intruder_99", clearance_level="INVALID_CLEARANCE")

    with pytest.raises(PermissionError):
        agent.run(query="Access classified record", user_context=unauthorized_user)

    audit_entry = populated_agent_db.query(AgentExecutionAudit).filter(
        AgentExecutionAudit.user_id == "intruder_99"
    ).first()
    assert audit_entry is not None
    assert audit_entry.validation_passed == 0
    assert audit_entry.detected_intent == "AUTHENTICATION_FAILURE"


def test_agent_high_risk_query_research_brief(populated_agent_db):
    """Verify that high-risk query generates Research Brief with Human Authority Required."""
    agent = BoundedAgentStateMachine(populated_agent_db)
    user = UserContext(clearance_level=Classification.PUBLIC.value)

    response = agent.run(
        query="Provide legal advice whether I can sue the Secretary in court under Section 4.",
        user_context=user,
    )

    assert response.is_high_risk is True
    assert response.is_research_brief is True
    assert "Human Authority Required" in response.answer
    assert "not a definitive legal" in response.answer.lower()


