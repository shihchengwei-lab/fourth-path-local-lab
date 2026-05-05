from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core_types import SetupError
from training_data import training_row_assistant_text


@dataclass(frozen=True)
class MainLimoCuratedCase:
    row_id: str
    category: str
    selected: bool
    score: float
    assistant_chars: int
    features: dict[str, int]


@dataclass(frozen=True)
class MainMixDistillCase:
    row_key: str
    row_id: str
    category: str
    bucket: str
    selected: bool
    score: float
    assistant_chars: int


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _sorted_count_by(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def limo_keyword_count(text: str, keywords: tuple[str, ...]) -> int:
    lower = text.lower()
    return sum(lower.count(keyword) for keyword in keywords)


def limo_template_features(text: str) -> dict[str, int]:
    lower = text.lower()
    return {
        "assistant_chars": len(text),
        "line_count": len([line for line in text.splitlines() if line.strip()]),
        "verification_markers": limo_keyword_count(
            lower,
            ("check", "verify", "validate", "confirm", "檢查", "驗證", "核對"),
        ),
        "exploration_markers": limo_keyword_count(
            lower,
            ("case", "option", "alternative", "suppose", "if ", "如果", "情況", "可能"),
        ),
        "connective_markers": limo_keyword_count(
            lower,
            ("because", "therefore", "since", "so ", "then", "thus", "因此", "所以", "接著", "然後"),
        ),
        "step_markers": len(re.findall(r"(?im)^\s*(?:\d+[.)]|[-*]\s+|step\s+\d+|步驟)", text)),
        "final_answer_markers": limo_keyword_count(
            lower,
            ("####", "answer", "final", "therefore", "所以", "答案"),
        ),
    }


def limo_template_score(text: str) -> float:
    features = limo_template_features(text)
    length_score = min(features["assistant_chars"] / 1200, 1.0) * 30.0
    verification_score = min(features["verification_markers"] / 2, 1.0) * 20.0
    exploration_score = min(features["exploration_markers"] / 3, 1.0) * 20.0
    connective_score = min(features["connective_markers"] / 6, 1.0) * 20.0
    structure_score = min((features["step_markers"] + features["final_answer_markers"]) / 4, 1.0) * 10.0
    overlong_penalty = max(0.0, (features["assistant_chars"] - 4096) / 4096) * 20.0
    return round(
        max(
            0.0,
            length_score
            + verification_score
            + exploration_score
            + connective_score
            + structure_score
            - overlong_penalty,
        ),
        3,
    )


def main_limo_curated_case_dict(case: MainLimoCuratedCase) -> dict[str, Any]:
    return {
        "id": case.row_id,
        "category": case.category,
        "selected": case.selected,
        "score": case.score,
        "assistant_chars": case.assistant_chars,
        "features": case.features,
    }


def run_main_limo_curate(
    rows: list[dict[str, Any]],
    output_file: Path,
    max_records: int = 800,
    min_score: float = 0.0,
    max_per_category: int = 0,
) -> dict[str, Any]:
    if max_records < 1:
        raise SetupError("--max-records must be at least 1.")
    if max_per_category < 0:
        raise SetupError("--max-per-category must be zero or greater.")

    scored: list[tuple[float, dict[str, Any], MainLimoCuratedCase]] = []
    for index, row in enumerate(rows, 1):
        text = training_row_assistant_text(row)
        features = limo_template_features(text)
        score = limo_template_score(text)
        row_id = str(row.get("id") or row.get("record_id") or f"row-{index}")
        category = str(row.get("category") or "unknown")
        scored.append(
            (
                score,
                row,
                MainLimoCuratedCase(
                    row_id=row_id,
                    category=category,
                    selected=False,
                    score=score,
                    assistant_chars=features["assistant_chars"],
                    features=features,
                ),
            )
        )

    scored.sort(key=lambda item: (-item[0], item[2].category, item[2].row_id))
    selected_rows: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    category_counts: Counter[str] = Counter()

    for score, row, case in scored:
        if len(selected_rows) >= max_records:
            break
        if score < min_score:
            continue
        if max_per_category and category_counts[case.category] >= max_per_category:
            continue
        curated = dict(row)
        curated["curation_source"] = "limo_less_is_more"
        curated["limo_score"] = score
        curated["limo_features"] = case.features
        selected_rows.append(curated)
        selected_ids.add(case.row_id)
        category_counts[case.category] += 1

    cases = [
        MainLimoCuratedCase(
            row_id=case.row_id,
            category=case.category,
            selected=case.row_id in selected_ids,
            score=case.score,
            assistant_chars=case.assistant_chars,
            features=case.features,
        )
        for _, _, case in scored
    ]

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in selected_rows)
        + ("\n" if selected_rows else ""),
        encoding="utf-8",
    )

    return {
        "path": str(output_file),
        "input_rows": len(rows),
        "selected_rows": len(selected_rows),
        "selection_rate": _safe_ratio(len(selected_rows), len(rows)),
        "max_records": max_records,
        "min_score": min_score,
        "max_per_category": max_per_category,
        "selected_category_counts": dict(sorted(category_counts.items())),
        "score_min": min((case.score for case in cases), default=0.0),
        "score_max": max((case.score for case in cases), default=0.0),
        "score_avg": round(_safe_ratio(sum(case.score for case in cases), len(cases)), 3),
        "cases": [main_limo_curated_case_dict(case) for case in cases],
    }


