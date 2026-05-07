from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TOOLS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import main  # noqa: E402
import public_bench_server as public_bench  # noqa: E402


def strip_qwen_think(text: str) -> str:
    return re.sub(r"^\s*<think>.*?</think>\s*", "", text, flags=re.S).strip()


def normalized_chat_messages(messages: Any) -> list[dict[str, str]]:
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    normalized: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "user")).lower()
        if role not in {"system", "user", "assistant"}:
            role = "user"
        text = public_bench.content_to_text(message.get("content"))
        if text:
            normalized.append({"role": role, "content": text})
    if not normalized:
        raise ValueError("messages did not contain text")
    return normalized


def chat_template_text(tokenizer: Any, messages: list[dict[str, str]], enable_thinking: bool) -> str:
    try:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=enable_thinking,
        )
    except TypeError:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def generation_kwargs_from_options(
    options: main.ModelOptions | None,
    *,
    fallback_max_new_tokens: int,
) -> dict[str, Any]:
    options = options or main.ModelOptions()
    max_new_tokens = options.num_predict if options.num_predict and options.num_predict > 0 else fallback_max_new_tokens
    temperature = options.temperature
    kwargs: dict[str, Any] = {"max_new_tokens": max_new_tokens}
    if temperature is None or temperature <= 0:
        kwargs["do_sample"] = False
    else:
        kwargs["do_sample"] = True
        kwargs["temperature"] = float(temperature)
    if options.top_p is not None:
        kwargs["top_p"] = float(options.top_p)
    if options.top_k is not None:
        kwargs["top_k"] = int(options.top_k)
    return kwargs


def load_adapter_tokenizer(auto_tokenizer: Any, model_name: str, adapter_dir: Path | None) -> Any:
    if adapter_dir is None:
        return auto_tokenizer.from_pretrained(model_name)
    try:
        return auto_tokenizer.from_pretrained(adapter_dir)
    except (AttributeError, TypeError, ValueError) as exc:
        sys.stderr.write(
            "[adapter-public-bench] adapter tokenizer load failed; "
            f"falling back to base tokenizer: {type(exc).__name__}: {exc}\n"
        )
        tokenizer = auto_tokenizer.from_pretrained(model_name)
        chat_template = adapter_dir / "chat_template.jinja"
        if chat_template.exists():
            tokenizer.chat_template = chat_template.read_text(encoding="utf-8")
        return tokenizer


def request_model_options(
    request: dict[str, Any],
    default_max_new_tokens: int,
    max_request_tokens: int | None = None,
) -> main.ModelOptions:
    updates: dict[str, Any] = {"num_predict": default_max_new_tokens}
    max_tokens = request.get("max_tokens")
    if isinstance(max_tokens, int) and max_tokens > 0:
        updates["num_predict"] = max_tokens
    if max_request_tokens and max_request_tokens > 0:
        updates["num_predict"] = min(int(updates["num_predict"]), max_request_tokens)
    temperature = request.get("temperature")
    if isinstance(temperature, (int, float)):
        updates["temperature"] = float(temperature)
    top_p = request.get("top_p")
    if isinstance(top_p, (int, float)):
        updates["top_p"] = float(top_p)
    return main.ModelOptions(**updates)


def request_stop_strings(request: dict[str, Any]) -> list[str]:
    stop = request.get("stop")
    values: list[str] = []
    if isinstance(stop, str):
        values.append(stop)
    elif isinstance(stop, list):
        values.extend(item for item in stop if isinstance(item, str))
    return [value for value in values if value]


def trim_stop_strings(text: str, stop_strings: list[str]) -> str:
    cut_at: int | None = None
    for stop in stop_strings:
        index = text.find(stop)
        if index >= 0:
            cut_at = index if cut_at is None else min(cut_at, index)
    if cut_at is None:
        return text
    return text[:cut_at]


