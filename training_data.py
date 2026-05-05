from __future__ import annotations

import json
import re
from copy import deepcopy
from collections import Counter
from pathlib import Path
from typing import Any

from core_types import SetupError
from main_agent_data import MainAgentRecord, load_main_agent_records
from training_boundaries import capability_dev_authority_overlap_issues


SFT_ALLOWED_MESSAGE_ROLES = ("system", "user", "assistant")
SFT_FORBIDDEN_TOP_LEVEL_FIELDS = ("prompt", "target_response", "candidate", "output", "response")
SFT_REQUIRED_GENERATED_METADATA = ("source", "split", "verifier_labels")


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _sorted_count_by(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _mix_distill_bucket(text: str, long_char_threshold: int) -> str:
    return "long" if len(text) >= long_char_threshold else "short"


def main_sft_messages(
    record: MainAgentRecord,
    system_prompt: str,
    include_system: bool = True,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if include_system:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(
        [
            {"role": "user", "content": record.prompt},
            {"role": "assistant", "content": record.target_response},
        ]
    )
    return messages


def verifier_metadata_labels(verifier: dict[str, Any]) -> list[str]:
    labels = [f"verifier:{name}" for name, value in sorted(verifier.items()) if value]
    return labels or ["reviewed_target"]


def infer_main_sft_source_split(input_file: Path) -> tuple[str, str]:
    name = input_file.name.lower()
    if "fresh_heldout" in name:
        return "synthetic_fresh_heldout", "heldout_eval"
    if "rotated_heldout" in name:
        return "synthetic_rotated_heldout", "heldout_eval"
    if "heldout" in name:
        return "synthetic_heldout", "heldout_eval"
    if "v6_training" in name:
        return "codex_golden_claude_second_opinion", "train_seed"
    if "hard" in name:
        return "synthetic_hard", "train_hard"
    return "synthetic_seed", "train_seed"


def export_main_sft(
    records: list[MainAgentRecord],
    output_file: Path,
    system_prompt: str,
    include_system: bool = True,
    source: str = "synthetic_seed",
    split: str = "train_seed",
) -> dict[str, Any]:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "id": record.record_id,
                "category": record.category,
                "source": source,
                "split": split,
                "verifier_labels": verifier_metadata_labels(record.verifier),
                "messages": main_sft_messages(record, system_prompt, include_system=include_system),
            },
            ensure_ascii=False,
        )
        for record in records
    ]
    output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    categories: dict[str, int] = {}
    for record in records:
        categories[record.category] = categories.get(record.category, 0) + 1
    return {
        "path": str(output_file),
        "records": len(records),
        "include_system": include_system,
        "source": source,
        "split": split,
        "categories": dict(sorted(categories.items())),
    }


def render_main_sft_export(data: dict[str, Any]) -> str:
    lines = [
        f"Main Agent SFT export: {data['path']}",
        f"Records: {data['records']}",
        f"Include system: {data['include_system']}",
        f"Source: {data['source']}",
        f"Split: {data['split']}",
        "Categories:",
    ]
    lines.extend(f"- {category}: {count}" for category, count in data["categories"].items())
    return "\n".join(lines)