def render_main_limo_curate(data: dict[str, Any]) -> str:
    lines = [
        f"Main Agent LIMO curate: {data['path']}",
        f"Input rows: {data['input_rows']}",
        f"Selected rows: {data['selected_rows']}",
        f"Selection rate: {data['selection_rate']:.3f}",
        f"Score range: {data['score_min']:.3f} - {data['score_max']:.3f}",
        f"Average score: {data['score_avg']:.3f}",
        "Selected categories:",
    ]
    if data["selected_category_counts"]:
        lines.extend(f"- {category}: {count}" for category, count in data["selected_category_counts"].items())
    else:
        lines.append("- none")
    return "\n".join(lines)


def mix_distill_row_score(row: dict[str, Any], text: str) -> float:
    value = row.get("limo_score")
    if isinstance(value, (int, float)):
        return float(value)
    return limo_template_score(text)


def mix_distill_bucket(text: str, long_char_threshold: int) -> str:
    return "long" if len(text) >= long_char_threshold else "short"


def main_mix_distill_case_dict(case: MainMixDistillCase) -> dict[str, Any]:
    return {
        "id": case.row_id,
        "category": case.category,
        "bucket": case.bucket,
        "selected": case.selected,
        "score": case.score,
        "assistant_chars": case.assistant_chars,
    }