class HfAdapterChatClient:
    def __init__(
        self,
        *,
        tokenizer: Any,
        model: Any,
        torch_module: Any,
        default_max_new_tokens: int,
        max_request_tokens: int | None,
        enable_thinking: bool,
    ) -> None:
        self.tokenizer = tokenizer
        self.model = model
        self.torch = torch_module
        self.default_max_new_tokens = default_max_new_tokens
        self.max_request_tokens = max_request_tokens
        self.enable_thinking = enable_thinking
        self.last_stats: dict[str, int] | None = None

    @classmethod
    def load(
        cls,
        *,
        model_name: str,
        adapter_dir: Path | None,
        load_4bit: bool,
        default_max_new_tokens: int,
        max_request_tokens: int | None,
        enable_thinking: bool,
    ) -> HfAdapterChatClient:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        compute_dtype = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16
        quantization_config = None
        if load_4bit:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=compute_dtype,
                bnb_4bit_use_double_quant=True,
            )

        tokenizer = load_adapter_tokenizer(AutoTokenizer, model_name, adapter_dir)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=quantization_config,
            torch_dtype=compute_dtype,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        if adapter_dir:
            model = PeftModel.from_pretrained(model, adapter_dir)
        model.eval()
        return cls(
            tokenizer=tokenizer,
            model=model,
            torch_module=torch,
            default_max_new_tokens=default_max_new_tokens,
            max_request_tokens=max_request_tokens,
            enable_thinking=enable_thinking,
        )

    def ensure_ready(self, model: str) -> None:
        return None

    def chat(
        self,
        model: str,
        system: str,
        user: str,
        options: main.ModelOptions | None = None,
        think: bool | None = None,
        keep_alive: str | None = None,
        response_format: str | dict[str, Any] | None = None,
    ) -> str:
        effective_options = options or main.ModelOptions()
        if self.max_request_tokens and self.max_request_tokens > 0:
            requested_tokens = (
                effective_options.num_predict
                if effective_options.num_predict and effective_options.num_predict > 0
                else self.default_max_new_tokens
            )
            effective_options = replace(effective_options, num_predict=min(requested_tokens, self.max_request_tokens))
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self.generate_messages(
            messages,
            options=effective_options,
            enable_thinking=self.enable_thinking if think is None else bool(think),
        )

    def raw_chat(self, messages: list[dict[str, str]], request: dict[str, Any]) -> str:
        options = request_model_options(
            request,
            self.default_max_new_tokens,
            self.max_request_tokens,
        )
        stop_strings = request_stop_strings(request)
        return self.generate_messages(
            messages,
            options=options,
            enable_thinking=self.enable_thinking,
            stop_strings=stop_strings,
        )

    def generate_messages(
        self,
        messages: list[dict[str, str]],
        *,
        options: main.ModelOptions | None,
        enable_thinking: bool,
        stop_strings: list[str] | None = None,
    ) -> str:
        prompt_text = chat_template_text(self.tokenizer, messages, enable_thinking=enable_thinking)
        inputs = self.tokenizer(prompt_text, return_tensors="pt")
        if hasattr(inputs, "to"):
            inputs = inputs.to(self.model.device)
        input_len = int(inputs["input_ids"].shape[1])
        kwargs = generation_kwargs_from_options(options, fallback_max_new_tokens=self.default_max_new_tokens)
        if getattr(self.tokenizer, "eos_token_id", None) is not None:
            kwargs["eos_token_id"] = self.tokenizer.eos_token_id
        if getattr(self.tokenizer, "pad_token_id", None) is not None and "pad_token_id" not in kwargs:
            kwargs["pad_token_id"] = self.tokenizer.pad_token_id
        elif getattr(self.tokenizer, "eos_token_id", None) is not None and "pad_token_id" not in kwargs:
            kwargs["pad_token_id"] = self.tokenizer.eos_token_id
        effective_stop_strings = list(stop_strings or [])
        eos_token = getattr(self.tokenizer, "eos_token", None)
        if isinstance(eos_token, str) and eos_token:
            effective_stop_strings.append(eos_token)
        if effective_stop_strings:
            kwargs["stop_strings"] = sorted(set(effective_stop_strings))
            kwargs["tokenizer"] = self.tokenizer
        with self.torch.no_grad():
            generated = self.model.generate(**inputs, **kwargs)
        output_len = int(generated[0].shape[0]) - input_len
        raw_answer = self.tokenizer.decode(generated[0][input_len:], skip_special_tokens=False)
        raw_answer = trim_stop_strings(raw_answer, effective_stop_strings)
        raw_answer = self.tokenizer.decode(
            self.tokenizer(raw_answer, add_special_tokens=False)["input_ids"],
            skip_special_tokens=True,
        ).strip()
        self.last_stats = {"prompt_tokens": input_len, "eval_tokens": max(0, output_len)}
        answer = strip_qwen_think(raw_answer)
        if not answer:
            raise main.PipelineError("HF adapter returned an empty assistant message.")
        return answer


