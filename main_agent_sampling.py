from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core_types import SetupError
from main_agent_curation import run_main_limo_curate, run_main_mix_distill_curate
from main_agent_data import MainAgentRecord, safe_ratio, sorted_count_by
from output_utils import elapsed_ms, new_run_id
from runtime_config import RuntimeConfig
from training_data import (
    load_sft_rows_or_raise,
    training_data_quality_errors,
    training_data_quality_report,
)


CandidateIssues = Callable[[str, str | None, float | None], list[str]]
CandidateScore = Callable[[str, str], float]
GenerateMain = Callable[[Any, RuntimeConfig, MainAgentRecord], Any]
VerifierIssues = Callable[[str, dict[str, Any]], list[str]]


@dataclass(frozen=True)
class MainContrastCase:
    record_id: str
    category: str
    selected: bool
    score_gap: float
    expert_score: float
    amateur_score: float
    expert_clean: bool
    amateur_clean: bool
    expert_issues: list[str]
    amateur_issues: list[str]
    expert_main_calls: int
    amateur_main_calls: int
    expert_eval_tokens: int
    amateur_eval_tokens: int


@dataclass(frozen=True)
class MainR1SampleCase:
    record_id: str
    category: str
    sample_index: int
    accepted: bool
    reward: float
    issues: list[str]
    main_call_count: int
    eval_tokens: int


def main_contrast_candidate_issues(
    record: MainAgentRecord,
    candidate: str,
    max_length_ratio: float | None,
    candidate_issues: CandidateIssues,
    verifier_issues: VerifierIssues,
) -> list[str]:
    issues = candidate_issues(
        candidate,
        record.target_response,
        max_length_ratio,
    )
    issues.extend(verifier_issues(candidate, record.verifier))
    return list(dict.fromkeys(issues))


def main_contrast_candidate_score(
    user_prompt: str,
    candidate: str,
    issues: list[str],
    candidate_score: CandidateScore,
) -> float:
    return 1000.0 * len(issues) + candidate_score(user_prompt, candidate)


def main_contrast_case_dict(case: MainContrastCase) -> dict[str, Any]:
    return {
        "id": case.record_id,
        "category": case.category,
        "selected": case.selected,
        "score_gap": round(case.score_gap, 3),
        "expert_score": round(case.expert_score, 3),
        "amateur_score": round(case.amateur_score, 3),
        "expert_clean": case.expert_clean,
        "amateur_clean": case.amateur_clean,
        "expert_issues": case.expert_issues,
        "amateur_issues": case.amateur_issues,
        "expert_main_calls": case.expert_main_calls,
        "amateur_main_calls": case.amateur_main_calls,
        "expert_eval_tokens": case.expert_eval_tokens,
        "amateur_eval_tokens": case.amateur_eval_tokens,
    }


def main_contrast_export_row(
    record: MainAgentRecord,
    generation: Any,
    expert_profile: str,
    amateur_profile: str,
    score_gap: float,
    include_system: bool,
    system_prompt: str,
    verifier_labels: list[str],
) -> dict[str, Any]:
    messages = []
    if include_system:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(
        [
            {"role": "user", "content": record.prompt},
            {"role": "assistant", "content": generation.text},
        ]
    )
    return {
        "id": record.record_id,
        "category": record.category,
        "source": "expert_amateur_contrast",
        "split": "train_candidate",
        "verifier_labels": [
            "expert_clean",
            "amateur_worse",
            *verifier_labels,
        ],
        "expert_profile": expert_profile,
        "amateur_profile": amateur_profile,
        "score_gap": round(score_gap, 3),
        "messages": messages,
    }