def run_main_mix_distill_curate(
    rows: list[dict[str, Any]],
    output_file: Path,
    max_records: int = 800,
    long_ratio: float = 0.2,
    long_char_threshold: int = 1200,
    max_per_category: int = 0,
) -> dict[str, Any]:
    if max_records < 1:
        raise SetupError("--max-records must be at least 1.")
    if not 0 <= long_ratio <= 1:
        raise SetupError("--long-ratio must be between 0 and 1.")
    if long_char_threshold < 1:
        raise SetupError("--long-char-threshold must be at least 1.")
    if max_per_category < 0:
        raise SetupError("--max-per-category must be zero or greater.")

    scored: list[tuple[float, dict[str, Any], MainMixDistillCase]] = []
    for index, row in enumerate(rows, 1):
        text = training_row_assistant_text(row)
        score = mix_distill_row_score(row, text)
        row_id = str(row.get("id") or row.get("record_id") or f"row-{index}")
        row_key = f"{row_id}#{index}"
        category = str(row.get("category") or "unknown")
        bucket = mix_distill_bucket(text, long_char_threshold)
        scored.append(
            (
                score,
                row,
                MainMixDistillCase(
                    row_key=row_key,
                    row_id=row_id,
                    category=category,
                    bucket=bucket,
                    selected=False,
                    score=score,
                    assistant_chars=len(text),
                ),
            )
        )

    scored.sort(key=lambda item: (-item[0], item[2].bucket, item[2].category, item[2].row_id))
    available_long = sum(1 for _, _, case in scored if case.bucket == "long")
    available_short = sum(1 for _, _, case in scored if case.bucket == "short")
    if long_ratio >= 1:
        long_target = min(available_long, max_records)
    elif long_ratio <= 0:
        long_target = 0
    else:
        max_long_from_ratio = int((available_short * long_ratio) // (1 - long_ratio))
        long_target = min(available_long, round(max_records * long_ratio), max_long_from_ratio)
    short_target = min(available_short, max_records - long_target)

    selected_rows: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    category_counts: Counter[str] = Counter()

    def can_select(case: MainMixDistillCase) -> bool:
        return case.row_key not in selected_keys and (
            not max_per_category or category_counts[case.category] < max_per_category
        )

    def select_case(row: dict[str, Any], case: MainMixDistillCase) -> None:
        selected = dict(row)
        selected["mix_distillation_source"] = "small_model_learnability_gap"
        selected["mix_distill_bucket"] = case.bucket
        selected["mix_distill_score"] = case.score
        selected["mix_distill_long_ratio_target"] = long_ratio
        selected_rows.append(selected)
        selected_keys.add(case.row_key)
        category_counts[case.category] += 1

    for desired_bucket, target in (("long", long_target), ("short", short_target)):
        for _, row, case in scored:
            if sum(1 for selected in selected_rows if selected.get("mix_distill_bucket") == desired_bucket) >= target:
                break
            if case.bucket == desired_bucket and can_select(case):
                select_case(row, case)

    for _, row, case in scored:
        if len(selected_rows) >= max_records:
            break
        if case.bucket == "short" and can_select(case):
            select_case(row, case)

    cases = [
        MainMixDistillCase(
            row_key=case.row_key,
            row_id=case.row_id,
            category=case.category,
            bucket=case.bucket,
            selected=case.row_key in selected_keys,
            score=case.score,
            assistant_chars=case.assistant_chars,
        )
        for _, _, case in scored
    ]

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in selected_rows)
        + ("\n" if selected_rows else ""),
        encoding="utf-8",
    )

    selected_bucket_counts = _sorted_count_by([str(row.get("mix_distill_bucket")) for row in selected_rows])
    selected_long = selected_bucket_counts.get("long", 0)
    return {
        "path": str(output_file),
        "input_rows": len(rows),
        "selected_rows": len(selected_rows),
        "selection_rate": _safe_ratio(len(selected_rows), len(rows)),
        "max_records": max_records,
        "long_ratio_target": long_ratio,
        "actual_long_ratio": _safe_ratio(selected_long, len(selected_rows)),
        "long_char_threshold": long_char_threshold,
        "max_per_category": max_per_category,
        "input_bucket_counts": _sorted_count_by([case.bucket for _, _, case in scored]),
        "selected_bucket_counts": selected_bucket_counts,
        "selected_category_counts": dict(sorted(category_counts.items())),
        "cases": [main_mix_distill_case_dict(case) for case in cases],
    }


def render_main_mix_distill_curate(data: dict[str, Any]) -> str:
    lines = [
        f"Main Agent mix distillation curate: {data['path']}",
        f"Input rows: {data['input_rows']}",
        f"Selected rows: {data['selected_rows']}",
        f"Selection rate: {data['selection_rate']:.3f}",
        f"Long ratio target: {data['long_ratio_target']:.3f}",
        f"Actual long ratio: {data['actual_long_ratio']:.3f}",
        "Selected buckets:",
    ]
    if data["selected_bucket_counts"]:
        lines.extend(f"- {bucket}: {count}" for bucket, count in data["selected_bucket_counts"].items())
    else:
        lines.append("- none")
    return "\n".join(lines)
