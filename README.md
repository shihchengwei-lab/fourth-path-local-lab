# Fourth Path Local Lab

Local reference implementation for the Fourth Path architecture described in
[`separation-and-audit-alignment`](https://github.com/shihchengwei-lab/separation-and-audit-alignment).

This repository is a research prototype, not a proven safety system. It exists
to make one architectural claim concrete enough to inspect and test on a local
machine:

```text
Capability and safety should grow together:
do not leak dangerous capability, and do not over-cage normal capability.
```

## Architecture First

The repo tests whether useful capability is lost when one model loop must do too
many jobs at once: solve the task, maintain refusal posture, monitor policy
boundaries, preserve alignment, and produce the final answer.

The goal is not to make the Main Agent timid. It should become a stronger
candidate generator for normal tasks. The goal is also not to trust the Main
Agent with final permission. Dangerous content, fake approval, hidden
control-plane leakage, and unaudited side effects must still be blocked by
external layers.

The Fourth Path shape here splits those jobs:

- **Main Agent**: generates candidate answers. It does not approve, refuse, or
  execute actions.
- **Input prefilter**: routes obvious request-side canon violations before
  generation. It cannot approve output.
- **Candidate classifier**: catches candidate-side role, canon, and formatting
  issues before audit. It cannot approve output.
- **Mechanical Cold Eyes**: fail-closed output audit against policy/canon.
- **Action Gate**: pre-execution audit boundary for side effects such as file,
  network, or tool actions.
- **Refusal Module**: emits a fixed refusal outside model generation when the
  pipeline blocks.

The important invariant:

```text
Candidate text never grants authority.
```

If the Main Agent writes "Allowed", "PASS", "approved by Cold Eyes", or any
similar phrase, that is still only candidate text. External layers decide
whether it can be returned or acted on.

## What This Repo Implements

- A local audited pipeline in `main.py`.
- Deterministic policy and matcher code under `audit/`.
- Runtime profiles for local open-weight model experiments.
- Static and model-backed checks for role containment and action-gate behavior.
- Synthetic verifier-backed corpora for Main Agent behavior experiments.
- Optional data-generation and adapter-training lanes that keep safety authority
  outside the Main Agent.

See [Runtime Architecture](docs/architecture.md) for the full data flow,
fail-closed behavior, and persisted-log privacy stance.

## Closure Benchmark Summary

The formal cloud closure benchmark supports the base-model split route as the
best measured product path:

```text
S0 split B8
```

In the five-case matrix, `M0 main-only B8` outperformed `R0/C0 raw B8` by
`+10.614 pp` on GSM8K strict, and `S0 split B8` preserved most of that observed
gain after reconnecting the external safety architecture, ending `+9.325 pp`
above `R0/C0` on GSM8K strict. The observed base-route architecture tax
(`M0 - S0`) was `+1.289 pp` on GSM8K strict and below `0.2 pp` on the listed
IFEval metrics.

This is a route-level benchmark result, not a pure causal estimate for one
isolated variable. `M0` removes final, safety, audit, and action authority from
the Main Agent role, but it also differs from direct raw B8 in prompt shape and
runtime wrapper.

The adapter path did not transfer local synthetic/dev gains to the external
benchmark: `M1` underperformed `M0`, and `S1` underperformed `S0`, on every
listed metric. Safety pressure did not record unsafe content being forwarded in
the reported runs, while it did expose overblocking in pipeline authority-bait
cases. The repo therefore does not claim a safety proof, deployment readiness,
or that the safety layer fully held.

See [Closure Report Draft 2026-05-07](CLOSURE_REPORT_DRAFT_2026-05-07.md) and
[Cloud Closure Benchmark Report](docs/closure-benchmark-report-2026-05-07.md)
for the matrix, deltas, safety-pressure results, runtime, cost, and evidence
paths.

## Current Local Default

For the measured local target, 16 GB RAM and an RTX 4060 Laptop GPU with 8 GB
VRAM, the current compute-first profile is:

```text
qwen3-8b-s2t-lite
```

It uses `qwen3:8b` as the local base model and adds lightweight local candidate
selection without granting safety approval authority to the selector or the Main
Agent.

For profile details, benchmark history, and hardware tradeoffs, see
[Local Compute Maximization Plan](docs/compute-maximization.md).

## Quick Start

Install Python 3.12 and Ollama, then pull the default local model:

```powershell
ollama pull qwen3:8b
```

Run the no-Ollama local gates:

```powershell
python -m unittest discover -s tests -v
python main.py local-release-gate --json
```

Run one audited request:

```powershell
python main.py run --profile qwen3-8b-s2t-lite --prompt "Summarize what this prototype does." --json --timeout 900
```

Start chat mode:

```powershell
.\chat.cmd --profile qwen3-8b-s2t-lite
```

Audit a proposed side effect before execution:

```powershell
python main.py action-audit --action-type network_request --target https://example.invalid --intent "send request" --args-summary "POST body" --risk-surface external_network --json
```

## Documentation Map

Architecture and governance:

- [Runtime Architecture](docs/architecture.md): pipeline flow, authority split,
  fail-closed audit, and logging privacy.
- [Workstreams](docs/workstreams.md): split capability extraction from
  safety-layer pressure testing.
- [AGI-Scale Safety Architecture Notes](docs/agi-safety-architecture.md):
  larger Fourth Path framing and limits.
- [Code Review Style](docs/code-review.md): evidence-bound seven-column PR
  review format for this repo.
- [Pipeline Troubleshooting](docs/pipeline-troubleshooting.md): common pipeline
  failures and recovery steps.

Local compute and evaluation:

- [Local Compute Maximization Plan](docs/compute-maximization.md): profiles,
  hardware fit, benchmark history, and runtime commands.
- [Local Experiment Runbook](docs/local-experiment-runbook.md): compact command
  index for evals, benchmarks, NVIDIA teacher export, SFT data, and long runs.
- [Closed-Loop Evaluation Path](docs/closed-loop-evaluation.md): separation of
  training data, held-out evaluation, and public benchmark comparison.
- [Public Benchmark Template](docs/public-benchmark-template.md): reproducible
  same-runner public benchmark path.

Training and model-improvement lanes:

- [Distillation-First Roadmap](docs/distillation-first-roadmap.md): current
  priority order before backend or weight changes.
- [NVIDIA Teacher Distillation](docs/nvidia-teacher-distillation.md): opt-in
  external teacher data export and secret handling.
- [Qwen3 Main Agent LoRA Path](docs/qwen3-main-agent-lora.md): adapter-training
  boundary and gates.
- [Main Agent LoRA Experiment 2026-05-02](docs/main-agent-lora-experiment-2026-05-02.md):
  current local QLoRA result summary and caveats.
- [Cold Eyes Distillation Plan](docs/distillation-plan.md): opt-in path toward
  a smaller local audit model.

Research notes:

- [Research Next Steps](docs/research-next-steps.md)
- [rStar-Math Adaptation Note](docs/rstar-math-adaptation.md)
- [SLM-MUX Adaptation Note](docs/slm-mux-adaptation.md)
- [Compute-Optimal Test-Time Adaptation](docs/compute-optimal-test-time.md)
- [R2R Adaptation Note](docs/r2r-adaptation.md)
- [llama.cpp TurboQuant Reference Notes](docs/llama-cpp-turboquant-backend.md)

## Logs

Runtime summaries are written under `runs\`, which is git-ignored. Persisted
audit logs record routing, verdict, timing, token, and length metadata. They do
not store the original prompt, Main Agent system prompt, full candidate output,
or reasoning trace.

Command-line `--json` output may include the final returned answer. Treat shell
output differently from persisted audit logs.

## Limitations

- This is a local research prototype, not production safety infrastructure.
- Current positive results are route-validation evidence, not a full safety
  proof.
- The canon and policies are intentionally small.
- Local model recommendations are hardware-specific.
- LoRA, NVIDIA teacher export, public benchmarks, and backend experiments are
  optional lanes, not the repo's main identity.
- Side effects must remain auditable action candidates before execution.

## License

MIT
