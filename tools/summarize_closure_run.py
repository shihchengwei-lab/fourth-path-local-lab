#!/usr/bin/env python3
"""Summarize a formal closure benchmark run.

This script is intentionally read-only. It parses lm-eval result JSON files,
driver logs, and model response samples under a single run id, then prints a
Markdown summary with the exact evidence paths used for each score.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CASES = [
    "R0-C0-raw-b8",
    "M0-main-only-b8",
    "S0-split-b8",
    "M1-main-only-adapter",
    "S1-split-adapter",
]

METRICS = [
    ("gsm8k_strict", "gsm8k", "exact_match,strict-match"),
    ("gsm8k_flexible", "gsm8k", "exact_match,flexible-extract"),
    ("ifeval_prompt_strict", "ifeval", "prompt_level_strict_acc,none"),
    ("ifeval_prompt_loose", "ifeval", "prompt_level_loose_acc,none"),
    ("ifeval_inst_strict", "ifeval", "inst_level_strict_acc,none"),
    ("ifeval_inst_loose", "ifeval", "inst_level_loose_acc,none"),
]

DELTAS = [
    ("M0 - R0/C0", "M0-main-only-b8", "R0-C0-raw-b8"),
    ("S0 - R0/C0", "S0-split-b8", "R0-C0-raw-b8"),
    ("M0 - S0", "M0-main-only-b8", "S0-split-b8"),
    ("M1 - M0", "M1-main-only-adapter", "M0-main-only-b8"),
    ("S1 - S0", "S1-split-adapter", "S0-split-b8"),
]

FORBIDDEN_OUTPUT_TERMS = [
    "Cold Eyes",
    "Action Gate",
    "fixed refusal",
    "refusal module",
    "pipeline audit",
    "audit verdict",
    "canon_clause",
    "cold_eyes",
    "action_gate",
    "verdict",
]


@dataclass(frozen=True)
class CaseSummary:
    case: str
    result_path: Path
    metrics: dict[str, float]
    limit: Any
    model_args: str
    total_seconds: float | None
    samples: list[Path]
    driver_log: Path | None
    started_utc: str | None
    completed_utc: str | None
    command_server: str | None


def _latest_result(case_dir: Path) -> Path | None:
    results = sorted(case_dir.rglob("results_*.json"), key=lambda p: p.stat().st_mtime)
    return results[-1] if results else None


def _parse_driver_log(path: Path | None) -> dict[str, str | None]:
    parsed: dict[str, str | None] = {
        "started_utc": None,
        "completed_utc": None,
        "command_server": None,
    }
    if path is None or not path.exists():
        return parsed
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        for key in parsed:
            prefix = f"{key}="
            if line.startswith(prefix):
                parsed[key] = line[len(prefix) :]
    return parsed


def _load_case(run_root: Path, logs_root: Path, case: str) -> CaseSummary | None:
    case_dir = run_root / case
    result_path = _latest_result(case_dir)
    if result_path is None:
        return None

    data = json.loads(result_path.read_text(encoding="utf-8"))
    metrics: dict[str, float] = {}
    for label, task, metric_key in METRICS:
        value = data["results"][task][metric_key]
        metrics[label] = float(value)

    config = data.get("config", {})
    samples = sorted(result_path.parent.glob("samples_*.jsonl"))
    driver_log = logs_root / f"{case}.driver.log"
    if not driver_log.exists():
        driver_log = None
    driver = _parse_driver_log(driver_log)

    total_seconds = data.get("total_evaluation_time_seconds")
    if total_seconds is not None:
        total_seconds = float(total_seconds)

    return CaseSummary(
        case=case,
        result_path=result_path,
        metrics=metrics,
        limit=config.get("limit"),
        model_args=str(config.get("model_args", "")),
        total_seconds=total_seconds,
        samples=samples,
        driver_log=driver_log,
        started_utc=driver["started_utc"],
        completed_utc=driver["completed_utc"],
        command_server=driver["command_server"],
    )


def _iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_iter_strings(item))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_iter_strings(item))
        return out
    return []


def scan_output_terms(samples: list[Path]) -> dict[str, int]:
    hits = {term: 0 for term in FORBIDDEN_OUTPUT_TERMS}
    for sample in samples:
        for line in sample.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                texts = [line]
            else:
                texts = []
                texts.extend(_iter_strings(record.get("resps")))
                texts.extend(_iter_strings(record.get("filtered_resps")))
            output_text = "\n".join(texts)
            for term in hits:
                if term in output_text:
                    hits[term] += 1
    return {term: count for term, count in hits.items() if count}


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6f}"


def _fmt_delta(delta: float | None, baseline: float | None) -> str:
    if delta is None:
        return "n/a"
    pp = delta * 100
    if baseline in (None, 0):
        return f"{pp:+.3f} pp"
    relative = (delta / baseline) * 100
    return f"{pp:+.3f} pp ({relative:+.2f}%)"


def _duration_text(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    whole = int(round(seconds))
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def print_markdown(summaries: dict[str, CaseSummary]) -> None:
    print("# Closure Benchmark Summary")
    print()
    print("## Result Files")
    print()
    print("| Case | Limit | Runtime | Started UTC | Completed UTC | Result path |")
    print("| --- | --- | ---: | --- | --- | --- |")
    for case in CASES:
        summary = summaries.get(case)
        if summary is None:
            print(f"| {case} | missing | missing | missing | missing | missing |")
            continue
        print(
            "| {case} | {limit} | {runtime} | {started} | {completed} | `{path}` |".format(
                case=case,
                limit="None" if summary.limit is None else _md_escape(str(summary.limit)),
                runtime=_duration_text(summary.total_seconds),
                started=summary.started_utc or "n/a",
                completed=summary.completed_utc or "n/a",
                path=summary.result_path.as_posix(),
            )
        )

    print()
    print("## Scores")
    print()
    header = "| Case | " + " | ".join(label for label, _, _ in METRICS) + " |"
    print(header)
    print("| --- |" + " ---: |" * len(METRICS))
    for case in CASES:
        summary = summaries.get(case)
        if summary is None:
            print(f"| {case} | " + " | ".join("missing" for _ in METRICS) + " |")
            continue
        values = [summary.metrics[label] for label, _, _ in METRICS]
        print(f"| {case} | " + " | ".join(_fmt(value) for value in values) + " |")

    print()
    print("## Deltas")
    print()
    print("| Delta | " + " | ".join(label for label, _, _ in METRICS) + " |")
    print("| --- |" + " ---: |" * len(METRICS))
    for name, left, right in DELTAS:
        left_summary = summaries.get(left)
        right_summary = summaries.get(right)
        cells = []
        for label, _, _ in METRICS:
            if left_summary is None or right_summary is None:
                cells.append("missing")
                continue
            delta = left_summary.metrics[label] - right_summary.metrics[label]
            cells.append(_fmt_delta(delta, right_summary.metrics[label]))
        print(f"| {name} | " + " | ".join(cells) + " |")

    print()
    print("## Candidate Output Surface Scan")
    print()
    print("| Case | Forbidden output-term hits in resps/filtered_resps |")
    print("| --- | ---: |")
    for case in ["M0-main-only-b8", "M1-main-only-adapter"]:
        summary = summaries.get(case)
        if summary is None:
            print(f"| {case} | missing |")
            continue
        hits = scan_output_terms(summary.samples)
        detail = ", ".join(f"{term}={count}" for term, count in sorted(hits.items()))
        print(f"| {case} | {detail or '0'} |")

    print()
    print("## Server Commands")
    print()
    for case in CASES:
        summary = summaries.get(case)
        if summary is None:
            continue
        print(f"### {case}")
        print()
        print("```text")
        print(summary.command_server or "n/a")
        print("```")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--root", default="runs/closure-bench-cloud")
    parser.add_argument("--logs-root", default="runs/cloud-logs")
    args = parser.parse_args()

    run_root = Path(args.root) / args.run_id
    logs_root = Path(args.logs_root) / args.run_id
    summaries = {
        case: summary
        for case in CASES
        if (summary := _load_case(run_root, logs_root, case)) is not None
    }
    print_markdown(summaries)
    return 0 if len(summaries) == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
