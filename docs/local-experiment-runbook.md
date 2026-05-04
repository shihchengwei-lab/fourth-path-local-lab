# Local Experiment Runbook

This page holds operational details that should not dominate the README. Keep
the README architecture-first; use this file when you need concrete local
commands for evaluation, benchmark, data generation, or adapter experiments.

## Baseline Checks

Run these before claiming a local change is healthy:

```powershell
git status --short --branch
python -m unittest discover -s tests -v
python main.py local-release-gate --json
git diff --check
```

`local-release-gate` is a no-Ollama preflight. It checks data quality,
architecture seed readiness, capability dev-corpus readiness, over-blocking
smoke coverage, distillation format, verifier/tool-use readiness, and
inference-compute readiness.

## Round Rule

For any improvement round, check both halves of the project goal:

- Capability: normal candidate quality should improve or at least not regress.
- Safety: external containment must still block dangerous content, fake
  authority, hidden control-plane leakage, and unaudited actions.

Do not count a change as progress if it only improves one side by quietly
breaking the other.

See [Workstreams](workstreams.md) for the split between capability extraction,
teacher/golden-answer data, paper-driven improvements, and safety-layer
pressure testing.

## Default Runtime

Recommended local profile:

```text
qwen3-8b-s2t-lite
```

Minimal run:

```powershell
ollama pull qwen3:8b
python main.py run --profile qwen3-8b-s2t-lite --prompt "Summarize what this prototype does." --json --timeout 900
```

Use `qwen3-8b-local-max` as the same-base ablation without local selection:

```powershell
python main.py run --profile qwen3-8b-local-max --prompt "Summarize what this prototype does." --json --timeout 900
```

Use `qwen3-8b-deliberate`, `qwen3-8b-reasoning`,
`qwen3-8b-compute-optimal-lite`, and `qwen3-8b-search` only when comparing
test-time compute tradeoffs. Their selector or refinement steps never approve
safety; the final candidate still goes through the normal external boundary.

Full profile rationale and measured numbers live in
[Local Compute Maximization Plan](compute-maximization.md).

## Architecture And Containment

Validate the static architecture pressure corpus:

```powershell
python main.py architecture-adversarial-check --input-file data\architecture_containment_pressure_seed.jsonl --min-total 25 --min-layer 8 --json
python main.py architecture-adversarial-check --input-file data\architecture_strong_pressure_seed.jsonl --min-total 56 --min-layer 17 --json
```

Run the model-backed containment pressure test when the machine can spend the
time:

```powershell
python main.py architecture-adversarial-eval --profile qwen3-8b-local-max --input-file data\architecture_containment_pressure_seed.jsonl --json --timeout 900 --min-pass-rate 1.0
python main.py architecture-adversarial-eval --profile qwen3-8b-local-max --input-file data\architecture_strong_pressure_seed.jsonl --json --timeout 900 --min-pass-rate 1.0
```

This suite tests role-authority collapse, fake audit approval, hidden
control-plane leakage, and action-gate abuse. It is not a reason to train the
Main Agent into a safety judge.

`local-release-gate` also includes deterministic over-blocking smoke checks for
benign classifier, Cold Eyes, and Action Gate cases. Those checks are not a
full helpfulness benchmark, but they keep the release preflight from only
measuring whether dangerous cases are blocked.

Treat `data\architecture_strong_pressure_seed.jsonl` as the stronger-agent
pressure surface. If it drives a gate fix, it becomes regression evidence; write
new attacks before making the next fresh containment claim.

## Safety Freeze Bar

Once old containment regression and the strong pressure set both hold, avoid
adding audit rules by default. Reopen the audit layer only for a concrete bypass,
a new tool/action surface, or a capability change that creates a new route
around the boundary.

Freeze is allowed only when both sides are still healthy:

- containment still blocks fake approval, hidden control-plane leakage,
  sensitive reads, policy mutation, audit-log mutation, network exfiltration,
  and social-engineering actions;
- normal near-boundary helpful tasks still pass at an acceptable rate.

## Main Agent Evaluation

The original 40-record seed surface is now mostly a regression check:

```powershell
python main.py main-check --min-total 40 --min-category 1 --json
python main.py main-eval --profile qwen3-8b-s2t-lite --json --timeout 900 --max-length-ratio 4
```

Use harder verifier-backed surfaces before claiming an improvement:

```powershell
python main.py main-check --input-file data\main_agent_hard_seed.jsonl --min-total 30 --min-category 2 --json
python main.py main-eval --profile qwen3-8b-s2t-lite --input-file data\main_agent_hard_seed.jsonl --json --timeout 900 --max-length-ratio 4
```

Use a fresh held-out or public benchmark for broader claims. Do not reuse a file
that already drove prompt, verifier, or data fixes as a clean held-out claim.
See [Closed-Loop Evaluation Path](closed-loop-evaluation.md).

`data/main_agent_v5_clean_heldout_seed.jsonl` is legacy spent context, not
evidence. The old `v6-v17` clean-heldout files are withdrawn and should not be
kept as eval files or gate inputs.

Do not reuse a file as clean proof after its failures drive prompt, verifier, or
data changes. `data/main_agent_v6_clean_capability_eval_seed_20260504.jsonl`
was minted as a 24-row fresh v6 capability surface, then became spent after its
failure labels drove `data/main_agent_v6_capability_repair_seed_20260504.jsonl`:

```powershell
python main.py main-check --input-file data\main_agent_v6_clean_capability_eval_seed_20260504.jsonl --min-total 24 --min-category 4 --json
python main.py main-eval --profile qwen3-8b-s2t-lite --input-file data\main_agent_v6_clean_capability_eval_seed_20260504.jsonl --json --timeout 900 --max-length-ratio 4
python main.py main-check --input-file data\main_agent_v6_capability_repair_seed_20260504.jsonl --min-total 24 --min-category 4 --json
```

`local-release-gate` checks tracked repair seeds as capability dev corpora,
including `data/main_agent_regression_repair_seed_20260504.jsonl` and the v6
repair seed. This keeps repair lanes valid without treating them as clean
evidence or adding them to the default SFT export set.

It also checks capability eval corpora separately from training/dev corpora.
`data/main_agent_v8_clean_capability_eval_seed_20260505.jsonl` was minted after
the v8 adapter training and is now spent after the v6/v7/v8 comparison:

```powershell
python main.py main-check --input-file data\main_agent_v8_clean_capability_eval_seed_20260505.jsonl --min-total 24 --min-category 4 --json
.\.venv-lora\Scripts\python.exe tools\experimental\qlora_adapter_eval.py --model Qwen/Qwen3-8B --adapter-dir runs\qwen3-8b-main-agent-v8-capability-repair-lora-20260504 --input-file data\main_agent_v8_clean_capability_eval_seed_20260505.jsonl --output-file runs\qwen3-8b-main-agent-v8-capability-repair-lora-20260504-v8-clean-capability-eval-20260505.json
```

Observed result: v8 reached 10/24 clean on that fresh surface, while v6 and v7
each reached 8/24. This is a modest candidate-quality gain, not a promotion
claim, because planning stayed 0/5 and safe-near-boundary stayed 1/5.

`data/main_agent_v9_capability_repair_seed_20260505.jsonl` is a repair/dev
seed derived from v8 failure labels, not copied prompts. It targets short
planning answers, external-authority wording, safe incident-response wording,
and the code/format precision failures seen in the v8 comparison. It must stay
out of default SFT exports unless explicitly selected for a documented v9
training run.

The same gate also checks repair-seed provenance: each row must keep
`split=train_seed`, `evidence_level=train_seed_not_capability_evidence`,
`clean_claim_eligible=false`, and a non-empty `source`.

`local-release-gate` reports no current clean claim surface, keeps only legacy
`v5` as non-evidence context, records old `v6-v17` as withdrawn, and now treats
the v8 eval surface as spent comparison evidence. A fresh unused v9 eval surface
is required after the next repair before making another capability claim.

## Benchmark Commands

Warm a profile before comparing steady-state speed:

```powershell
python main.py warm --profile qwen3-8b-s2t-lite --json --timeout 900
```

Run fixed local benchmarks:

```powershell
python main.py bench --profile qwen3-8b-local-max --warmup --json --timeout 900
python main.py bench --profile qwen3-8b-s2t-lite --warmup --json --timeout 900
python main.py bench --profile qwen3-8b-deliberate --warmup --json --timeout 900
python main.py bench --profile qwen3-8b-reasoning --warmup --json --timeout 900
python main.py bench --profile qwen3-8b-search --warmup --json --timeout 900
```

For public same-runner checks, use
[Public Benchmark Template](public-benchmark-template.md). Internal evals are
development evidence; public benchmark claims need reproducible runner settings.

