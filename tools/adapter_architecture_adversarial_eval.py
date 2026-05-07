#!/usr/bin/env python3
"""Run architecture adversarial eval with the HF adapter-backed pipeline.

The normal `main.py architecture-adversarial-eval` command uses the configured
Ollama runtime. This wrapper keeps the same architecture eval core but swaps in
the HF adapter client used by the formal closure benchmark, so S1 safety
evidence can be tied to the adapter-backed split path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
for path in (PROJECT_ROOT, TOOLS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import adapter_public_bench_server as adapter_bench  # noqa: E402
import main  # noqa: E402
from eval_reports import (  # noqa: E402
    architecture_adversarial_eval_gate_errors,
    render_architecture_adversarial_eval,
    write_architecture_adversarial_eval_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Base Hugging Face model id or path.")
    parser.add_argument("--adapter-dir", default=None, help="Optional PEFT adapter directory.")
    parser.add_argument("--profile", choices=sorted(main.RUNTIME_PROFILES), default="qwen3-8b-local-max")
    parser.add_argument("--input-file", default="data/architecture_containment_pressure_seed.jsonl")
    parser.add_argument("--canon", default=str(PROJECT_ROOT / "canon.md"))
    parser.add_argument("--runs-dir", default=str(PROJECT_ROOT / "runs" / "adapter-architecture-adversarial-eval"))
    parser.add_argument("--output-file", default=None)
    parser.add_argument("--default-max-new-tokens", type=int, default=2048)
    parser.add_argument("--max-request-tokens", type=int, default=0)
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--no-4bit", action="store_true")
    parser.add_argument("--min-pass-rate", type=float, default=0.0)
    parser.add_argument("--json", action="store_true")
    return parser


def run(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    records, errors, total = main.load_architecture_adversarial_records(Path(args.input_file))
    if errors:
        result = main.ArchitectureAdversarialCheck(Path(args.input_file), total, {}, errors)
        data: dict[str, object] = result.public_dict()
        data["gate_errors"] = errors
        output_file = Path(args.output_file) if args.output_file else None
        path = write_architecture_adversarial_eval_summary(data, output_file, Path(args.runs_dir))
        return data, path

    adapter_dir = Path(args.adapter_dir) if args.adapter_dir else None
    client = adapter_bench.HfAdapterChatClient.load(
        model_name=args.model,
        adapter_dir=adapter_dir,
        load_4bit=not args.no_4bit,
        default_max_new_tokens=args.default_max_new_tokens,
        max_request_tokens=args.max_request_tokens if args.max_request_tokens > 0 else None,
        enable_thinking=args.enable_thinking,
    )
    runtime = main.RUNTIME_PROFILES[args.profile]
    data = main.run_architecture_adversarial_eval(
        client=client,
        runtime=runtime,
        canon=main.load_canon(Path(args.canon)),
        records=records,
        log_dir=Path(args.runs_dir),
    )
    data["profile"] = main.profile_dict(args.profile, runtime)
    data["adapter_backend"] = {
        "model": args.model,
        "adapter_dir": str(adapter_dir) if adapter_dir else None,
        "default_max_new_tokens": args.default_max_new_tokens,
        "max_request_tokens": args.max_request_tokens if args.max_request_tokens > 0 else None,
        "enable_thinking": bool(args.enable_thinking),
        "load_4bit": not bool(args.no_4bit),
    }
    data["gate_errors"] = architecture_adversarial_eval_gate_errors(
        data,
        min_pass_rate=args.min_pass_rate,
    )
    output_file = Path(args.output_file) if args.output_file else None
    path = write_architecture_adversarial_eval_summary(data, output_file, Path(args.runs_dir))
    return data, path


def main_entry() -> int:
    args = build_parser().parse_args()
    data, path = run(args)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_architecture_adversarial_eval(data, path))
    return 1 if data.get("gate_errors") else 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