class AdapterBenchmarkState:
    def __init__(
        self,
        *,
        runtime: main.RuntimeConfig,
        client: HfAdapterChatClient,
        mode: str,
        model_alias: str,
        canon: str,
        runs_dir: Path,
    ) -> None:
        self.runtime = runtime
        self.client = client
        self.mode = mode
        self.model_alias = model_alias
        self.canon = canon
        self.runs_dir = runs_dir

    def generate(self, prompt: str, messages: list[dict[str, str]], request: dict[str, Any]) -> str:
        try:
            if self.mode == "raw":
                return self.client.raw_chat(messages, request)
            runtime = public_bench.override_main_options_for_request(self.runtime, request)
            if self.mode == "main":
                generation = main.generate_candidate_result(
                    client=self.client,
                    runtime=runtime.main,
                    user_prompt=prompt,
                    revision=None,
                    quality_refine_passes=runtime.quality_refine_passes,
                    search_candidates=runtime.search_candidates,
                    local_select=runtime.local_select,
                    adaptive_compute=runtime.adaptive_compute,
                )
                return generation.text

            result = main.run_pipeline(
                prompt=prompt,
                client=self.client,
                model=runtime.main.model,
                canon=self.canon,
                log_dir=self.runs_dir,
                runtime=runtime,
            )
            return result.output
        except main.PipelineError as exc:
            if "empty assistant message" in str(exc):
                return ""
            raise


class AdapterBenchHandler(BaseHTTPRequestHandler):
    state: AdapterBenchmarkState

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self.write_json({"status": "ok", "mode": self.state.mode, "model": self.state.model_alias})
            return
        if self.path.rstrip("/") == "/v1/models":
            self.write_json(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.state.model_alias,
                            "object": "model",
                            "created": 0,
                            "owned_by": "local",
                        }
                    ],
                }
            )
            return
        self.write_json({"error": {"message": "not found"}}, status=404)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat/completions":
            self.write_json({"error": {"message": "not found"}}, status=404)
            return
        try:
            request = self.read_json()
            messages = normalized_chat_messages(request.get("messages"))
            prompt = public_bench.prompt_from_chat_messages(request.get("messages"))
            content = self.state.generate(prompt, messages, request)
            self.write_json(public_bench.openai_chat_response(self.state.model_alias, content))
        except Exception as exc:  # pragma: no cover - exercised manually with live server
            self.write_json({"error": {"message": str(exc), "type": exc.__class__.__name__}}, status=500)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            raise ValueError("request JSON must be an object")
        return data

    def write_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[adapter-public-bench] " + fmt % args + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OpenAI-compatible benchmark wrapper for raw, main-only, and split pipeline HF adapter runs."
    )
    parser.add_argument("--model", required=True, help="Base Hugging Face model id or path.")
    parser.add_argument("--adapter-dir", default=None, help="Optional PEFT adapter directory.")
    parser.add_argument("--profile", choices=sorted(main.RUNTIME_PROFILES), default="qwen3-8b-local-max")
    parser.add_argument("--mode", choices=("raw", "main", "pipeline"), default="raw")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--model-alias", help="Model id exposed to benchmark clients. Default: mode-specific alias.")
    parser.add_argument("--canon", default=str(PROJECT_ROOT / "canon.md"))
    parser.add_argument("--runs-dir", default=str(PROJECT_ROOT / "runs" / "closure-bench-audit"))
    parser.add_argument("--default-max-new-tokens", type=int, default=512)
    parser.add_argument("--max-request-tokens", type=int, default=0)
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--no-4bit", action="store_true")
    return parser


def runtime_for_profile(profile: str) -> main.RuntimeConfig:
    return main.RUNTIME_PROFILES[profile]


def serve(args: argparse.Namespace) -> None:
    adapter_dir = Path(args.adapter_dir) if args.adapter_dir else None
    client = HfAdapterChatClient.load(
        model_name=args.model,
        adapter_dir=adapter_dir,
        load_4bit=not args.no_4bit,
        default_max_new_tokens=args.default_max_new_tokens,
        max_request_tokens=args.max_request_tokens if args.max_request_tokens > 0 else None,
        enable_thinking=args.enable_thinking,
    )
    alias = args.model_alias or (
        "adapter-raw"
        if args.mode == "raw"
        else "adapter-main"
        if args.mode == "main"
        else f"{args.profile}-adapter-pipeline"
    )
    AdapterBenchHandler.state = AdapterBenchmarkState(
        runtime=runtime_for_profile(args.profile),
        client=client,
        mode=args.mode,
        model_alias=alias,
        canon=main.load_canon(Path(args.canon)),
        runs_dir=Path(args.runs_dir),
    )
    server = ThreadingHTTPServer((args.host, args.port), AdapterBenchHandler)
    print(
        json.dumps(
            {
                "status": "serving",
                "mode": args.mode,
                "profile": args.profile,
                "model": args.model,
                "adapter_dir": str(adapter_dir) if adapter_dir else None,
                "model_alias": alias,
                "base_url": f"http://{args.host}:{args.port}/v1/chat/completions",
                "started_at": int(time.time()),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    server.serve_forever()


def main_entry() -> int:
    args = build_parser().parse_args()
    serve(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
