# Closure Benchmark Plan

This is the final evidence run plan for comparing raw `qwen3:8b`, the split
Fourth Path pipeline, and the current Main Agent adapter. It is descriptive:
there is no pass threshold, promotion gate, or deployment claim in this report.

## Cases

| Case | Meaning | Path |
| --- | --- | --- |
| A0 | raw B8 | Direct `qwen3:8b` through Ollama's OpenAI-compatible chat endpoint. |
| A1 | split B8 | `qwen3:8b` candidate generation through `run_pipeline`, with external Classify / Cold Eyes / Action Gate behavior preserved. |
| A2 | raw B8 + adapter | Hugging Face base model plus PEFT adapter, called directly by the benchmark chat messages. |
| A3 | split B8 + adapter | Same adapter-backed Main Agent candidate path, then the split pipeline and external boundary layers. |

Default split profile: `qwen3-8b-local-max`.

Reason: this profile keeps the comparison focused on raw candidate generation
plus the split boundary. Profiles with local selection, search, or refinement
add extra model calls and are useful later, but they mix another architecture
change into the A0-A3 closure matrix.

Default adapter: `runs\qwen3-8b-main-agent-v19-v18-failure-repair-lora-20260505`.

Reason: the final local convergence notes identify the best current path as the
v19 adapter plus the current runtime hint layer. The newer v22 adapter is a
diagnostic artifact, not the selected adapter for closure. A3 gets the runtime
hint through the current split pipeline; A2 remains a raw direct adapter call by
design.

## Runner

Primary runner: EleutherAI `lm-evaluation-harness` with
`local-chat-completions`.

Use the closure runner:

```powershell
.\tools\run-closure-bench.ps1 -Case all -Tasks ifeval,gsm8k -NoLimit
```

Useful preflight before spending GPU time:

```powershell
.\tools\run-closure-bench.ps1 -PreflightOnly
```

Important parameters:

```text
-RawModel       Ollama raw model name. Default: qwen3:8b
-SplitProfile   Fourth Path split profile. Default: qwen3-8b-local-max
-HfModel        Hugging Face base model for adapter runs. Default: Qwen/Qwen3-8B
-AdapterDir     PEFT adapter directory. Default: runs\qwen3-8b-main-agent-v19-v18-failure-repair-lora-20260505
-Python         benchmark venv Python. Default: .\.venv-bench\Scripts\python.exe
-AdapterPython  LoRA/transformers venv Python. Default: .\.venv-lora\Scripts\python.exe
```

## Reporting

Record the exact command, resolved adapter path, task versions, and output path.
For each case, report the metrics exactly as produced by the harness.

Use this table shape:

| Case | Tasks | Limit | Model path | Split path | Adapter | Output path | Metrics | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A0 | | | raw Ollama | no | no | | | |
| A1 | | | Ollama via Main Agent | yes | no | | | |
| A2 | | | HF direct chat | no | yes | | | |
| A3 | | | HF via Main Agent | yes | yes | | | |

Interpretation should stay factual:

- Architecture tax: compare A1 against A0, and A3 against A2.
- Adapter effect: compare A2 against A0, and A3 against A1.
- Split effect on safety boundary: inspect refusals, boundary blocks, audit logs,
  and any normal-task over-blocking.
- Adapter prompt mismatch: A2 is deliberately raw/direct, even though the adapter
  was trained for the Main Agent candidate role. Treat it as observed evidence,
  not as the intended deployment path.

Do not write `pass`, `fail`, `safe`, `unsafe`, `final`, or `deployable` unless
the text is explicitly describing a tool field. The closure report should say
what happened, not convert the result into a hidden threshold.

## Outputs

The runner writes harness outputs under:

```text
runs\closure-bench
```

A1 and A3 also write pipeline audit logs under:

```text
runs\public-bench-audit
runs\closure-bench-audit
```

Keep raw samples and audit logs local unless a later review explicitly asks to
publish sanitized summaries.