def run_main_contrast_export_core(
    client: Any,
    expert_runtime: RuntimeConfig,
    amateur_runtime: RuntimeConfig,
    records: list[MainAgentRecord],
    output_file: Path,
    expert_profile: str,
    amateur_profile: str,
    *,
    generate_main: GenerateMain,
    candidate_issues: CandidateIssues,
    verifier_issues: VerifierIssues,
    candidate_score: CandidateScore,
    verifier_labels: Callable[[dict[str, Any]], list[str]],
    system_prompt: str,
    min_score_gap: float = 100.0,
    max_length_ratio: float | None = None,
    include_system: bool = True,
) -> dict[str, Any]:
    cases: list[MainContrastCase] = []
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()

    for record in records:
        expert_generation = generate_main(client, expert_runtime, record)
        amateur_generation = generate_main(client, amateur_runtime, record)

        expert_issues = main_contrast_candidate_issues(
            record,
            expert_generation.text,
            max_length_ratio,
            candidate_issues,
            verifier_issues,
        )
        amateur_issues = main_contrast_candidate_issues(
            record,
            amateur_generation.text,
            max_length_ratio,
            candidate_issues,
            verifier_issues,
        )
        expert_score = main_contrast_candidate_score(
            record.prompt,
            expert_generation.text,
            expert_issues,
            candidate_score,
        )
        amateur_score = main_contrast_candidate_score(
            record.prompt,
            amateur_generation.text,
            amateur_issues,
            candidate_score,
        )
        score_gap = amateur_score - expert_score
        selected = not expert_issues and score_gap >= min_score_gap

        case = MainContrastCase(
            record_id=record.record_id,
            category=record.category,
            selected=selected,
            score_gap=score_gap,
            expert_score=expert_score,
            amateur_score=amateur_score,
            expert_clean=not expert_issues,
            amateur_clean=not amateur_issues,
            expert_issues=expert_issues,
            amateur_issues=amateur_issues,
            expert_main_calls=expert_generation.call_count,
            amateur_main_calls=amateur_generation.call_count,
            expert_eval_tokens=expert_generation.stats.get("eval_tokens", 0),
            amateur_eval_tokens=amateur_generation.stats.get("eval_tokens", 0),
        )
        cases.append(case)
        if selected:
            row = main_contrast_export_row(
                record,
                expert_generation,
                expert_profile,
                amateur_profile,
                score_gap,
                include_system=include_system,
                system_prompt=system_prompt,
                verifier_labels=verifier_labels(record.verifier),
            )
            rows.append(row)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )

    case_dicts = [main_contrast_case_dict(case) for case in cases]
    selected_category_counts = sorted_count_by(case.category for case in cases if case.selected)
    return {
        "path": str(output_file),
        "expert_profile": expert_profile,
        "amateur_profile": amateur_profile,
        "expert_model": expert_runtime.main.model,
        "amateur_model": amateur_runtime.main.model,
        "records": len(records),
        "selected_records": len(rows),
        "selection_rate": safe_ratio(len(rows), len(records)),
        "min_score_gap": min_score_gap,
        "include_system": include_system,
        "max_length_ratio": max_length_ratio,
        "selected_category_counts": selected_category_counts,
        "total_expert_main_calls": sum(case.expert_main_calls for case in cases),
        "total_amateur_main_calls": sum(case.amateur_main_calls for case in cases),
        "total_eval_tokens": sum(case.expert_eval_tokens + case.amateur_eval_tokens for case in cases),
        "total_duration_ms": elapsed_ms(started),
        "cases": case_dicts,
    }


def render_main_contrast_export(data: dict[str, Any]) -> str:
    lines = [
        f"Main Agent contrast export: {data['path']}",
        f"Expert: {data['expert_profile']} ({data['expert_model']})",
        f"Amateur: {data['amateur_profile']} ({data['amateur_model']})",
        f"Records: {data['records']}",
        f"Selected: {data['selected_records']}",
        f"Selection rate: {data['selection_rate']:.3f}",
        f"Minimum score gap: {data['min_score_gap']}",
        f"Total expert calls: {data['total_expert_main_calls']}",
        f"Total amateur calls: {data['total_amateur_main_calls']}",
        f"Total eval tokens: {data['total_eval_tokens']}",
        f"Total ms: {data['total_duration_ms']}",
        "Selected categories:",
    ]
    if data["selected_category_counts"]:
        lines.extend(f"- {category}: {count}" for category, count in data["selected_category_counts"].items())
    else:
        lines.append("- none")
    return "\n".join(lines)


def main_r1_reward(issues: list[str]) -> float:
    return 1.0 if not issues else 0.0


def main_r1_sample_case_dict(case: MainR1SampleCase) -> dict[str, Any]:
    return {
        "id": case.record_id,
        "category": case.category,
        "sample_index": case.sample_index,
        "accepted": case.accepted,
        "reward": case.reward,
        "issues": case.issues,
        "main_call_count": case.main_call_count,
        "eval_tokens": case.eval_tokens,
    }


def main_r1_sample_export_row(
    record: MainAgentRecord,
    generation: Any,
    profile: str,
    sample_index: int,
    reward: float,
    include_system: bool,
    system_prompt: str,
    verifier_labels: list[str],
) -> dict[str, Any]:
    messages = []
    if include_system:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(
        [
            {"role": "user", "content": record.prompt},
            {"role": "assistant", "content": generation.text},
        ]
    )
    return {
        "id": f"{record.record_id}-sample-{sample_index}",
        "record_id": record.record_id,
        "category": record.category,
        "source": "r1_rejection_sampling",
        "split": "train_candidate",
        "verifier_labels": [
            "accepted_by_local_verifier",
            *verifier_labels,
        ],
        "profile": profile,
        "sample_index": sample_index,
        "reward": reward,
        "messages": messages,
    }