def sft_export_format_gate_data(paths: Path | list[Path], system_prompt: str) -> dict[str, Any]:
    source_paths = [paths] if isinstance(paths, Path) else list(paths)
    all_rows: list[dict[str, Any]] = []
    file_reports: list[dict[str, Any]] = []
    load_errors: list[str] = []
    validation_errors: list[str] = []
    source_total = 0

    for path in source_paths:
        records, file_load_errors, total = load_main_agent_records(path)
        source_total += total
        load_errors.extend(f"{path}: {error}" for error in file_load_errors)
        rows = [
            {
                "id": record.record_id,
                "category": record.category,
                "source": "synthetic_seed",
                "split": "quality_gate",
                "verifier_labels": verifier_metadata_labels(record.verifier),
                "messages": main_sft_messages(record, system_prompt, include_system=True),
            }
            for record in records
        ]
        file_validation_errors = [
            f"{path}: {error}"
            for index, row in enumerate(rows, 1)
            for error in validate_sft_jsonl_row(row, index)
        ]
        validation_errors.extend(file_validation_errors)
        file_report = training_data_quality_report(rows) if rows else {}
        file_reports.append(
            {
                "source_path": str(path),
                "source_total": total,
                "rows": len(rows),
                "system_rows": file_report.get("system_rows", 0),
                "duplicate_ids": file_report.get("duplicate_ids", []),
                "load_errors": [f"{path}: {error}" for error in file_load_errors],
                "validation_errors": file_validation_errors,
            }
        )
        all_rows.extend(rows)

    report = training_data_quality_report(all_rows) if all_rows else {}
    format_errors = (
        training_data_quality_errors(report, require_system=True)
        if all_rows
        else ["training data is empty"]
    )
    return {
        "source_path": str(source_paths[0]) if len(source_paths) == 1 else None,
        "source_paths": [str(path) for path in source_paths],
        "source_total": source_total,
        "rows": len(all_rows),
        "system_rows": report.get("system_rows", 0),
        "duplicate_ids": report.get("duplicate_ids", []),
        "files": file_reports,
        "load_errors": load_errors,
        "validation_errors": validation_errors,
        "format_errors": format_errors,
        "errors": load_errors + validation_errors + format_errors,
    }


def load_sft_jsonl_rows(path: Path) -> tuple[list[dict[str, Any]], list[str], int]:
    if not path.exists():
        return [], [f"file not found: {path}"], 0

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    total = 0
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        total += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {index}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(row, dict):
            errors.append(f"line {index}: row must be an object")
            continue
        row_errors = validate_sft_jsonl_row(row, index)
        if row_errors:
            errors.extend(row_errors)
            continue
        rows.append(row)
    return rows, errors, total


def load_sft_rows_or_raise(path: Path) -> list[dict[str, Any]]:
    rows, errors, _ = load_sft_jsonl_rows(path)
    if errors:
        raise SetupError("; ".join(errors))
    return rows


def validate_sft_jsonl_row(row: dict[str, Any], line_number: int) -> list[str]:
    errors: list[str] = []
    row_id = row.get("id")
    if not isinstance(row_id, str) or not row_id.strip():
        errors.append(f"line {line_number}: id must be a non-empty string")

    for field_name in SFT_FORBIDDEN_TOP_LEVEL_FIELDS:
        if field_name in row:
            errors.append(
                f"line {line_number}: {field_name} is not allowed in SFT rows; use messages instead"
            )

    messages = row.get("messages")
    if not isinstance(messages, list) or not messages:
        errors.append(f"line {line_number}: messages must be a non-empty list")
        return errors

    seen_roles: set[str] = set()
    assistant_has_text = False
    for message_index, message in enumerate(messages, 1):
        if not isinstance(message, dict):
            errors.append(f"line {line_number}: messages[{message_index}] must be an object")
            continue
        role = message.get("role")
        if role not in SFT_ALLOWED_MESSAGE_ROLES:
            errors.append(
                f"line {line_number}: messages[{message_index}].role must be one of "
                f"{', '.join(SFT_ALLOWED_MESSAGE_ROLES)}"
            )
        elif isinstance(role, str):
            seen_roles.add(role)

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            errors.append(f"line {line_number}: messages[{message_index}].content must be a non-empty string")
        elif role == "assistant":
            assistant_has_text = True

    if "user" not in seen_roles:
        errors.append(f"line {line_number}: row must contain a user message")
    if "assistant" not in seen_roles or not assistant_has_text:
        errors.append(f"line {line_number}: row must contain an assistant message with text content")
    return errors


def training_row_assistant_text(row: dict[str, Any]) -> str:
    messages = row.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        return content.strip() if isinstance(content, str) else ""
    return ""


def training_row_user_text(row: dict[str, Any]) -> str:
    messages = row.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        content = message.get("content")
        return content.strip() if isinstance(content, str) else ""
    return ""


def answer_diversity_score(best_text: str, alternate_text: str) -> float:
    best_tokens = set(re.findall(r"\w+", best_text.lower()))
    alternate_tokens = set(re.findall(r"\w+", alternate_text.lower()))
    if best_tokens or alternate_tokens:
        overlap = len(best_tokens & alternate_tokens)
        union = len(best_tokens | alternate_tokens)
        token_distance = 1.0 - _safe_ratio(overlap, union)
    else:
        token_distance = 0.0 if best_text == alternate_text else 1.0
    length_distance = _safe_ratio(
        abs(len(best_text) - len(alternate_text)),
        max(len(best_text), len(alternate_text), 1),
    )
    return round((token_distance * 0.8) + (length_distance * 0.2), 4)


