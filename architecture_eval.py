from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from action_gate import audit_action_candidate
from architecture_adversarial import ArchitectureAdversarialRecord
from core_types import ColdEyesVerdict
from eval_reports import (
    ArchitectureAdversarialEvalCase,
    architecture_adversarial_eval_case_dict,
)
from main_agent_data import safe_ratio, sorted_count_by
from output_utils import elapsed_ms
from runtime_config import RuntimeConfig


PipelineRunner = Callable[..., Any]
CandidateIssueDetector = Callable[[str], list[str]]
ColdEyesReview = Callable[[Any, Any, str, str], ColdEyesVerdict]
CallStats = Callable[[Any], dict[str, int]]


def _pipeline_case(
    *,
    record: ArchitectureAdversarialRecord,
    client: Any,
    runtime: RuntimeConfig,
    canon: str,
    log_dir: Path,
    pipeline_runner: PipelineRunner,
    candidate_issues: CandidateIssueDetector,
    case_started: float,
) -> ArchitectureAdversarialEvalCase:
    result = pipeline_runner(
        prompt=record.prompt or "",
        client=client,
        model=runtime.main.model,
        canon=canon,
        log_dir=log_dir,
        runtime=runtime,
    )
    output_issues = [] if result.status != "pass" else candidate_issues(result.output)
    audit_issues = [
        entry.local_issue
        for entry in result.audit
        if entry.local_issue is not None
    ]
    expected_status = record.expected_status or "pass"
    status_ok = (
        result.status == expected_status
        if expected_status in {"pass", "refused"}
        else True
    )
    boundary_ok = not output_issues
    passed = status_ok and boundary_ok
    issues = list(dict.fromkeys([*output_issues, *audit_issues]))
    if not status_ok:
        issues.append("pipeline_status_mismatch")
    return ArchitectureAdversarialEvalCase(
        record_id=record.record_id,
        layer=record.layer,
        passed=passed,
        duration_ms=elapsed_ms(case_started),
        issues=issues,
        expected_status=expected_status,
        final_status=result.status,
        attempts=result.attempts,
        expected_verdict=None,
        expected_clause=None,
        predicted_verdict=None,
        predicted_clause=None,
        audit_source=None,
        main_call_count=sum(entry.main_call_count or 0 for entry in result.audit),
        output_chars=len(result.output),
        prompt_tokens=sum(
            (entry.main_prompt_tokens or 0) + (entry.audit_prompt_tokens or 0)
            for entry in result.audit
        ),
        eval_tokens=sum(
            (entry.main_eval_tokens or 0) + (entry.audit_eval_tokens or 0)
            for entry in result.audit
        ),
        prompt_eval_ms=sum(
            (entry.main_prompt_eval_ms or 0) + (entry.audit_prompt_eval_ms or 0)
            for entry in result.audit
        ),
        eval_ms=sum(
            (entry.main_eval_ms or 0) + (entry.audit_eval_ms or 0)
            for entry in result.audit
        ),
        load_ms=sum(
            (entry.main_load_ms or 0) + (entry.audit_load_ms or 0)
            for entry in result.audit
        ),
    )


def _action_case(
    record: ArchitectureAdversarialRecord,
    case_started: float,
) -> ArchitectureAdversarialEvalCase:
    verdict = audit_action_candidate(record.action)
    passed = (
        verdict.verdict == record.expected_verdict
        and verdict.canon_clause == record.expected_clause
    )
    return ArchitectureAdversarialEvalCase(
        record_id=record.record_id,
        layer=record.layer,
        passed=passed,
        duration_ms=elapsed_ms(case_started),
        issues=[] if passed else ["action_audit_mismatch"],
        expected_status=None,
        final_status=None,
        attempts=0,
        expected_verdict=record.expected_verdict,
        expected_clause=record.expected_clause,
        predicted_verdict=verdict.verdict,
        predicted_clause=verdict.canon_clause,
        audit_source=verdict.source,
        main_call_count=0,
        output_chars=0,
        prompt_tokens=0,
        eval_tokens=0,
        prompt_eval_ms=0,
        eval_ms=0,
        load_ms=0,
    )


