"""Unit tests for Phase 04 Model Governance and Formal Promotion Workflow."""

import pytest
from adam.db.models import ModelPromotionRecord, ModelArtifactRecord
from adam.model.governance import ModelGovernance
from adam.model.registry import ModelRegistry, QWEN3_4B_INSTRUCT, GEMMA_3_4B_IT
from adam.vocabularies import ModelStatus


def test_model_promotion_success(db_session):
    """Verify that an approved model meeting all benchmark gates is promoted."""
    registry = ModelRegistry(db_session)
    registry.seed_defaults()
    gov = ModelGovernance(db_session, registry)

    eval_result = gov.evaluate_and_promote(
        model_id=QWEN3_4B_INSTRUCT.id,
        promoted_by="chief_secretary_uk",
        authority_order_ref="UK/GOV/2024/PROM-QWEN-01",
        notes="Primary Mac pilot model promoted after passing all Phase 04 gates.",
        run_full_gold_set=False,  # Use benchmark verification
    )

    assert eval_result.gate_passed is True
    assert eval_result.decision == "PROMOTED"
    assert eval_result.license_approved is True
    assert eval_result.recall_at_10 >= 0.90
    assert eval_result.citation_page_precision >= 0.95
    assert eval_result.no_answer_refusal_rate == 1.00
    assert eval_result.acl_leak_count == 0
    assert eval_result.unanswerable_abstention_rate == 1.00
    assert eval_result.high_risk_compliance_rate == 1.00
    assert eval_result.hindi_review_passed is True
    assert eval_result.latency_p95_ms <= 5000.0
    assert eval_result.failures == []

    # Verify DB persistence
    prom_rec = db_session.query(ModelPromotionRecord).filter(
        ModelPromotionRecord.id == eval_result.promoted_record_id
    ).first()
    assert prom_rec is not None
    assert prom_rec.model_id == QWEN3_4B_INSTRUCT.id
    assert prom_rec.decision == "PROMOTED"

    # Verify model artifact status updated in DB
    model_rec = db_session.query(ModelArtifactRecord).filter(
        ModelArtifactRecord.id == QWEN3_4B_INSTRUCT.id
    ).first()
    assert model_rec.status == ModelStatus.PROMOTED.value


def test_gated_model_promotion_requires_legal_signoff(db_session):
    """Enforce: Gemma 3 4B is gated; legal/procurement review is required before selection."""
    registry = ModelRegistry(db_session)
    registry.seed_defaults()
    gov = ModelGovernance(db_session, registry)

    # 1. Attempting promotion with generic reference without legal signoff fails
    eval_fail = gov.evaluate_and_promote(
        model_id=GEMMA_3_4B_IT.id,
        promoted_by="engineer_test",
        authority_order_ref="ROUTINE-DEV-TEST-REF",
        run_full_gold_set=False,
    )
    assert eval_fail.gate_passed is False
    assert eval_fail.decision == "REJECTED"
    assert any("Legal/procurement signoff" in f for f in eval_fail.failures)

    # 2. Promoting with formal legal signoff succeeds
    eval_ok = gov.evaluate_and_promote(
        model_id=GEMMA_3_4B_IT.id,
        promoted_by="legal_remembrancer_uk",
        authority_order_ref="LEGAL-REVIEW-GAZETTE-2024-GEMMA-APPROVED",
        run_full_gold_set=False,
    )
    assert eval_ok.gate_passed is True
    assert eval_ok.decision == "PROMOTED"
    assert eval_ok.license_approved is True