def _training_row_labels(row: dict[str, Any]) -> list[str]:
    labels = row.get("verifier_labels")
    return [label for label in labels if isinstance(label, str)] if isinstance(labels, list) else []


def _is_accepted_teacher_alternate(row: dict[str, Any]) -> bool:
    labels = set(_training_row_labels(row))
    accepted_by = row.get("accepted_by")
    return accepted_by == "local_verifier" or "accepted_by_local_verifier" in labels


def _best_plus_alt_sft_best_row(
    record: MainAgentRecord,
    *,
    system_prompt: str,
    include_system: bool,
) -> dict[str, Any]:
    return {
        "id": f"{record.record_id}-best",
        "record_id": record.record_id,
        "category": record.category,
        "source": "codex_golden_claude_best",
        "split": "train_seed_best",
        "verifier_labels": [
            "best_answer",
            "codex_golden",
            "claude_second_opinion",
            "not_clean_claim_evidence",
            *verifier_metadata_labels(record.verifier),
        ],
        "messages": main_sft_messages(record, system_prompt, include_system=include_system),
    }


def _best_plus_alt_sft_alternate_row(
    record: MainAgentRecord,
    row: dict[str, Any],
    *,
    system_prompt: str,
    include_system: bool,
) -> dict[str, Any]:
    alternate = deepcopy(row)
    provider = str(alternate.get("teacher_provider") or alternate.get("external_teacher_provider") or "teacher")
    alternate["id"] = f"{record.record_id}-alt-{re.sub(r'[^A-Za-z0-9_.-]+', '-', provider).strip('-').lower()}"
    alternate["record_id"] = record.record_id
    alternate["category"] = record.category
    alternate["source"] = "nvidia_teacher_second_opinion_alt"
    alternate["split"] = "train_candidate_alt"
    labels = [
        "alternate_answer",
        *[label for label in _training_row_labels(row) if label != "alternate_answer"],
        "not_clean_claim_evidence",
    ]
    alternate["verifier_labels"] = list(dict.fromkeys(labels))
    messages = []
    if include_system:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(
        [
            {"role": "user", "content": record.prompt},
            {"role": "assistant", "content": training_row_assistant_text(row)},
        ]
    )
    alternate["messages"] = messages
    return alternate


