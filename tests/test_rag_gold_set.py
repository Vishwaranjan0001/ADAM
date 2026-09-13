"""Pilot Gate Evaluation Test Suite executing >=200 Hindi and English officer queries.

Per Phase 03 Acceptance Criteria:
- Build a gold set of >=200 Hindi/English officer questions, including known-answer,
  no-answer, amendments, conflicting documents and ACL-denied cases.
- Pilot gate:
  - >=90% recall@10 for answer-bearing queries
  - >=95% citation page precision
  - 100% tested no-answer cases refuse unsupported claims
  - 0 cross-tenant/ACL leaks
- Measure by department and language.
"""

import pytest
from sqlalchemy.orm import Session

from adam.rag.evaluation import populate_eval_corpus, evaluate_gold_set
from adam.rag.gold_set import generate_gold_questions


@pytest.fixture(scope="module")
def eval_db_session():
    """Module-scoped database session populated with the gold evaluation corpus."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from adam.db.models import Base

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()

    # Populate evaluation corpus
    populate_eval_corpus(session)

    try:
        yield session
    finally:
        session.close()


def test_gold_dataset_scale_and_diversity():
    """Verify that the gold set meets or exceeds the 200 questions requirement and is diverse."""
    questions = generate_gold_questions()
    assert len(questions) >= 200, f"Expected >= 200 questions, got {len(questions)}"

    # Check categories
    categories = {q["category"] for q in questions}
    assert "known_answer" in categories
    assert "no_answer" in categories
    assert "amendment" in categories
    assert "conflicting_docs" in categories
    assert "acl_denied" in categories

    # Check languages
    languages = {q["language"] for q in questions}
    assert "en" in languages
    assert "hi" in languages

    hi_count = sum(1 for q in questions if q["language"] == "hi")
    en_count = sum(1 for q in questions if q["language"] == "en")
    assert hi_count >= 80, f"Expected >= 80 Hindi questions, got {hi_count}"
    assert en_count >= 80, f"Expected >= 80 English questions, got {en_count}"


def test_pilot_gate_evaluation(eval_db_session: Session):
    """Execute complete gold set evaluation and assert all pilot gate acceptance criteria."""
    scorecard = evaluate_gold_set(eval_db_session)

    # 1. Total questions evaluated
    assert scorecard.total_queries >= 200

    # 2. Gate 1: Recall@10 >= 90% for answer-bearing queries
    assert scorecard.recall_at_10 >= 0.90, (
        f"Recall@10 failed: {scorecard.recall_at_10 * 100:.2f}% (Target: >= 90%)"
    )

    # 3. Gate 2: Citation Page Precision >= 95%
    assert scorecard.citation_page_precision >= 0.95, (
        f"Citation page precision failed: {scorecard.citation_page_precision * 100:.2f}% (Target: >= 95%)"
    )

    # 4. Gate 3: 100% tested no-answer cases refuse unsupported claims
    assert scorecard.no_answer_refusal_rate >= 1.00, (
        f"No-answer refusal rate failed: {scorecard.no_answer_refusal_rate * 100:.2f}% (Target: 100%)"
    )

    # 5. Gate 4: 0 cross-tenant / ACL leaks
    assert scorecard.acl_leak_count == 0, (
        f"ACL leak count failed: {scorecard.acl_leak_count} unauthorized records leaked (Target: 0)"
    )

    # 6. Overall gate pass flag
    assert scorecard.gate_passed is True

    # 7. Measurement breakdown by department and language
    assert len(scorecard.by_department) >= 3
    assert "en" in scorecard.by_language
    assert "hi" in scorecard.by_language
    assert scorecard.by_language["en"]["accuracy"] >= 0.85
    assert scorecard.by_language["hi"]["accuracy"] >= 0.85