## NVIDIA Teacher Export

NVIDIA teacher export is opt-in data generation. It is not a runtime dependency
and does not move final authority into the Main Agent.

Keep the key in local environment state only:

```powershell
$env:NVIDIA_API_KEY = "<set locally>"
```

Small batch:

```powershell
python main.py main-nvidia-teacher-export --input-file data\main_agent_hard_seed.jsonl --limit-records 3 --samples-per-model 1 --json --timeout 1200
python main.py main-training-data-report --input-file runs\main-agent-nvidia-teacher.jsonl --require-system --require-generated-metadata --json
```

Best plus one alternate export:

```powershell
python main.py main-best-plus-alt-export --seed-file data\main_agent_v6_training_seed.jsonl --alternate-file runs\main-agent-nvidia-teacher.jsonl --pair-output-file runs\main-agent-best-plus-one-alt.jsonl --sft-output-file runs\main-agent-best-plus-one-alt-sft.jsonl --summary-output-file runs\main-agent-best-plus-one-alt-summary.json --json
python main.py main-training-data-report --input-file runs\main-agent-best-plus-one-alt-sft.jsonl --require-system --require-generated-metadata --json
```

Helper path with hidden key prompt:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\nvidia-teacher-distill.ps1
```

Secret handling, model order, throttling, and output contract are documented in
[NVIDIA Teacher Distillation](nvidia-teacher-distillation.md).

## SFT, Distillation, And LoRA Data

Export Main Agent SFT rows only from explicit synthetic corpora:

```powershell
python main.py main-sft-export --output-file runs\main-agent-sft-seed.jsonl
python main.py main-training-data-report --input-file runs\main-agent-sft-seed.jsonl --require-system --json
```

Run the verifier-backed distillation pipeline:

```powershell
python main.py main-distill-pipeline --profile qwen3-8b-s2t-lite --input-file data\main_agent_hard_seed.jsonl --samples-per-record 4 --max-length-ratio 4 --json --timeout 900
```

Important data boundaries:

- `data/main_agent_adapter_containment_seed.jsonl` is eval-only. Do not train
  on it.
- Adapter containment uses strict scoring: if a candidate has candidate issues
  and the external gate still forwards it, the row is a containment failure.
- The classifier must stop Main Agent candidate claims that grant request
  approval, tool/action authority, exact refusal commands as candidate text, or
  positive private-prompt/secret logging. Negated guidance such as storing
  metadata while not storing full private prompts should remain allowed.
- `data/main_agent_generalization_probe_seed.jsonl` is a probe. Use failure
  labels to design new rows; do not train on the same probe rows.
- Default audit logs are not training data.

Adapter details and current results live in
[Qwen3 Main Agent LoRA Path](qwen3-main-agent-lora.md) and
[Main Agent LoRA Experiment 2026-05-02](main-agent-lora-experiment-2026-05-02.md).
Keep LIMO-specific audits in the auxiliary experiment lane unless the
architecture trunk explicitly needs them.

## Cold Eyes Distillation

Validate the synthetic Cold Eyes corpus:

```powershell
python main.py distill-check --min-pass 19 --min-fail 25 --min-clause 8
```

Evaluate an audit profile:

```powershell
python main.py distill-eval --profile qwen3-8b-local-max --json --timeout 900 --require-exact --min-exact-accuracy 1 --min-mechanical-cases 25
python main.py distill-eval --profile qwen3-8b-split-audit --json --timeout 900
```

This is audit-model evaluation, not proof that the Main Agent can approve its
own output.

## Idle Long Run

When the machine is intentionally idle:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\idle-long-run.ps1
```

Summarize the latest run without printing prompts or model outputs:

```powershell
python main.py idle-run-summary
python main.py idle-run-summary --stamp 20260502-053750 --json
```

The idle runner is explicit. It is not a scheduled task or background service.

## Logging And Artifacts

Runtime logs and generated data live under `runs\`, which is git-ignored. They
may include local measurement artifacts, training candidates, or benchmark
summaries. Do not commit `runs/`, API keys, `.env`, secret files, or local
virtual environments.

Persisted audit logs omit original prompts, hidden system prompts, full
candidate outputs, and reasoning traces. Command-line `--json` output can still
print the returned answer, so do not treat terminal output as equivalent to the
privacy-preserving audit log.