def run_main_best_plus_alt_export(
    records: list[MainAgentRecord],
    alternate_rows: list[dict[str, Any]],
    *,
    pair_output_file: Path,
    sft_output_file: Path,
    system_prompt: str,
    include_system: bool = True,
    min_diversity: float = 0.15,
) -> dict[str, Any]:
    if not 0 <= min_diversity <= 1:
        raise SetupError("--min-diversity must be between 0 and 1.")

    alternates_by_record: dict[str, list[tuple[float, dict[str, Any]]]] = {}
    skipped_alternates: Counter[str] = Counter()
    records_by_id = {record.record_id: record for record in records}

    for row in alternate_rows:
        record_id = row.get("record_id")
        if not isinstance(record_id, str) or record_id not in records_by_id:
            skipped_alternates["unknown_record_id"] += 1
            continue
        if not _is_accepted_teacher_alternate(row):
            skipped_alternates["not_accepted_by_local_verifier"] += 1
            continue
        record = records_by_id[record_id]
        if training_row_user_text(row) != record.prompt:
            skipped_alternates["prompt_mismatch"] += 1
            continue
        alternate_text = training_row_assistant_text(row)
        if not alternate_text or alternate_text == record.target_response:
            skipped_alternates["empty_or_identical_answer"] += 1
            continue
        score = answer_diversity_score(record.target_response, alternate_text)
        if score < min_diversity:
            skipped_alternates["below_min_diversity"] += 1
            continue
        alternates_by_record.setdefault(record_id, []).append((score, row))

    pair_rows: list[dict[str, Any]] = []
    sft_rows: list[dict[str, Any]] = []
    alternate_category_counts: Counter[str] = Counter()
    alternate_model_counts: Counter[str] = Counter()
    records_without_alternate: list[str] = []

    for record in records:
        candidates = sorted(
            alternates_by_record.get(record.record_id, []),
            key=lambda item: (
                -item[0],
                str(item[1].get("teacher_model") or ""),
                str(item[1].get("id") or ""),
            ),
        )
        selected = candidates[0] if candidates else None
        best_row = _best_plus_alt_sft_best_row(
            record,
            system_prompt=system_prompt,
            include_system=include_system,
        )
        sft_rows.append(best_row)

        pair_row = {
            "id": record.record_id,
            "category": record.category,
            "prompt": record.prompt,
            "best_response": record.target_response,
            "best_source": getattr(record, "source", None) or "codex_golden_claude_second_opinion",
            "best_review_note": getattr(record, "review_note", None),
            "alternate_response": None,
            "alternate_source": None,
            "alternate_teacher_model": None,
            "alternate_source_id": None,
            "alternate_selection_score": None,
            "alternate_available_count": len(candidates),
            "clean_claim_eligible": False,
            "evidence_level": "training_material_not_capability_evidence",
        }

        if selected is None:
            records_without_alternate.append(record.record_id)
        else:
            score, row = selected
            alternate_text = training_row_assistant_text(row)
            pair_row.update(
                {
                    "alternate_response": alternate_text,
                    "alternate_source": row.get("source"),
                    "alternate_teacher_model": row.get("teacher_model"),
                    "alternate_source_id": row.get("id"),
                    "alternate_selection_score": score,
                }
            )
            sft_rows.append(
                _best_plus_alt_sft_alternate_row(
                    record,
                    row,
                    system_prompt=system_prompt,
                    include_system=include_system,
                )
            )
            alternate_category_counts[record.category] += 1
            teacher_model = row.get("teacher_model")
            if isinstance(teacher_model, str) and teacher_model:
                alternate_model_counts[teacher_model] += 1

        pair_rows.append(pair_row)

    pair_output_file.parent.mkdir(parents=True, exist_ok=True)
    pair_output_file.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in pair_rows) + ("\n" if pair_rows else ""),
        encoding="utf-8",
    )
    sft_output_file.parent.mkdir(parents=True, exist_ok=True)
    sft_output_file.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in sft_rows) + ("\n" if sft_rows else ""),
        encoding="utf-8",
    )

    category_counts = Counter(record.category for record in records)
    return {
        "pair_file": str(pair_output_file),
        "sft_file": str(sft_output_file),
        "seed_records": len(records),
        "sft_rows": len(sft_rows),
        "best_rows": len(records),
        "alternate_rows": len(sft_rows) - len(records),
        "records_without_alternate": records_without_alternate,
        "category_counts": dict(sorted(category_counts.items())),
        "alternate_category_counts": dict(sorted(alternate_category_counts.items())),
        "alternate_model_counts": dict(sorted(alternate_model_counts.items())),
        "skipped_alternate_counts": dict(sorted(skipped_alternates.items())),
        "selection_rule": (
            "canonical seed is best; choose at most one verifier-passing teacher "
            "answer with highest text diversity per record"
        ),
        "min_diversity": min_diversity,
        "evidence_level": "training_material_not_capability_evidence",
    }


def render_main_best_plus_alt_export(data: dict[str, Any]) -> str:
    lines = [
        f"Main Agent best+alt export: {data['sft_file']}",
        f"Pair file: {data['pair_file']}",
        f"Best rows: {data['best_rows']}",
        f"Alternate rows: {data['alternate_rows']}",
        f"SFT rows: {data['sft_rows']}",
        f"Records without alternate: {len(data['records_without_alternate'])}",
        f"Minimum diversity: {data['min_diversity']}",
        f"Evidence level: {data['evidence_level']}",
    ]
    if data["alternate_category_counts"]:
        lines.append("Alternate categories:")
        lines.extend(f"- {category}: {count}" for category, count in data["alternate_category_counts"].items())
    if data["alternate_model_counts"]:
        lines.append("Alternate models:")
        lines.extend(f"- {model}: {count}" for model, count in data["alternate_model_counts"].items())
    if data["skipped_alternate_counts"]:
        lines.append("Skipped alternates:")
        lines.extend(f"- {reason}: {count}" for reason, count in data["skipped_alternate_counts"].items())
    return "\n".join(lines)


