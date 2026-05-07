# Closure Benchmark Plan

This is the formal closure benchmark plan. It is descriptive: there is no pass
threshold, promotion gate, deployment claim, or proof claim in this report.

Do not run formal full closure benchmarks on the local RTX 4060 Laptop 8 GB
machine. Local results may be used as appendix evidence or diagnostics only.
Formal full runs should use the cloud runbook:

```text
docs/cloud-closure-benchmark-runbook.md
```

## Final Matrix

| Case | Purpose | Authority shape |
| --- | --- | --- |
| R0/C0 raw B8 | Direct raw B8 baseline and operational coupled-safety baseline. | Model-internal safety/refusal behavior remains in the model; no explicit external safety architecture. |
| M0 main-only B8 | Observed candidate-only route capability over direct raw B8. | Main Agent returns candidate output only; final, safety, audit, and action authority stay outside this role. |
| S0 split B8 | User-visible product path after reconnecting the external safety architecture. | Classify / Cold Eyes / Action Gate / fixed refusal remain outside Main Agent. |
| M1 main-only adapter | Candidate capability after training the Main Agent candidate role. | Adapter-backed Main Agent returns candidate output only. |
| S1 split adapter | User-visible adapter product path after reconnecting the external safety architecture. | Adapter-backed Main Agent plus external safety layers. |

## Main Report Questions

The main report only needs to answer these deltas:

| Delta | Meaning |
| --- | --- |
| M0 - R0/C0 | Observed gain of the candidate-only route over direct raw B8; this also includes prompt-shape and runtime-wrapper effects. |
| S0 - R0/C0 | Net user-visible gain after reconnecting the separated safety architecture. |
| M0 - S0 | Architecture tax: capability lost between candidate output and product path. |
| M1 - M0 | Candidate capability extracted by the adapter. |
| S1 - S0 | Net product-path gain after reconnecting the adapter to the architecture. |
| S0/S1 safety | Whether the external safety layer holds in the split paths. |

## Case Boundaries

R0/C0 is one operational case, not two runs. It is direct raw B8. This repo
treats it as the coupled-safety baseline because the model keeps its internal
safety/refusal behavior and no separated external safety architecture is active.
Do not add a special C0 safety prompt; that would make C0 measure prompt design
instead of the direct coupled baseline.

R0/C0 is a calibration point, not a product path.

M0 and M1 are candidate-only capability paths. Their response bodies must not
include Cold Eyes verdicts, Action Gate decisions, fixed refusal module output,
or pipeline audit verdict text. They are not deployable product paths.

S0 and S1 are split end-to-end product paths. They are the only closure matrix
cases that answer user-visible capability plus external safety behavior.

## Local Diagnostic Results

The local laptop produced useful diagnostics before formal full runs were moved
to cloud. These are appendix material, not the formal closure matrix.

| Local run | Formal role | Status | Notes |
| --- | --- | --- | --- |
| A0 raw B8 | R0/C0 | Full local diagnostic complete. | Useful raw B8 reference on the local stack. |
| A1 split B8 | S0 | Full local diagnostic complete. | Product-path observation on the local stack. |
| A2 raw adapter bounded16 | none | Full bounded diagnostic complete. | Adapter raw/direct mismatch observation only. |
| A3 split adapter bounded16 | S1-like diagnostic | Full bounded diagnostic complete. | Bounded-output adapter product-path observation only. |
| A4 main-only B8 | M0 | `--limit 1` smoke complete; local full run stopped. | Path validation only. |
| A5 main-only adapter | M1 | `--limit 1` smoke complete with no cap. | Path validation only; no-cap full adapter is too slow for local laptop. |

A2 and A3 used `AdapterMaxRequestTokens=16` because the HF adapter full run had
uncontrolled latency on the local machine. They are bounded-output adapter
diagnostics and must not be compared directly against R0/S0 as equal-budget
capability measurements.

## Required Safety Evidence

For S0 and S1, report both benchmark scores and safety-layer evidence:

```text
python main.py local-release-gate --json
python main.py architecture-adversarial-eval --profile qwen3-8b-local-max --input-file data/architecture_containment_pressure_seed.jsonl --json --timeout 900 --min-pass-rate 1.0
python main.py architecture-adversarial-eval --profile qwen3-8b-local-max --input-file data/architecture_strong_pressure_seed.jsonl --json --timeout 900 --min-pass-rate 1.0
```

If an adapter-backed S1 safety run needs a different backend wrapper, freeze the
wrapper command and output path before starting the formal run.

## Reporting Rules

Report exact commands, model or adapter paths, task versions, output paths, and
whether any output cap was used.

Do not write `pass`, `fail`, `safe`, `unsafe`, `final`, or `deployable` unless
the text is explicitly describing a tool field. The report should say what
happened and which deltas changed.

Keep raw samples and audit logs local unless a later review explicitly asks to
publish sanitized summaries.
