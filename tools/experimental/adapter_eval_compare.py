from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _safe_str(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _case_issues(row: Mapping[str, Any]) -> list[str]:
    return [issue for issue in _safe_list(row.get("issues")) if isinstance(issue, str) and issue]


def _case_clean(row: Mapping[str, Any]) -> bool:
    clean = row.get("clean")
    if isinstance(clean, bool):
        return clean
    return not _case_issues(row)


def _clean_summary(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "clean": sum(1 for row in rows if _case_clean(row)),
        "dirty": sum(1 for row in rows if not _case_clean(row)),
    }


def _issue_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(issue for row in rows for issue in _case_issues(row))
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _category_clean(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    categories = sorted({_safe_str(row.get("category"), "unknown") for row in rows})
    data: dict[str, dict[str, int]] = {}
    for category in categories:
        category_rows = [row for row in rows if _safe_str(row.get("category"), "unknown") == category]
        data[category] = _clean_summary(category_rows)
    return data


def _category_delta(
    baseline_rows: list[Mapping[str, Any]],
    candidate_rows: list[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    baseline = _category_clean(baseline_rows)
    candidate = _category_clean(candidate_rows)
    categories = sorted(set(baseline) | set(candidate))
    return {
        category: {
            "baseline_clean": baseline.get(category, {}).get("clean", 0),
            "candidate_clean": candidate.get(category, {}).get("clean", 0),
            "clean_delta": candidate.get(category, {}).get("clean", 0)
            - baseline.get(category, {}).get("clean", 0),
            "total": max(
                baseline.get(category, {}).get("total", 0),
                candidate.get(category, {}).get("total", 0),
            ),
        }
        for category in categories
    }


def _load_eval_summary(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: adapter eval summary must be a JSON object")
    if not isinstance(data.get("results"), list):
        raise ValueError(f"{path}: adapter eval summary must contain results list")
    return data


def _rows_by_id(summary: Mapping[str, Any], label: str) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(_safe_list(summary.get("results")), 1):
        if not isinstance(row, Mapping):
            continue
        case_id = _safe_str(row.get("id"), "")
        if not case_id:
            raise ValueError(f"{label}: result {index} is missing id")
        if case_id in rows:
            raise ValueError(f"{label}: duplicate result id {case_id}")
        rows[case_id] = row
    return rows


def _case_ref(row: Mapping[str, Any], issues: list[str]) -> dict[str, Any]:
    return {
        "id": _safe_str(row.get("id"), "unknown"),
        "category": _safe_str(row.get("category"), "unknown"),
        "issues": issues,
    }


def compare_adapter_eval_data(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    baseline_name: str = "baseline",
    candidate_name: str = "candidate",
    baseline_path: str | None = None,
    candidate_path: str | None = None,
) -> dict[str, Any]:
    baseline_by_id = _rows_by_id(baseline, baseline_name)
    candidate_by_id = _rows_by_id(candidate, candidate_name)
    comparable_ids = sorted(set(baseline_by_id) & set(candidate_by_id))
    baseline_rows = [baseline_by_id[case_id] for case_id in comparable_ids]
    candidate_rows = [candidate_by_id[case_id] for case_id in comparable_ids]

    fixed_cases: list[dict[str, Any]] = []
    regressed_cases: list[dict[str, Any]] = []
    persistent_failures: list[dict[str, Any]] = []
    unchanged_clean_count = 0

    for case_id in comparable_ids:
        baseline_row = baseline_by_id[case_id]
        candidate_row = candidate_by_id[case_id]
        baseline_clean = _case_clean(baseline_row)
        candidate_clean = _case_clean(candidate_row)
        baseline_issues = _case_issues(baseline_row)
        candidate_issues = _case_issues(candidate_row)
        if not baseline_clean and candidate_clean:
            fixed_cases.append(_case_ref(baseline_row, baseline_issues))
        elif baseline_clean and not candidate_clean:
            regressed_cases.append(_case_ref(candidate_row, candidate_issues))
        elif not baseline_clean and not candidate_clean:
            persistent_failures.append(
                {
                    "id": case_id,
                    "category": _safe_str(candidate_row.get("category"), _safe_str(baseline_row.get("category"), "unknown")),
                    "baseline_issues": baseline_issues,
                    "candidate_issues": candidate_issues,
                    "same_issue_labels": sorted(set(baseline_issues) & set(candidate_issues)),
                }
            )
        else:
            unchanged_clean_count += 1

    baseline_clean = _clean_summary(baseline_rows)
    candidate_clean = _clean_summary(candidate_rows)
    baseline_issues = Counter(_issue_counts(baseline_rows))
    candidate_issues = Counter(_issue_counts(candidate_rows))
    issue_delta = {
        issue: candidate_issues.get(issue, 0) - baseline_issues.get(issue, 0)
        for issue in sorted(set(baseline_issues) | set(candidate_issues))
    }

    return {
        "baseline_name": baseline_name,
        "candidate_name": candidate_name,
        "baseline_path": baseline_path,
        "candidate_path": candidate_path,
        "baseline_adapter": baseline.get("adapter"),
        "candidate_adapter": candidate.get("adapter"),
        "input_file_match": baseline.get("input_file") == candidate.get("input_file"),
        "baseline_input_file": baseline.get("input_file"),
        "candidate_input_file": candidate.get("input_file"),
        "baseline_enable_thinking": baseline.get("enable_thinking"),
        "candidate_enable_thinking": candidate.get("enable_thinking"),
        "baseline_augment_prompts": baseline.get("augment_prompts", False),
        "candidate_augment_prompts": candidate.get("augment_prompts", False),
        "comparable_total": len(comparable_ids),
        "missing_from_baseline": sorted(set(candidate_by_id) - set(baseline_by_id)),
        "missing_from_candidate": sorted(set(baseline_by_id) - set(candidate_by_id)),
        "baseline_clean": baseline_clean,
        "candidate_clean": candidate_clean,
        "clean_delta": candidate_clean["clean"] - baseline_clean["clean"],
        "fixed_cases": fixed_cases,
        "regressed_cases": regressed_cases,
        "persistent_failures": persistent_failures,
        "unchanged_clean_count": unchanged_clean_count,
        "baseline_issue_counts": _issue_counts(baseline_rows),
        "candidate_issue_counts": _issue_counts(candidate_rows),
        "issue_delta": issue_delta,
        "category_delta": _category_delta(baseline_rows, candidate_rows),
    }


def compare_adapter_eval_files(
    baseline_path: Path,
    candidate_path: Path,
    *,
    baseline_name: str = "baseline",
    candidate_name: str = "candidate",
) -> dict[str, Any]:
    return compare_adapter_eval_data(
        _load_eval_summary(baseline_path),
        _load_eval_summary(candidate_path),
        baseline_name=baseline_name,
        candidate_name=candidate_name,
        baseline_path=str(baseline_path),
        candidate_path=str(candidate_path),
    )


def render_adapter_eval_comparison(data: Mapping[str, Any]) -> str:
    lines = [
        f"Adapter eval comparison: {data['baseline_name']} -> {data['candidate_name']}",
        (
            "Clean: {base}/{total} -> {cand}/{total} (delta {delta:+d})"
        ).format(
            base=data["baseline_clean"]["clean"],
            cand=data["candidate_clean"]["clean"],
            total=data["comparable_total"],
            delta=data["clean_delta"],
        ),
        f"Input file match: {data['input_file_match']}",
        f"Fixed cases: {len(data['fixed_cases'])}",
        f"Regressed cases: {len(data['regressed_cases'])}",
        f"Persistent failures: {len(data['persistent_failures'])}",
    ]
    if data["fixed_cases"]:
        lines.extend(["", "Fixed:"])
        lines.extend(
            "- {id} ({category}): {issues}".format(
                id=case["id"],
                category=case["category"],
                issues=", ".join(case["issues"]) or "none",
            )
            for case in data["fixed_cases"]
        )
    if data["regressed_cases"]:
        lines.extend(["", "Regressed:"])
        lines.extend(
            "- {id} ({category}): {issues}".format(
                id=case["id"],
                category=case["category"],
                issues=", ".join(case["issues"]) or "none",
            )
            for case in data["regressed_cases"]
        )
    if data["persistent_failures"]:
        lines.extend(["", "Persistent failures:"])
        lines.extend(
            "- {id} ({category}): baseline={baseline}; candidate={candidate}".format(
                id=case["id"],
                category=case["category"],
                baseline=", ".join(case["baseline_issues"]) or "none",
                candidate=", ".join(case["candidate_issues"]) or "none",
            )
            for case in data["persistent_failures"]
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two qlora_adapter_eval JSON summaries by case id.")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--baseline-name", default="baseline")
    parser.add_argument("--candidate-name", default="candidate")
    parser.add_argument("--output-file", default=None)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main_cli() -> int:
    args = parse_args()
    data = compare_adapter_eval_files(
        Path(args.baseline),
        Path(args.candidate),
        baseline_name=args.baseline_name,
        candidate_name=args.candidate_name,
    )
    if args.output_file:
        output_path = Path(args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        data["output_file"] = str(output_path)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_adapter_eval_comparison(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
