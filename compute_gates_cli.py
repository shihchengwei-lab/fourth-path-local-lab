from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from compute_gates import (
    kv_cache_estimate_data,
    next_token_headroom_data,
    r2r_estimate_data,
    render_inference_compute_gate,
    render_kv_cache_estimate,
    render_next_token_headroom,
    render_r2r_estimate,
)
from output_utils import print_json_or_text


def r2r_estimate_command(args: argparse.Namespace) -> int:
    data = r2r_estimate_data(
        small_params_b=args.small_params_b,
        large_params_b=args.large_params_b,
        router_params_b=args.router_params_b,
        large_token_rate=args.large_token_rate,
        output_tokens=args.output_tokens,
        backend=args.backend,
    )
    print_json_or_text(data, args.json, render_r2r_estimate(data))
    return 0


def kv_cache_estimate_command(args: argparse.Namespace) -> int:
    data = kv_cache_estimate_data(
        layers=args.layers,
        kv_heads=args.kv_heads,
        head_dim=args.head_dim,
        context_tokens=args.context_tokens,
        batch_size=args.batch_size,
        kv_bits=args.kv_bits,
        quantized_kv_bits=args.quantized_kv_bits,
    )
    print_json_or_text(data, args.json, render_kv_cache_estimate(data))
    return 0


def next_token_headroom_command(args: argparse.Namespace) -> int:
    data = next_token_headroom_data(args.backend)
    print_json_or_text(data, args.json, render_next_token_headroom(data))
    return 0


def inference_compute_gate_command(
    args: argparse.Namespace,
    gate_data: Callable[[Path], dict[str, Any]],
) -> int:
    data = gate_data(Path(args.distill_file))
    print_json_or_text(data, args.json, render_inference_compute_gate(data))
    return 1 if data["errors"] else 0
