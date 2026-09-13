"""Phase 09: Benchmark Evaluation Metrics Unit Test Suite.

Verifies:
- Retrieval nDCG@k
- Citation coverage and unsupported-claim rate
- Abstention metrics (precision, recall, F1)
- Latency percentiles (p50, p90, p95, p99)
- OCR Character Error Rate (CER) and Word Error Rate (WER)
- User correction rate calculation
"""

import pytest
from adam.evaluation.metrics import (
    compute_ndcg,
    compute_citation_coverage,
    compute_unsupported_claim_rate,
    compute_abstention_metrics,
    compute_latency_percentiles,
    character_error_rate,
    word_error_rate,
    compute_user_correction_rate,
)


def test_ndcg_computation():
    """Verify nDCG@k calculation with perfect ranking, inverted ranking, and empty inputs."""
    ground_truth = {"doc_a": 3, "doc_b": 2, "doc_c": 1, "doc_d": 0}

    # Perfect ranking -> nDCG should be 1.0
    perfect_ranking = ["doc_a", "doc_b", "doc_c", "doc_d"]
    assert compute_ndcg(perfect_ranking, ground_truth, k=4) == pytest.approx(1.0, abs=1e-3)

    # Inverted ranking -> nDCG should be strictly lower than 1.0
    imperfect_ranking = ["doc_c", "doc_d", "doc_b", "doc_a"]
    ndcg_imperfect = compute_ndcg(imperfect_ranking, ground_truth, k=4)
    assert 0.0 < ndcg_imperfect < 1.0

    # Empty inputs
    assert compute_ndcg([], ground_truth) == 0.0
    assert compute_ndcg(["doc_a"], {}) == 0.0


def test_citation_coverage_and_unsupported_rate():
    """Verify citation coverage and unsupported-claim rate."""
    evidence = [
        "The Governor approved Hill Compensatory Allowance at Rs 1800 per month for Category-A stations.",
        "The effective commencement date is 01 February 2026.",
    ]
    grounded_claims = [
        "Hill Compensatory Allowance is Rs 1800 per month.",
        "The allowance commences on 01 February 2026.",
    ]
    unsupported_claims = [
        "Hill Compensatory Allowance is Rs 1800 per month.",
        "The allowance commences on 01 February 2026.",
        "Free housing quarters are provided in Dehradun.",  # Hallucinated / unsupported
    ]

    # Grounded claims should yield 100% coverage and 0% unsupported rate
    cov_perfect = compute_citation_coverage(grounded_claims, evidence)
    assert cov_perfect == 1.0
    assert compute_unsupported_claim_rate(grounded_claims, evidence) == 0.0

    # One unsupported claim out of three -> ~66.7% coverage, ~33.3% unsupported
    cov_partial = compute_citation_coverage(unsupported_claims, evidence)
    assert 0.60 <= cov_partial <= 0.70
    assert compute_unsupported_claim_rate(unsupported_claims, evidence) > 0.30


def test_abstention_metrics():
    """Verify abstention precision, recall, and F1 calculation."""
    # Predictions: True = abstained (declared unanswerable), False = attempted answer
    # Ground truth: True = actually unanswerable, False = answerable
    predictions =  [True,  True,  False, False, True]
    ground_truth = [True,  False, False, True,  True]
    # TP: idx 0, 4 (2)
    # FP: idx 1 (1)
    # FN: idx 3 (1)
    # TN: idx 2 (1)

    metrics = compute_abstention_metrics(predictions, ground_truth)
    assert metrics["true_positives"] == 2
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 1
    assert metrics["true_negatives"] == 1
    assert metrics["precision"] == pytest.approx(2 / 3, abs=1e-3)
    assert metrics["recall"] == pytest.approx(2 / 3, abs=1e-3)
    assert metrics["f1"] == pytest.approx(2 / 3, abs=1e-3)


def test_latency_percentiles():
    """Verify p50, p90, p95, p99 latency computation."""
    latencies = [10.0 * i for i in range(1, 101)]  # 10 to 1000 ms

    p = compute_latency_percentiles(latencies)
    assert p["count"] == 100
    assert p["min"] == 10.0
    assert p["max"] == 1000.0
    assert p["p50"] == 500.0
    assert p["p90"] == 900.0
    assert p["p95"] == 950.0
    assert p["p99"] == 990.0


def test_cer_and_wer_metrics():
    """Verify Character Error Rate (CER) and Word Error Rate (WER) across bilingual text."""
    ref = "शासनादेश संख्या 8892 वित्त अनुभाग"
    hyp = "शासनादेश संख्या 8892 वित्त अनुभाग"
    assert character_error_rate(ref, hyp) == 0.0
    assert word_error_rate(ref, hyp) == 0.0

    # 1 word substituted out of 5
    hyp_sub = "शासनादेश संख्या 8892 गृह अनुभाग"
    assert word_error_rate(ref, hyp_sub) == pytest.approx(0.20, abs=1e-2)
    assert character_error_rate(ref, hyp_sub) > 0.0


def test_user_correction_rate():
    """Verify correction rate formula based on audit records."""
    assert compute_user_correction_rate(0, 100) == 0.0
    assert compute_user_correction_rate(5, 100) == 0.05
    assert compute_user_correction_rate(10, 0) == 0.0