def training_data_quality_report(rows: list[dict[str, Any]], long_char_threshold: int = 1200) -> dict[str, Any]:
    if long_char_threshold < 1:
        raise SetupError("--long-char-threshold must be at least 1.")

    ids: list[str] = []
    record_ids: list[str] = []
    assistant_lengths: list[int] = []
    system_rows = 0
    message_counts: list[int] = []
    source_values: list[str] = []
    split_values: list[str] = []
    verifier_label_values: list[str] = []
    curation_values: list[str] = []
    mix_source_values: list[str] = []
    bucket_values: list[str] = []
    category_values: list[str] = []
    missing_source_rows = 0
    missing_split_rows = 0
    missing_verifier_label_rows = 0

    for index, row in enumerate(rows, 1):
        text = training_row_assistant_text(row)
        row_id = str(row.get("id") or f"row-{index}")
        record_id = str(row.get("record_id") or row_id)
        category = str(row.get("category") or "unknown")
        messages = row.get("messages")
        message_list = messages if isinstance(messages, list) else []
        if any(isinstance(message, dict) and message.get("role") == "system" for message in message_list):
            system_rows += 1

        ids.append(row_id)
        record_ids.append(record_id)
        category_values.append(category)
        assistant_lengths.append(len(text))
        message_counts.append(len(message_list))
        source = row.get("source")
        split = row.get("split")
        verifier_labels = row.get("verifier_labels")
        if not isinstance(source, str) or not source.strip():
            missing_source_rows += 1
            source_values.append("unknown")
        else:
            source_values.append(source.strip())
        if not isinstance(split, str) or not split.strip():
            missing_split_rows += 1
            split_values.append("unknown")
        else:
            split_values.append(split.strip())
        if not isinstance(verifier_labels, list) or not all(
            isinstance(label, str) and label.strip() for label in verifier_labels
        ):
            missing_verifier_label_rows += 1
        else:
            verifier_label_values.extend(label.strip() for label in verifier_labels)
        curation_values.append(str(row.get("curation_source") or "none"))
        mix_source_values.append(str(row.get("mix_distillation_source") or "none"))
        bucket_values.append(str(row.get("mix_distill_bucket") or _mix_distill_bucket(text, long_char_threshold)))

    id_counts = Counter(ids)
    record_counts = Counter(record_ids)
    duplicate_ids = sorted(row_id for row_id, count in id_counts.items() if count > 1)
    duplicate_record_ids = sorted(row_id for row_id, count in record_counts.items() if count > 1)
    return {
        "rows": len(rows),
        "category_counts": _sorted_count_by(category_values),
        "source_counts": _sorted_count_by(source_values),
        "split_counts": _sorted_count_by(split_values),
        "verifier_label_counts": _sorted_count_by(verifier_label_values),
        "curation_source_counts": _sorted_count_by(curation_values),
        "mix_distillation_source_counts": _sorted_count_by(mix_source_values),
        "reasoning_bucket_counts": _sorted_count_by(bucket_values),
        "long_char_threshold": long_char_threshold,
        "system_rows": system_rows,
        "system_row_rate": _safe_ratio(system_rows, len(rows)),
        "assistant_chars_min": min(assistant_lengths, default=0),
        "assistant_chars_max": max(assistant_lengths, default=0),
        "assistant_chars_avg": round(_safe_ratio(sum(assistant_lengths), len(assistant_lengths)), 3),
        "messages_per_row_avg": round(_safe_ratio(sum(message_counts), len(message_counts)), 3),
        "missing_source_rows": missing_source_rows,
        "missing_split_rows": missing_split_rows,
        "missing_verifier_label_rows": missing_verifier_label_rows,
        "duplicate_ids": duplicate_ids,
        "duplicate_record_ids": duplicate_record_ids,
    }


