from __future__ import annotations

import time
from typing import Any, Callable

from core_types import ColdEyesVerdict
from distill_data import DistillRecord
from eval_reports import DistillEvalCase, distill_eval_case_dict
from output_utils import elapsed_ms
from runtime_config import RoleRuntime


ColdEyesReview = Callable[[Any, RoleRuntime, str, str], ColdEyesVerdict]
CallStats = Callable[[Any], dict[str, int]]
ResponseFormatLabel = Callable[[str | dict[str, Any] | None], str | None]


def run_distill_eval_core(
    client: Any,
    runtime: RoleRuntime,
    canon: str,
    records: list[DistillRecord],
    *,
    cold_eyes_review: ColdEyesReview,
    latest_call_stats: CallStats,
    response_format_label: ResponseFormatLabel,
) -> dict[str, Any]:
    cases: list[DistillEvalCase] = []
    started = time.perf_counter()
    for record in records:
        case_started = time.perf_counter()
        verdict = cold_eyes_review(client, runtime, canon, record.candidate)
        stats = {} if verdict.source == "mechanical" else latest_call_stats(client)
        verdict_match = verdict.verdict == record.verdict
        exact_match = verdict_match and verdict.canon_clause == record.canon_clause
        cases.append(
            DistillEvalCase(
                record_id=record.record_id,
                expected_verdict=record.verdict,
                expected_clause=record.canon_clause,
                predicted_verdict=verdict.verdict,
                predicted_clause=verdict.canon_clause,
                audit_source=verdict.source,
                verdict_match=verdict_match,
                exact_match=exact_match,
                duration_ms=elapsed_ms(case_started),
                prompt_tokens=stats.get("prompt_tokens", 0),
                eval_tokens=stats.get("eval_tokens", 0),
                prompt_eval_ms=stats.get("prompt_eval_ms", 0),
                eval_ms=stats.get("eval_ms", 0),
                load_ms=stats.get("load_ms", 0),
            )
        )

    case_dicts = [distill_eval_case_dict(case) for case in cases]
    verdict_matches = sum(case.verdict_match for case in cases)
    exact_matches = sum(case.exact_match for case in cases)
    total = len(cases)
    mechanical_cases = sum(case.audit_source == "mechanical" for case in cases)
    mismatches = [
        {
            "id": case.record_id,
            "expected_verdict": case.expected_verdict,
            "expected_clause": case.expected_clause,
            "predicted_verdict": case.predicted_verdict,
            "predicted_clause": case.predicted_clause,
            "verdict_match": case.verdict_match,
        }
        for case in cases
        if not case.exact_match
    ]
    mismatch_counts_by_expected_clause = {"pass": 0, "C1": 0, "C2": 0, "C3": 0}
    source_counts_by_expected_clause = {
        "pass": {"mechanical": 0, "llm": 0, "cache": 0},
        "C1": {"mechanical": 0, "llm": 0, "cache": 0},
        "C2": {"mechanical": 0, "llm": 0, "cache": 0},
        "C3": {"mechanical": 0, "llm": 0, "cache": 0},
    }
    for case in cases:
        key = case.expected_clause or "pass"
        if case.audit_source.endswith("_cache"):
            source_counts_by_expected_clause[key]["cache"] += 1
        elif case.audit_source == "mechanical":
            source_counts_by_expected_clause[key]["mechanical"] += 1
        else:
            source_counts_by_expected_clause[key]["llm"] += 1
        if not case.exact_match:
            mismatch_counts_by_expected_clause[key] += 1
    return {
        "audit_model": runtime.model,
        "audit_options": runtime.options.payload(),
        "audit_no_think": runtime.no_think,
        "audit_response_format": response_format_label(runtime.response_format),
        "total": total,
        "verdict_matches": verdict_matches,
        "exact_matches": exact_matches,
        "partial_matches": verdict_matches - exact_matches,
        "verdict_misses": total - verdict_matches,
        "mechanical_cases": mechanical_cases,
        "llm_cases": total - mechanical_cases,
        "estimated_llm_audit_calls_saved": mechanical_cases,
        "mismatches": mismatches,
        "mismatch_counts_by_expected_clause": mismatch_counts_by_expected_clause,
        "source_counts_by_expected_clause": source_counts_by_expected_clause,
        "verdict_accuracy": verdict_matches / total if total else 0,
        "exact_accuracy": exact_matches / total if total else 0,
        "total_duration_ms": elapsed_ms(started),
        "cases": case_dicts,
    }
