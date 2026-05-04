from __future__ import annotations

from pathlib import Path
from typing import Any

from output_utils import print_json_or_text
from training_data import (
    load_sft_jsonl_rows,
    render_training_data_quality_report,
    training_data_report_data,
)


def main_training_data_report_command(args: Any) -> int:
    rows, errors, total = load_sft_jsonl_rows(Path(args.input_file))
    if errors:
        data = {"path": args.input_file, "total": total, "errors": errors}
        print_json_or_text(data, args.json, "\n".join(errors))
        return 1

    data = training_data_report_data(
        rows,
        path=args.input_file,
        require_system=args.require_system,
        require_generated_metadata=getattr(args, "require_generated_metadata", False),
        long_char_threshold=args.long_char_threshold,
    )
    print_json_or_text(data, args.json, render_training_data_quality_report(data))
    return 1 if data["format_errors"] else 0
