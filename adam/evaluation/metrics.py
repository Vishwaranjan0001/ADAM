"""Extended benchmark evaluation metrics per Phase 09 specification.

Covers:
- Retrieval nDCG@k and Recall@k
- Citation precision and citation coverage
- Unsupported-claim rate
- Abstention precision, recall, and F1
- Latency percentiles (p50, p95, p99)
- OCR CER (Character Error Rate) and WER (Word Error Rate)
- User correction rate from feedback records
"""

import math
import unicodedata
from typing import List, Dict, Any, Optional


def compute_ndcg(
    retrieved_ids: List[str],
    ground_truth_relevance: Dict[str, int],
    k: int = 10,
) -> float:
    """Compute Normalized Discounted Cumulative Gain at rank k (nDCG@k).

    Args:
        retrieved_ids: Ordered list of retrieved document/chunk IDs.
        ground_truth_relevance: Mapping of document/chunk ID to relevance score (e.g., 0, 1, 2, 3).
        k: Cutoff rank.

    Returns:
        nDCG score between 0.0 and 1.0.
    """
    if not retrieved_ids or not ground_truth_relevance or k <= 0:
        return 0.0

    retrieved_k = retrieved_ids[:k]

    # Compute DCG@k
    dcg = 0.0
    for rank_idx, item_id in enumerate(retrieved_k):
        rel = ground_truth_relevance.get(item_id, 0)
        if rel > 0:
            dcg += (2**rel - 1) / math.log2(rank_idx + 2)

    # Compute Ideal DCG (IDCG@k)
    sorted_rels = sorted(ground_truth_relevance.values(), reverse=True)[:k]
    idcg = 0.0
    for rank_idx, rel in enumerate(sorted_rels):
        if rel > 0:
            idcg += (2**rel - 1) / math.log2(rank_idx + 2)

    if idcg == 0.0:
        return 1.0 if dcg == 0.0 else 0.0

    return dcg / idcg


def compute_citation_coverage(
    claims: List[str],
    evidence_passages: List[str],
) -> float:
    """Compute fraction of factual claims grounded in the citation evidence packet."""
    if not claims:
        return 1.0
    if not evidence_passages:
        return 0.0

    joined_evidence = " ".join(evidence_passages).lower()
    grounded_claims = 0

    for claim in claims:
        claim_clean = claim.strip().lower()
        if not claim_clean:
            continue
        # Extract meaningful tokens (length >= 4)
        tokens = [t for t in claim_clean.split() if len(t) >= 4]
        if not tokens:
            grounded_claims += 1
            continue
        # If at least 50% of substantial claim tokens match evidence, mark as covered
        matched = sum(1 for t in tokens if t in joined_evidence)
        if (matched / len(tokens)) >= 0.5:
            grounded_claims += 1

    return grounded_claims / len(claims)


def compute_unsupported_claim_rate(
    claims: List[str],
    evidence_passages: List[str],
) -> float:
    """Compute rate of hallucinated or unsupported claims (1.0 - coverage)."""
    coverage = compute_citation_coverage(claims, evidence_passages)
    return round(max(0.0, 1.0 - coverage), 4)


def compute_abstention_metrics(
    predictions: List[bool],
    ground_truth: List[bool],
) -> Dict[str, float]:
    """Compute Precision, Recall, F1, and Accuracy for abstention on unanswerable queries."""
    if len(predictions) != len(ground_truth):
        raise ValueError("predictions and ground_truth lists must have identical lengths")

    tp = sum(1 for p, g in zip(predictions, ground_truth) if p and g)
    fp = sum(1 for p, g in zip(predictions, ground_truth) if p and not g)
    fn = sum(1 for p, g in zip(predictions, ground_truth) if not p and g)
    tn = sum(1 for p, g in zip(predictions, ground_truth) if not p and not g)

    total = len(predictions)
    accuracy = (tp + tn) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if tp == 0 and fp == 0 else 0.0)
    recall = tp / (tp + fn) if (tp + fn) > 0 else (1.0 if tp == 0 and fn == 0 else 0.0)
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
    }


def compute_latency_percentiles(latencies_ms: List[float]) -> Dict[str, float]:
    """Compute p50, p90, p95, p99, and mean response latencies in milliseconds."""
    if not latencies_ms:
        return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "count": 0}

    sorted_lats = sorted(latencies_ms)
    n = len(sorted_lats)

    def _pct(p: float) -> float:
        idx = int(math.ceil((p / 100.0) * n)) - 1
        idx = max(0, min(idx, n - 1))
        return sorted_lats[idx]

    return {
        "p50": round(_pct(50.0), 2),
        "p90": round(_pct(90.0), 2),
        "p95": round(_pct(95.0), 2),
        "p99": round(_pct(99.0), 2),
        "mean": round(sum(sorted_lats) / n, 2),
        "min": round(sorted_lats[0], 2),
        "max": round(sorted_lats[-1], 2),
        "count": n,
    }


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate (WER) using Levenshtein distance over word tokens."""
    ref_words = reference.strip().split()
    hyp_words = hypothesis.strip().split()

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    r_len = len(ref_words)
    h_len = len(hyp_words)

    dp = [[0] * (h_len + 1) for _ in range(r_len + 1)]
    for i in range(r_len + 1):
        dp[i][0] = i
    for j in range(h_len + 1):
        dp[0][j] = j

    for i in range(1, r_len + 1):
        for j in range(1, h_len + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],      # deletion
                    dp[i][j - 1],      # insertion
                    dp[i - 1][j - 1],  # substitution
                )

    return round(dp[r_len][h_len] / r_len, 4)


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate (CER) using normalized Levenshtein distance."""
    ref_norm = unicodedata.normalize("NFC", reference.strip())
    hyp_norm = unicodedata.normalize("NFC", hypothesis.strip())

    if not ref_norm:
        return 0.0 if not hyp_norm else 1.0

    r_len = len(ref_norm)
    h_len = len(hyp_norm)

    dp = [[0] * (h_len + 1) for _ in range(r_len + 1)]
    for i in range(r_len + 1):
        dp[i][0] = i
    for j in range(h_len + 1):
        dp[0][j] = j

    for i in range(1, r_len + 1):
        for j in range(1, h_len + 1):
            if ref_norm[i - 1] == hyp_norm[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],
                    dp[i][j - 1],
                    dp[i - 1][j - 1],
                )

    return round(dp[r_len][h_len] / r_len, 4)


def compute_user_correction_rate(
    correction_records_count: int,
    total_chat_turns: int,
) -> float:
    """Compute user correction rate from feedback/correction records."""
    if total_chat_turns <= 0:
        return 0.0
    return round(min(1.0, correction_records_count / total_chat_turns), 4)