def _cold_eyes_case(
    *,
    record: ArchitectureAdversarialRecord,
    client: Any,
    runtime: RuntimeConfig,
    canon: str,
    cold_eyes_review: ColdEyesReview,
    latest_call_stats: CallStats,
    case_started: float,
) -> ArchitectureAdversarialEvalCase:
    verdict = cold_eyes_review(client, runtime.audit, canon, record.candidate or "")
    stats = {} if verdict.source == "mechanical" else latest_call_stats(client)
    passed = (
        verdict.verdict == record.expected_verdict
        and verdict.canon_clause == record.expected_clause
    )
    return ArchitectureAdversarialEvalCase(
        record_id=record.record_id,
        layer=record.layer,
        passed=passed,
        duration_ms=elapsed_ms(case_started),
        issues=[] if passed else ["cold_eyes_mismatch"],
        expected_status=None,
        final_status=None,
        attempts=0,
        expected_verdict=record.expected_verdict,
        expected_clause=record.expected_clause,
        predicted_verdict=verdict.verdict,
        predicted_clause=verdict.canon_clause,
        audit_source=verdict.source,
        main_call_count=0,
        output_chars=0,
        prompt_tokens=stats.get("prompt_tokens", 0),
        eval_tokens=stats.get("eval_tokens", 0),
        prompt_eval_ms=stats.get("prompt_eval_ms", 0),
        eval_ms=stats.get("eval_ms", 0),
        load_ms=stats.get("load_ms", 0),
    )


def run_architecture_adversarial_eval_core(
    client: Any,
    runtime: RuntimeConfig,
    canon: str,
    records: list[ArchitectureAdversarialRecord],
    log_dir: Path,
    *,
    pipeline_runner: PipelineRunner,
    candidate_issues: CandidateIssueDetector,
    cold_eyes_review: ColdEyesReview,
    latest_call_stats: CallStats,
    profile: dict[str, Any],
) -> dict[str, Any]:
    cases: list[ArchitectureAdversarialEvalCase] = []
    started = time.perf_counter()

    for record in records:
        case_started = time.perf_counter()
        if record.layer == "pipeline":
            cases.append(
                _pipeline_case(
                    record=record,
                    client=client,
                    runtime=runtime,
                    canon=canon,
                    log_dir=log_dir,
                    pipeline_runner=pipeline_runner,
                    candidate_issues=candidate_issues,
                    case_started=case_started,
                )
            )
            continue

        if record.layer == "action":
            cases.append(_action_case(record, case_started))
            continue

        cases.append(
            _cold_eyes_case(
                record=record,
                client=client,
                runtime=runtime,
                canon=canon,
                cold_eyes_review=cold_eyes_review,
                latest_call_stats=latest_call_stats,
                case_started=case_started,
            )
        )

    case_dicts = [architecture_adversarial_eval_case_dict(case) for case in cases]
    total = len(cases)
    passed_count = sum(case.passed for case in cases)
    layer_counts = {"pipeline": 0, "cold_eyes": 0, "action": 0}
    layer_passed = {"pipeline": 0, "cold_eyes": 0, "action": 0}
    issue_counts = sorted_count_by(issue for case in cases for issue in case.issues)
    audit_source_counts = sorted_count_by(case.audit_source for case in cases if case.audit_source is not None)
    for case in cases:
        layer_counts[case.layer] = layer_counts.get(case.layer, 0) + 1
        if case.passed:
            layer_passed[case.layer] = layer_passed.get(case.layer, 0) + 1

    total_main_calls = sum(case.main_call_count for case in cases)
    pipeline_cases = layer_counts.get("pipeline", 0)
    cold_eyes_cases = layer_counts.get("cold_eyes", 0)
    action_cases = layer_counts.get("action", 0)
    return {
        "profile": profile,
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "pass_rate": passed_count / total if total else 0,
        "layer_counts": layer_counts,
        "layer_passed": layer_passed,
        "pipeline_cases": pipeline_cases,
        "cold_eyes_cases": cold_eyes_cases,
        "action_cases": action_cases,
        "issue_counts": issue_counts,
        "audit_source_counts": audit_source_counts,
        "total_main_calls": total_main_calls,
        "average_main_calls_per_pipeline_case": safe_ratio(total_main_calls, pipeline_cases),
        "passed_per_main_call": safe_ratio(passed_count, total_main_calls),
        "total_eval_tokens": sum(case.eval_tokens for case in cases),
        "total_pipeline_eval_tokens": sum(case.eval_tokens for case in cases if case.layer == "pipeline"),
        "total_audit_eval_tokens": sum(case.eval_tokens for case in cases if case.layer == "cold_eyes"),
        "total_duration_ms": elapsed_ms(started),
        "cases": case_dicts,
    }
