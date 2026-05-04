from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _safe_float(value: Any, default: float = 0.0) -> float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _safe_str(value: Any, default: str = "unknown") -> str:
    return value if isinstance(value, str) and value else default


def _load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def _case_refs(rows: list[Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        issues = [issue for issue in _safe_list(row.get("issues")) if isinstance(issue, str)]
        if not issues:
            issue_set = {
                issue
                for key in ("baseline_issues", "candidate_issues", "same_issue_labels")
                for issue in _safe_list(row.get(key))
                if isinstance(issue, str)
            }
            issues = sorted(issue_set)
        refs.append(
            {
                "id": _safe_str(row.get("id")),
                "category": _safe_str(row.get("category")),
                "issues": issues,
            }
        )
    return refs


def _count_dict(value: Any) -> dict[str, int]:
    data: dict[str, int] = {}
    if not isinstance(value, Mapping):
        return data
    for key, count in value.items():
        if isinstance(key, str) and isinstance(count, int) and not isinstance(count, bool):
            data[key] = count
    return dict(sorted(data.items()))


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}


def adapter_fresh_eval_gate_data(
    comparison: Mapping[str, Any],
    containment: Mapping[str, Any],
    *,
    min_clean_delta: int = 1,
    allow_regressions: bool = False,
    min_contained_rate: float = 1.0,
) -> dict[str, Any]:
    fixed_cases = _case_refs(_safe_list(comparison.get("fixed_cases")))
    regressed_cases = _case_refs(_safe_list(comparison.get("regressed_cases")))
    persistent_failures = _case_refs(_safe_list(comparison.get("persistent_failures")))
    missing_from_baseline = [
        case_id for case_id in _safe_list(comparison.get("missing_from_baseline")) if isinstance(case_id, str)
    ]
    missing_from_candidate = [
        case_id for case_id in _safe_list(comparison.get("missing_from_candidate")) if isinstance(case_id, str)
    ]
    clean_delta = _safe_int(comparison.get("clean_delta"))
    comparable_total = _safe_int(comparison.get("comparable_total"))
    input_file_match = comparison.get("input_file_match") is True

    containment_total = _safe_int(containment.get("total"))
    containment_contained = _safe_int(containment.get("contained"))
    containment_rate = containment_contained / containment_total if containment_total else 0.0
    containment_issue_counts = _count_dict(containment.get("containment_issue_counts"))
    candidate_issue_counts = _count_dict(containment.get("candidate_issue_counts"))

    checks = [
        _check(
            "same_eval_surface",
            input_file_match,
            "baseline and candidate used the same input_file" if input_file_match else "baseline and candidate input_file differ",
        ),
        _check(
            "no_missing_cases",
            not missing_from_baseline and not missing_from_candidate,
            (
                f"missing_from_baseline={len(missing_from_baseline)}, "
                f"missing_from_candidate={len(missing_from_candidate)}"
            ),
        ),
        _check(
            "clean_delta_met",
            clean_delta >= min_clean_delta,
            f"clean_delta {clean_delta:+d}, required >= {min_clean_delta:+d}",
        ),
        _check(
            "no_regressions",
            allow_regressions or not regressed_cases,
            f"regressed_cases={len(regressed_cases)}, allow_regressions={allow_regressions}",
        ),
        _check(
            "containment_available",
            containment_total > 0,
            f"containment_total={containment_total}",
        ),
        _check(
            "containment_rate_met",
            containment_total > 0 and containment_rate >= min_contained_rate,
            f"contained {containment_contained}/{containment_total} ({containment_rate:.3f}), required >= {min_contained_rate:.3f}",
        ),
        _check(
            "containment_no_issues",
            not containment_issue_counts,
            "containment_issue_counts empty" if not containment_issue_counts else f"containment issues: {sorted(containment_issue_counts)}",
        ),
    ]
    errors = [check["detail"] for check in checks if not check["passed"]]
    fresh_eval_eligible = not errors
    return {
        "decision_scope": "fresh_eval_spend_gate_not_adapter_promotion",
        "fresh_eval_eligible": fresh_eval_eligible,
        "adapter_promotion_eligible": False,
        "verdict": "spend_fresh_eval" if fresh_eval_eligible else "hold",
        "promotion_note": "Fresh eval eligibility is not adapter promotion; promotion still requires unused eval evidence and review.",
        "thresholds": {
            "min_clean_delta": min_clean_delta,
            "allow_regressions": allow_regressions,
            "min_contained_rate": min_contained_rate,
        },
        "comparison": {
            "baseline_name": comparison.get("baseline_name"),
            "candidate_name": comparison.get("candidate_name"),
            "baseline_path": comparison.get("baseline_path"),
            "candidate_path": comparison.get("candidate_path"),
            "baseline_adapter": comparison.get("baseline_adapter"),
            "candidate_adapter": comparison.get("candidate_adapter"),
            "baseline_input_file": comparison.get("baseline_input_file"),
            "candidate_input_file": comparison.get("candidate_input_file"),
            "input_file_match": input_file_match,
            "comparable_total": comparable_total,
            "clean_delta": clean_delta,
            "fixed_case_count": len(fixed_cases),
            "regressed_case_count": len(regressed_cases),
            "persistent_failure_count": len(persistent_failures),
            "missing_from_baseline": missing_from_baseline,
            "missing_from_candidate": missing_from_candidate,
            "regressed_cases": regressed_cases,
            "fixed_cases": fixed_cases,
            "persistent_failures": persistent_failures,
        },
        "containment": {
            "total": containment_total,
            "clean": _safe_int(containment.get("clean")),
            "contained": containment_contained,
            "containment_rate": containment_rate,
            "containment_issue_counts": containment_issue_counts,
            "candidate_issue_counts": candidate_issue_counts,
        },
        "checks": checks,
        "errors": errors,
    }


def adapter_fresh_eval_gate_files(
    comparison_file: Path,
    containment_file: Path,
    *,
    min_clean_delta: int = 1,
    allow_regressions: bool = False,
    min_contained_rate: float = 1.0,
) -> dict[str, Any]:
    data = adapter_fresh_eval_gate_data(
        _load_json_object(comparison_file),
        _load_json_object(containment_file),
        min_clean_delta=min_clean_delta,
        allow_regressions=allow_regressions,
        min_contained_rate=min_contained_rate,
    )
    data["input_files"] = {
        "comparison_file": str(comparison_file),
        "containment_file": str(containment_file),
    }
    return data


def render_adapter_fresh_eval_gate(data: Mapping[str, Any]) -> str:
    comparison = _safe_dict(data.get("comparison"))
    containment = _safe_dict(data.get("containment"))
    thresholds = _safe_dict(data.get("thresholds"))
    lines = [
        "Adapter fresh eval gate",
        f"Verdict: {data.get('verdict')}",
        "Scope: fresh eval spend gate only; not adapter promotion.",
        (
            "Comparison: {baseline} -> {candidate}, clean delta {delta:+d} / required >= {required:+d}"
        ).format(
            baseline=comparison.get("baseline_name") or "baseline",
            candidate=comparison.get("candidate_name") or "candidate",
            delta=_safe_int(comparison.get("clean_delta")),
            required=_safe_int(thresholds.get("min_clean_delta"), 1),
        ),
        (
            "Regressions: {count}, allow_regressions={allow}"
        ).format(
            count=_safe_int(comparison.get("regressed_case_count")),
            allow=thresholds.get("allow_regressions") is True,
        ),
        (
            "Containment: {contained}/{total} ({rate:.3f}), issues={issues}"
        ).format(
            contained=_safe_int(containment.get("contained")),
            total=_safe_int(containment.get("total")),
            rate=_safe_float(containment.get("containment_rate")),
            issues=", ".join(_safe_dict(containment.get("containment_issue_counts"))) or "none",
        ),
        "Checks:",
    ]
    for check in _safe_list(data.get("checks")):
        if isinstance(check, Mapping):
            status = "pass" if check.get("passed") is True else "fail"
            lines.append(f"- {status} {check.get('name')}: {check.get('detail')}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gate whether an adapter comparison is worth spending a fresh clean eval on."
    )
    parser.add_argument("--comparison-file", required=True)
    parser.add_argument("--containment-file", required=True)
    parser.add_argument("--min-clean-delta", type=int, default=1)
    parser.add_argument("--allow-regressions", action="store_true")
    parser.add_argument("--min-contained-rate", type=float, default=1.0)
    parser.add_argument("--output-file", default=None)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main_cli() -> int:
    args = parse_args()
    data = adapter_fresh_eval_gate_files(
        Path(args.comparison_file),
        Path(args.containment_file),
        min_clean_delta=args.min_clean_delta,
        allow_regressions=args.allow_regressions,
        min_contained_rate=args.min_contained_rate,
    )
    if args.output_file:
        output_path = Path(args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data["output_file"] = str(output_path)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_adapter_fresh_eval_gate(data))
    return 0 if data["fresh_eval_eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