def sft_authority_boundary_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    issue_rows: list[dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()

    for index, row in enumerate(rows, 1):
        row_id = str(row.get("id") or f"row-{index}")
        messages = row.get("messages")
        message_list = messages if isinstance(messages, list) else []
        for message_index, message in enumerate(message_list, 1):
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            field_name = "prompt" if role == "user" else "target_response"
            raw_issues = capability_dev_authority_overlap_issues({field_name: content})
            issues = [
                issue.replace("prompt:", "user:", 1).replace("target_response:", "assistant:", 1)
                for issue in raw_issues
            ]
            if not issues:
                continue
            issue_counts.update(issues)
            issue_rows.append(
                {
                    "row_id": row_id,
                    "message_index": message_index,
                    "role": role,
                    "issues": issues,
                }
            )

    return {
        "authority_boundary_message_count": len(issue_rows),
        "authority_boundary_issue_count": sum(issue_counts.values()),
        "authority_boundary_issue_counts": dict(sorted(issue_counts.items())),
        "authority_boundary_issue_rows": issue_rows,
    }


def training_data_quality_errors(
    data: dict[str, Any],
    require_system: bool = False,
    require_generated_metadata: bool = False,
) -> list[str]:
    errors: list[str] = []
    if data["rows"] < 1:
        errors.append("training data is empty")
    if data["duplicate_ids"]:
        errors.append(f"duplicate row ids: {', '.join(data['duplicate_ids'])}")
    if require_system and data["system_rows"] != data["rows"]:
        missing = data["rows"] - data["system_rows"]
        errors.append(f"missing system messages: {missing} row(s)")
    if require_generated_metadata:
        if data.get("missing_source_rows", 0):
            errors.append(f"missing source metadata: {data['missing_source_rows']} row(s)")
        if data.get("missing_split_rows", 0):
            errors.append(f"missing split metadata: {data['missing_split_rows']} row(s)")
        if data.get("missing_verifier_label_rows", 0):
            errors.append(
                f"missing verifier label metadata: {data['missing_verifier_label_rows']} row(s)"
            )
    return errors


def training_data_report_data(
    rows: list[dict[str, Any]],
    *,
    path: Path | str,
    require_system: bool,
    require_generated_metadata: bool,
    long_char_threshold: int = 1200,
) -> dict[str, Any]:
    data = training_data_quality_report(rows, long_char_threshold=long_char_threshold)
    data.update(sft_authority_boundary_report(rows))
    data["path"] = str(path)
    data["require_system"] = require_system
    data["require_generated_metadata"] = require_generated_metadata
    data["format_errors"] = training_data_quality_errors(
        data,
        require_system=require_system,
        require_generated_metadata=require_generated_metadata,
    )
    if data["authority_boundary_message_count"]:
        data["format_errors"].append(
            "authority/refusal/control-plane SFT boundary issues: "
            f"{data['authority_boundary_message_count']} message(s)"
        )
    return data


def render_training_data_quality_report(data: dict[str, Any]) -> str:
    lines = [
        "Main Agent training-data report",
        f"Rows: {data['rows']}",
        f"Assistant chars: min={data['assistant_chars_min']} avg={data['assistant_chars_avg']:.3f} max={data['assistant_chars_max']}",
        f"System rows: {data['system_rows']} ({data['system_row_rate']:.3f})",
        "Reasoning buckets:",
    ]
    if data["reasoning_bucket_counts"]:
        lines.extend(f"- {bucket}: {count}" for bucket, count in data["reasoning_bucket_counts"].items())
    else:
        lines.append("- none")
    lines.append("Categories:")
    if data["category_counts"]:
        lines.extend(f"- {category}: {count}" for category, count in data["category_counts"].items())
    else:
        lines.append("- none")
    lines.append("Splits:")
    if data.get("split_counts"):
        lines.extend(f"- {split}: {count}" for split, count in data["split_counts"].items())
    else:
        lines.append("- none")
    if data.get("verifier_label_counts"):
        lines.append("Verifier labels:")
        lines.extend(f"- {label}: {count}" for label, count in data["verifier_label_counts"].items())
    if data["duplicate_ids"] or data["duplicate_record_ids"]:
        lines.append("Duplicate keys detected.")
    if data.get("authority_boundary_issue_counts"):
        lines.append("Authority/refusal/control-plane boundary issues:")
        lines.extend(
            f"- {issue}: {count}"
            for issue, count in data["authority_boundary_issue_counts"].items()
        )
    if data.get("format_errors"):
        lines.append("Format errors:")
        lines.extend(f"- {error}" for error in data["format_errors"])
    return "\n".join(lines)