def run_main_r1_sample_export_core(
    client: Any,
    runtime: RuntimeConfig,
    records: list[MainAgentRecord],
    output_file: Path,
    profile: str,
    *,
    generate_main: GenerateMain,
    candidate_issues: CandidateIssues,
    verifier_issues: VerifierIssues,
    verifier_labels: Callable[[dict[str, Any]], list[str]],
    system_prompt: str,
    samples_per_record: int = 4,
    min_reward: float = 1.0,
    max_length_ratio: float | None = None,
    include_system: bool = True,
) -> dict[str, Any]:
    if samples_per_record < 1:
        raise SetupError("--samples-per-record must be at least 1.")
    if not 0 <= min_reward <= 1:
        raise SetupError("--min-reward must be between 0 and 1.")

    cases: list[MainR1SampleCase] = []
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()

    for record in records:
        for sample_index in range(1, samples_per_record + 1):
            generation = generate_main(client, runtime, record)
            issues = main_contrast_candidate_issues(
                record,
                generation.text,
                max_length_ratio,
                candidate_issues,
                verifier_issues,
            )
            reward = main_r1_reward(issues)
            accepted = reward >= min_reward
            case = MainR1SampleCase(
                record_id=record.record_id,
                category=record.category,
                sample_index=sample_index,
                accepted=accepted,
                reward=reward,
                issues=issues,
                main_call_count=generation.call_count,
                eval_tokens=generation.stats.get("eval_tokens", 0),
            )
            cases.append(case)
            if accepted:
                rows.append(
                    main_r1_sample_export_row(
                        record,
                        generation,
                        profile=profile,
                        sample_index=sample_index,
                        reward=reward,
                        include_system=include_system,
                        system_prompt=system_prompt,
                        verifier_labels=verifier_labels(record.verifier),
                    )
                )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )

    accepted_cases = [case for case in cases if case.accepted]
    issue_counts = sorted_count_by(issue for case in cases for issue in case.issues)
    return {
        "path": str(output_file),
        "profile": profile,
        "main_model": runtime.main.model,
        "records": len(records),
        "samples_per_record": samples_per_record,
        "total_samples": len(cases),
        "accepted_samples": len(rows),
        "acceptance_rate": safe_ratio(len(rows), len(cases)),
        "min_reward": min_reward,
        "include_system": include_system,
        "max_length_ratio": max_length_ratio,
        "accepted_category_counts": sorted_count_by(case.category for case in accepted_cases),
        "issue_counts": issue_counts,
        "total_main_calls": sum(case.main_call_count for case in cases),
        "total_eval_tokens": sum(case.eval_tokens for case in cases),
        "total_duration_ms": elapsed_ms(started),
        "cases": [main_r1_sample_case_dict(case) for case in cases],
    }


def render_main_r1_sample_export(data: dict[str, Any]) -> str:
    lines = [
        f"Main Agent R1-lite sample export: {data['path']}",
        f"Profile: {data['profile']} ({data['main_model']})",
        f"Records: {data['records']}",
        f"Samples per record: {data['samples_per_record']}",
        f"Total samples: {data['total_samples']}",
        f"Accepted samples: {data['accepted_samples']}",
        f"Acceptance rate: {data['acceptance_rate']:.3f}",
        f"Minimum reward: {data['min_reward']}",
        f"Total main calls: {data['total_main_calls']}",
        f"Total eval tokens: {data['total_eval_tokens']}",
        f"Total ms: {data['total_duration_ms']}",
        "Accepted categories:",
    ]
    if data["accepted_category_counts"]:
        lines.extend(f"- {category}: {count}" for category, count in data["accepted_category_counts"].items())
    else:
        lines.append("- none")
    if data["issue_counts"]:
        lines.append("Issue labels:")
        lines.extend(f"- {issue}: {count}" for issue, count in data["issue_counts"].items())
    return "\n".join(lines)


def run_main_distill_pipeline_core(
    client: Any,
    runtime: RuntimeConfig,
    records: list[MainAgentRecord],
    runs_dir: Path,
    profile: str,
    *,
    generate_main: GenerateMain,
    candidate_issues: CandidateIssues,
    verifier_issues: VerifierIssues,
    verifier_labels: Callable[[dict[str, Any]], list[str]],
    system_prompt: str,
    pipeline_id: str | None = None,
    samples_per_record: int = 4,
    min_reward: float = 1.0,
    max_length_ratio: float | None = None,
    include_system: bool = True,
    limo_max_records: int = 800,
    limo_min_score: float = 0.0,
    mix_max_records: int = 800,
    mix_long_ratio: float = 0.2,
    mix_long_char_threshold: int = 1200,
    mix_max_per_category: int = 0,
) -> dict[str, Any]:
    pipeline_id = pipeline_id or new_run_id()
    runs_dir.mkdir(parents=True, exist_ok=True)
    r1_path = runs_dir / f"main-agent-r1-samples-{pipeline_id}.jsonl"
    limo_path = runs_dir / f"main-agent-limo-curated-{pipeline_id}.jsonl"
    mix_path = runs_dir / f"main-agent-mix-distill-{pipeline_id}.jsonl"
    manifest_path = runs_dir / f"main-distill-pipeline-{pipeline_id}.json"

    r1_data = run_main_r1_sample_export_core(
        client=client,
        runtime=runtime,
        records=records,
        output_file=r1_path,
        profile=profile,
        generate_main=generate_main,
        candidate_issues=candidate_issues,
        verifier_issues=verifier_issues,
        verifier_labels=verifier_labels,
        system_prompt=system_prompt,
        samples_per_record=samples_per_record,
        min_reward=min_reward,
        max_length_ratio=max_length_ratio,
        include_system=include_system,
    )
    r1_rows = load_sft_rows_or_raise(r1_path)
    limo_data = run_main_limo_curate(
        r1_rows,
        limo_path,
        max_records=limo_max_records,
        min_score=limo_min_score,
    )
    limo_rows = load_sft_rows_or_raise(limo_path)
    mix_data = run_main_mix_distill_curate(
        limo_rows,
        mix_path,
        max_records=mix_max_records,
        long_ratio=mix_long_ratio,
        long_char_threshold=mix_long_char_threshold,
        max_per_category=mix_max_per_category,
    )
    mix_rows = load_sft_rows_or_raise(mix_path)
    final_report = training_data_quality_report(mix_rows, long_char_threshold=mix_long_char_threshold)
    final_report["format_errors"] = training_data_quality_errors(
        final_report,
        require_system=include_system,
        require_generated_metadata=True,
    )
    if final_report["format_errors"]:
        raise SetupError("; ".join(final_report["format_errors"]))

    data = {
        "pipeline_id": pipeline_id,
        "manifest_path": str(manifest_path),
        "profile": profile,
        "main_model": runtime.main.model,
        "records": len(records),
        "parameters": {
            "samples_per_record": samples_per_record,
            "min_reward": min_reward,
            "max_length_ratio": max_length_ratio,
            "include_system": include_system,
            "limo_max_records": limo_max_records,
            "limo_min_score": limo_min_score,
            "mix_max_records": mix_max_records,
            "mix_long_ratio": mix_long_ratio,
            "mix_long_char_threshold": mix_long_char_threshold,
            "mix_max_per_category": mix_max_per_category,
        },
        "artifacts": {
            "r1_samples": str(r1_path),
            "limo_curated": str(limo_path),
            "mix_distill": str(mix_path),
        },
        "r1": r1_data,
        "limo": limo_data,
        "mix": mix_data,
        "final_training_data_report": final_report,
        "heldout_eval_command": (
            "python main.py main-eval --profile "
            f"{profile} --input-file data\\main_agent_fresh_heldout_seed.jsonl --json --timeout 900 --max-length-ratio 4"
        ),
    }
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def render_main_distill_pipeline(data: dict[str, Any]) -> str:
    report = data["final_training_data_report"]
    return "\n".join(
        [
            f"Main Agent distill pipeline: {data['manifest_path']}",
            f"Profile: {data['profile']} ({data['main_model']})",
            f"Input records: {data['records']}",
            f"R1 accepted: {data['r1']['accepted_samples']}/{data['r1']['total_samples']}",
            f"LIMO selected: {data['limo']['selected_rows']}/{data['limo']['input_rows']}",
            f"Mix selected: {data['mix']['selected_rows']}/{data['mix']['input_rows']}",
            f"Final rows: {report['rows']}",
            f"Final buckets: {report['reasoning_bucket_counts']}",
            f"Final format errors: {len(report.get('format_errors', []))}",
            f"Held-out eval: {data['heldout_eval_command']}",
        ]
    )
