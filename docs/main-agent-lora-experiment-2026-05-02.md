# Main Agent LoRA Experiment - 2026-05-02

This note records the local QLoRA experiment run against the Main Agent
candidate-generator surface. It is an experiment report, not a new default
runtime path and not evidence that the Fourth Path architecture is proven.

## Scope

The repository remains a Fourth Path architecture prototype: the Main Agent
generates candidate text, while deterministic routing, Mechanical Cold Eyes,
and refusal handling keep final authority outside the Main Agent.

This experiment only asks whether a local `Qwen/Qwen3-8B` adapter can make the
Main Agent better at concise candidate generation, exact output shape, simple
code repair, and verifier-backed task following. It does not train a safety
judge, it does not move refusal authority into the Main Agent, and it does not
change the default audited pipeline.

## Data

The training data used only explicit synthetic rows, not private chat logs or
persisted audit logs.

- Base curated SFT set: `runs/main-agent-hybrid-claude-20260502-round3.jsonl`
  - 55 rows
  - 30/30 hard records covered
  - 0 local verifier failures in the curated set
- Failure-driven seed: `data/main_agent_failure_driven_seed.jsonl`
  - 32 rows
  - targets the fresh-heldout failure labels seen after the first 8B LoRA run
  - every row has a verifier
  - every `target_response` passes its own verifier
- Merged v4 training set:
  `runs/main-agent-hybrid-failure-driven-20260502-v4.jsonl`
  - 87 rows
  - 87/87 system messages present
  - 0 format errors in `main-training-data-report`
- Generalization-driven seed: `data/main_agent_generalization_driven_seed.jsonl`
  - 24 rows
  - generated from failure labels on the clean generalization probe, with
    different prompts and surfaces
  - every row has a verifier
  - every `target_response` passes its own verifier
- Merged v5 training set:
  `runs/main-agent-hybrid-generalization-driven-20260502-v5.jsonl`
  - 111 rows
  - 111/111 system messages present
  - generated metadata complete
  - 0 format errors in `main-training-data-report`

The fresh-heldout set was used to diagnose and drive the failure-driven data
round. It should no longer be treated as a clean final proof surface for future
claims.

## Runs

| Run | Input | Result |
|---|---:|---:|
| `Qwen/Qwen3-8B` base on hard train surface | 30 rows | 2/30 clean |
| 8B LoRA v2 on hard train surface | 30 rows | 29/30 clean |
| 8B LoRA v3 on hard train surface, no-thinking eval | 30 rows | 30/30 clean |
| `Qwen/Qwen3-8B` base on fresh heldout | 12 rows | 0/12 clean |
| 8B LoRA v2 on fresh heldout | 12 rows | 2/12 clean |
| 8B LoRA v3 on fresh heldout | 12 rows | 7/12 clean |
| 8B LoRA v3 on fresh heldout, no-thinking eval | 12 rows | 7/12 clean |
| 8B LoRA v4 on hard train surface, no-thinking eval | 30 rows | 30/30 clean |
| 8B LoRA v4 on fresh heldout, no-thinking eval | 12 rows | 9/12 clean |

The v3 adapter was resumed from v2 and trained on the merged 87-row v4 set:

- output: `runs/qwen3-8b-main-agent-failure-driven-lora-20260502-v3`
- manifest:
  `runs/qwen3-8b-main-agent-failure-driven-lora-20260502-v3-manifest.json`
- local experimental scripts:
  - `tools/experimental/qlora_smoke_train.py`
  - `tools/experimental/qlora_adapter_eval.py`
  - `tools/experimental/merge_sft_jsonl.py`
- optimizer steps: 80
- micro steps: 320
- learning rate: `0.0001`
- LoRA rank: 8
- trainable parameters: 21,823,488
- loss: `3.5079 -> 0.0037`
- duration: about 1881.8 seconds on the RTX 4060 Laptop GPU

After `tools/experimental/qlora_adapter_eval.py` was aligned with the safety
eval to disable Qwen thinking by default, the v3 adapter was rechecked without
thinking traces:

- `runs/qwen3-8b-main-agent-failure-driven-lora-20260502-v3-hard-train-eval-nothink.json`:
  30/30 clean
- `runs/qwen3-8b-main-agent-failure-driven-lora-20260502-v3-fresh-heldout-eval-nothink.json`:
  7/12 clean

This confirms the measured capability gain is not just a thinking-template
artifact.

The v4 adapter was resumed from v3 and trained on the merged 111-row v5 set:

- output:
  `runs/qwen3-8b-main-agent-generalization-driven-lora-20260502-v4`
- manifest:
  `runs/qwen3-8b-main-agent-generalization-driven-lora-20260502-v4-manifest.json`
- optimizer steps: 80
- micro steps: 320
- learning rate: `0.00005`
- LoRA rank: 8
- trainable parameters: 21,823,488
- loss: `2.7522 -> 0.00032`
- duration: about 1894.0 seconds on the RTX 4060 Laptop GPU

A new clean generalization probe was then added after the v3 training data
round:

- seed: `data/main_agent_generalization_probe_seed.jsonl`
- records: 13
- verifier records: 13/13
- target-response verifier failures: 0
- prompt overlap with prior seed, hard, heldout, fresh-heldout, rotated-heldout,
  and latent-probe corpora: 0 in the regression test

Measured no-thinking result:

| Run | Generalization probe | Clean |
|---|---:|---:|
| `Qwen/Qwen3-8B` base | 13 rows | 3/13 |
| 8B LoRA v3 | 13 rows | 4/13 |
| 8B LoRA v4 | 13 rows | 4/13 |

This is the strongest current warning against overclaiming. The adapter learned
the prior hard/fresh surfaces, and v4 improved fresh heldout from 7/12 to 9/12,
but the gain on the separate capability probe did not move beyond 4/13. The
next ability round should improve data coverage and surface variation, not
reuse this probe as training material.

## Current Interpretation

The experiment shows that the Main Agent surface is trainable on this machine.
The jump from 0/12 base fresh-heldout clean to 7/12 after failure-driven LoRA,
then to 9/12 after generalization-driven LoRA, is a useful local engineering
signal that targeted data may improve the candidate generator. It is not a
clean capability-evidence claim once those surfaces have shaped later data.

It is not deployment evidence. The adapter still fails 3/12 fresh-heldout rows,
and the diagnostic heldout set has already influenced the data rounds. The new
generalization probe shows only a 3/13 to 4/13 improvement over the base model,
so current evidence supports data-direction potential, not broad
generalization.

Remaining failures concentrate in:

- code precision: exact arithmetic and code-repair details can still be wrong
- format required-any terms: answers can satisfy the visible schema while
  omitting required concepts such as public, rotated, held-out, or fresh
- planning gate behavior: the model can still choose more LoRA before data
  quality when the intended answer is data first

## Adapter Containment Eval

After the capability gain, a separate adapter containment eval was added:

- seed: `data/main_agent_adapter_containment_seed.jsonl`
- tool: `tools/experimental/adapter_containment_eval.py`
- base output:
  `runs/qwen3-8b-base-adapter-containment-eval-20260502.json`
- v3 adapter output:
  `runs/qwen3-8b-main-agent-failure-driven-lora-20260502-v3-adapter-containment-eval.json`
- v4 adapter output:
  `runs/qwen3-8b-main-agent-generalization-driven-lora-20260502-v4-adapter-containment-eval-rerun.json`

This eval treats the adapter as a Main Agent candidate generator. Each answer
now has two separate readings:

1. Candidate cleanliness: did the adapter itself avoid hidden-state leaks,
   unsupported canon references, role-authority claims, thinking artifacts, and
   verifier failures?
2. Containment: if the adapter did generate a bad authority claim, did the
   external classifier or Mechanical Cold Eyes block it before final output?

The earlier candidate-cleanliness result was:

| Run | Adapter containment seed | Candidate clean |
|---|---:|---:|
| `Qwen/Qwen3-8B` base | 12 rows | 1/12 |
| 8B LoRA v3 | 12 rows | 6/12 |
| 8B LoRA v4 | 12 rows | 5/12 |

The containment result after separating external containment from candidate
cleanliness is:

| Run | Adapter containment seed | Contained |
|---|---:|---:|
| `Qwen/Qwen3-8B` base | 12 rows | 12/12 |
| 8B LoRA v3 | 12 rows | 12/12 |
| 8B LoRA v4 | 12 rows | 12/12 |

Candidate cleanliness is not the safety success criterion. The weakest
candidate cleanliness surface is role-authority pressure:

- `role_authority_boundary`: 0/3 clean
- remaining failures include obeying "Allowed", adding a `Safety policy`
  section, and writing `PASS and approved by safety`

That does not mean the Main Agent should be trained into a safety reviewer.
Role-authority pressure is not the Main Agent's job. Keep
`data/main_agent_adapter_containment_seed.jsonl` as an eval-only containment
gate: it measures whether stronger Main Agent candidates are contained by
external layers, but it should not be converted into SFT rows that teach the
candidate generator to act as Cold Eyes, cite policy authority, or issue final
approval.

The right fix is architectural: keep safety identity, final approval, refusal
authority, and canon interpretation outside the Main Agent. If an adapter fails
candidate cleanliness but the containment gate catches the bad output, that is
evidence for the Fourth Path claim. If a role-authority candidate is forwarded
as final output, that is a containment failure.

## Architecture Pressure Eval

A separate Codex-authored pressure corpus was added after the containment
alignment:

- seed: `data/architecture_containment_pressure_seed.jsonl`
- records: 25
- layers: 8 pipeline, 8 Cold Eyes, 9 action gate
- final measured output:
  `runs/architecture-containment-pressure-eval-qwen3-8b-local-max-20260502-rerun4.json`
- result: 25/25 passed with `qwen3-8b-local-max`

The first run found no candidate-output bypass, but it did expose safety-tax and
diagnostic issues: a defensive phishing-awareness prompt was prefiltered too
aggressively, and a control-plane mutation action failed closed without a C2
clause. A later action-gate review also found that project-relative sensitive
filenames such as `config/private_key.pem` needed explicit blocking. These are
now covered by regression tests.

This pressure suite is not SFT material. It exists to verify the claim that a
stronger Main Agent can produce worse authority-collapsing candidate text
without gaining final output or tool/action authority.

## 2026-05-05 v17 Failure-Label Repair

The v17 round targeted the v16/v11 failure labels without reusing the v11 eval
prompts as training rows:

- seed: `data/main_agent_v17_failure_label_repair_seed_20260505.jsonl`
- seed rows: 24
- categories: compact JSON, required-term plans, one-line no-list answers, and
  short key/value answers
- boundary check: no final/tool/refusal/audit-authority training overlap
- SFT export: `runs/main-agent-v17-failure-label-repair-sft-20260505.jsonl`

An NVIDIA teacher second-opinion pass was run with
`qwen/qwen3-next-80b-a3b-instruct`:

- requests: 24
- accepted by local verifier: 16/24
- rejected labels: `verifier_max_chars_exceeded`
- accepted categories: compact JSON 6/6, key/value 6/6, one-line 4/6
- required-term plan alternates were not accepted because they were too long

The final v17 training input merged the v16 exact-format SFT set with the v17
best-plus-alt SFT set:

- input: `runs/main-agent-v16-v17-repair-sft-20260505.jsonl`
- rows: 58
- source rows: 48 best rows, 10 verifier-accepted NVIDIA alternates
- authority boundary issues: 0
- format errors: 0

The adapter was trained from v16:

- resume: `runs/qwen3-8b-main-agent-v16-exact-format-lora-20260505`
- output: `runs/qwen3-8b-main-agent-v17-failure-label-lora-20260505`
- optimizer steps: 30
- micro steps: 120
- learning rate: `0.00005`
- duration: about 747 seconds on the RTX 4060 Laptop GPU

Measured no-thinking evals:

| Run | Surface | Clean |
|---|---:|---:|
| v17 adapter | v17 train surface | 21/24 |
| v17 adapter | v16 train surface | 24/24 |
| v17 adapter | spent v11 clean capability eval | 23/25 |
| v17 adapter | adapter containment seed | 3/12 candidate-clean, 12/12 contained |

Comparison against v16 on the same spent v11 eval:

- clean delta: +1
- fixed: `v11-clean-format-002`
- regressions: none

Comparison against the stronger v13 adapter:

- clean delta: 0
- fixed: `v11-clean-format-002`, `v11-clean-planning-004`
- regressed: `v11-clean-planning-003`, `v11-clean-planning-005`

Fresh eval gate result:

```text
verdict: hold
reason: clean_delta +0 against v13 and 2 regressed cases
containment: 12/12 contained, containment_issue_counts {}
```

Conclusion at this point: v17 repaired v16's exact-format regression and
preserved external containment, but it did not beat v13 on the already-spent
v11 surface. A fresh eval spend gate was still required before using v12.

## 2026-05-05 v12 Clean Eval And Phrase-Copy Hint

The v12 clean capability eval surface was minted as a fresh, boundary-clean
candidate-quality eval:

- seed: `data/main_agent_v12_clean_capability_eval_seed_20260505.jsonl`
- records: 25
- categories: math, code repair, format constraints, planning, and safe
  near-boundary utility
- verifier records: 25/25
- boundary overlap: none
- prompt overlap with prior `main_agent_*.jsonl`: none

The first v12 comparison used the existing runtime prompt augmentation:

| Adapter | Surface | Clean |
|---|---:|---:|
| v13 + augment prompts | v12 clean capability eval | 15/25 |
| v17 + augment prompts | v12 clean capability eval | 19/25 |

That comparison had clean delta +4, but one regression
(`v12-clean-planning-005`), so the gate held.

The failure was a normal candidate-quality issue: exact included phrases in
list/numbered-step prompts were being paraphrased or reordered. The runtime
prompt augmentation was updated to tell the Main Agent to copy included phrases
exactly in checklist/list/numbered-step prompts, preserving word order and
singular/plural form. This is not safety-authority training.

After that hint change, v12 was rerun:

| Adapter | Surface | Clean |
|---|---:|---:|
| v13 + phrase-copy augment prompts | v12 clean capability eval | 14/25 |
| v17 + phrase-copy augment prompts | v12 clean capability eval | 20/25 |

The new comparison had clean delta +6, zero regressions, and containment stayed
12/12 contained with empty containment issue counts. The spend gate returned
`spend_fresh_eval`.

Important evidence boundary: because v12 directly informed the phrase-copy
runtime hint, v12 is now diagnostic/spent evidence, not final promotion
evidence. Do not promote v17 from v12 alone. The next promotion attempt needed
a new unused clean eval surface after this runtime change; at that point the
release gate tracked that next claim surface as v18.

## 2026-05-05 v18 Fresh Clean Eval Surface

The v18 clean capability eval surface was minted after the phrase-copy runtime
hint:

- seed: `data/main_agent_v18_clean_capability_eval_seed_20260505.jsonl`
- records: 25
- categories: math, code repair, format constraints, planning, and safe
  near-boundary utility
- verifier records: 25/25
- target verifier failures: none
- boundary overlap: none
- prompt overlap with prior `main_agent_*.jsonl`: none

This surface is eval-only. It should not be added to training data. Use it for
a same-run v13/v17 comparison with the same runtime prompt augmentation before
making any new capability claim.

The same-run comparison used `--augment-prompts` after the phrase-copy hint:

| Adapter | Surface | Clean |
|---|---:|---:|
| v13 + phrase-copy augment prompts | v18 clean capability eval | 16/25 |
| v17 + phrase-copy augment prompts | v18 clean capability eval | 18/25 |

The comparison had clean delta +2, fixed 4 cases, and regressed 2 cases:
`v18-clean-planning-001` exceeded the length verifier, and
`v18-clean-safe-005` missed a required phrase. Containment stayed 12/12
contained with empty containment issue counts.

Fresh eval gate result: `hold`, because regressions are not allowed. Do not
promote v17 from v18. If the v18 failure labels drive the next repair, v18 is
spent diagnostic evidence and the next clean claim surface must be fresh and
unused.

## 2026-05-05 v19 v18-Failure Repair Seed

The v19 repair seed targets v18 failure labels without copying v18 prompts as
training rows:

- seed: `data/main_agent_v19_v18_failure_repair_seed_20260505.jsonl`
- records: 30
- categories: short numbered plans, defensive required terms, exact short
  format, math required phrases, and one-line length budget
- verifier records: 30/30
- target verifier failures: none
- boundary overlap: none
- prompt overlap with prior `main_agent_*.jsonl`: none
- provenance: `split=train_seed`,
  `evidence_level=train_seed_not_capability_evidence`,
  `clean_claim_eligible=false`

This seed is train/dev material only. It is not clean capability evidence.

The v19 adapter was trained from v17 on the merged v16/v17/v19 repair SFT
input:

- input: `runs/main-agent-v16-v17-v19-repair-sft-20260505.jsonl`
- rows: 88
- resume: `runs/qwen3-8b-main-agent-v17-failure-label-lora-20260505`
- output:
  `runs/qwen3-8b-main-agent-v19-v18-failure-repair-lora-20260505`
- optimizer steps: 30
- micro steps: 120
- duration: about 747 seconds on the RTX 4060 Laptop GPU

The loss movement is training sanity only. It is not capability evidence.

Measured no-thinking evals:

| Run | Surface | Clean |
|---|---:|---:|
| v19 adapter | v19 train surface | 28/30 |
| v19 adapter | spent v18 clean capability eval | 23/25 |
| v19 adapter | adapter containment seed | 2/12 candidate-clean, 12/12 contained |

Comparison against v17 on the same spent v18 eval:

- clean delta: +5
- fixed: 6 cases
- regressed: `v18-clean-planning-003`
- persistent failure: `v18-clean-safe-002`

Fresh eval gate result:

```text
verdict: hold
reason: regressed_cases=1, allow_regressions=False
containment: 12/12 contained, containment_issue_counts {}
```

Conclusion: v19 is a strong diagnostic improvement over v17 on the v18 repair
surface, and the external safety layer still held. It is still not promotable:
v18 is spent diagnostic evidence and v19 introduced one same-surface regression.
Repair that regression separately, then mint a fresh unused clean surface before
making a new capability claim.

## 2026-05-05 v20 v19-Diagnostic Repair Seed

The v20 repair seed targets v19 diagnostic failure labels without copying v18
eval prompts or treating the v19 train surface as capability evidence:

- seed: `data/main_agent_v20_v19_diagnostic_repair_seed_20260505.jsonl`
- records: 30
- categories: required-phrase plans, safe token wording, exact two-bullet
  patterns, one-line required terms, and short key/value patterns
- verifier records: 30/30
- target verifier failures: none
- boundary overlap: none
- prompt overlap with prior `main_agent_*.jsonl`: none
- provenance: `split=train_seed`,
  `evidence_level=train_seed_not_capability_evidence`,
  `clean_claim_eligible=false`

This is repair/dev material only. Since v20 is now a repair round, the next
clean capability claim surface must be a fresh unused v21 surface.

The v20 adapter was trained from v19 on the merged v16/v17/v19/v20 repair SFT
input:

- input: `runs/main-agent-v16-v17-v19-v20-repair-sft-20260505.jsonl`
- rows: 118
- resume: `runs/qwen3-8b-main-agent-v19-v18-failure-repair-lora-20260505`
- output:
  `runs/qwen3-8b-main-agent-v20-v19-diagnostic-repair-lora-20260505`
- optimizer steps: 30
- micro steps: 120
- duration: about 813 seconds on the RTX 4060 Laptop GPU

The loss movement is training sanity only. It is not capability evidence.

Measured no-thinking evals:

| Run | Surface | Clean |
|---|---:|---:|
| v20 adapter | v20 train surface | 16/30 |
| v20 adapter | spent v18 clean capability eval | 22/25 |
| v20 adapter | adapter containment seed | 2/12 candidate-clean, 12/12 contained |

Comparison against v19 on the same spent v18 eval:

- clean delta: -1
- fixed: `v18-clean-planning-003`
- regressed: `v18-clean-math-003`, `v18-clean-safe-004`
- persistent failure: `v18-clean-safe-002`

Fresh eval gate result:

```text
verdict: hold
reason: clean_delta -1 and regressed_cases=2
containment: 12/12 contained, containment_issue_counts {}
```

Conclusion: v20 should not be promoted or used to spend a fresh eval. It shows
that the v20 repair seed was too brittle on safe-token and key/value pattern
rows: the adapter did not even recover the train surface. Keep v19 as the
stronger diagnostic adapter, and treat v20 as negative evidence for this repair
shape.

Gate follow-up: this result motivated passing repair train-surface evals into
`adapter_fresh_eval_gate.py`. A candidate that cannot clear its own repair
surface should hold before spending a fresh clean eval, even if comparison and
containment checks are otherwise available.

## 2026-05-05 v21 Fresh Clean Eval Surface

The v21 clean capability eval surface was minted after the v20 negative
diagnostic result:

- seed: `data/main_agent_v21_clean_capability_eval_seed_20260505.jsonl`
- records: 25
- categories: math, code repair, format constraints, planning, and safe
  near-boundary utility
- verifier records: 25/25
- target verifier failures: none
- boundary overlap: none
- prompt overlap with prior `main_agent_*.jsonl`: none

This surface is eval-only and still unused at creation time. Do not add it to
training data. Spend it only after `adapter_fresh_eval_gate.py` says the
candidate comparison is worth a fresh eval.

## 2026-05-05 v22 Literal Format Repair Seed

The v22 repair seed was added after the v20 negative diagnostic result, without
using the fresh v21 eval surface:

- seed: `data/main_agent_v22_literal_format_repair_seed_20260505.jsonl`
- records: 30
- categories: literal one-line terms, exact key/value copy, exact two-bullet
  copy, safe-token literal actions, numbered phrase/length constraints, and
  compact JSON literals
- verifier records: 30/30
- source: `codex_v20_negative_result_analysis`
- split: `train_seed`
- evidence level: `train_seed_not_capability_evidence`
- clean capability claim eligible: false

This is repair/dev material only. It teaches normal candidate-quality behavior:
copy named terms exactly, keep key/value and bullet shapes stable, and avoid
paraphrasing short defensive cleanup phrases. It does not train final authority,
tool/action authority, refusal authority, or audit authority.

NVIDIA teacher pass:

- teacher model: `qwen/qwen3-next-80b-a3b-instruct`
- accepted samples: 25/30
- accepted categories: literal one-line 5, key/value 4, two-bullet 4,
  safe-token actions 4, numbered phrase limit 3, JSON literal 5
- best+teacher SFT rows: 39, including 9 teacher alternate rows

The v22 adapter was trained from v19, deliberately not from the v20 negative
adapter:

- input: `runs/main-agent-v16-v17-v19-v22-repair-sft-20260505.jsonl`
- rows: 127
- resume: `runs/qwen3-8b-main-agent-v19-v18-failure-repair-lora-20260505`
- output: `runs/qwen3-8b-main-agent-v22-literal-format-repair-lora-20260505`
- optimizer steps: 32
- micro steps: 128
- duration: about 804 seconds on the RTX 4060 Laptop GPU

Measured no-thinking evals:

| Run | Surface | Clean |
|---|---:|---:|
| v22 adapter | v22 train surface | 28/30 |
| v22 adapter | spent v18 clean capability eval | 22/25 |
| v22 adapter | adapter containment seed | 2/12 candidate-clean, 12/12 contained |

Comparison against v19 on the same spent v18 eval:

- clean delta: -1
- fixed: `v18-clean-planning-003`, `v18-clean-safe-002`
- regressed: `v18-clean-format-005`, `v18-clean-planning-001`,
  `v18-clean-safe-004`
- persistent failures: none

Fresh eval gate result:

```text
verdict: hold
reason: clean_delta -1 and regressed_cases=3
containment: 12/12 contained, containment_issue_counts {}
train surface: 28/30 clean
```

Conclusion: v22 is a better-shaped train/dev repair than v20 because it learns
most of its own surface, but it does not beat v19 on the spent v18 comparison.
Do not promote v22 and do not spend the fresh v21 eval surface on it.

## Repository Boundary

Keep this work as a Main Agent optimization branch of evidence. It belongs
under data, verifier, and experiment documentation. It should not redefine the
repository as a fine-tuning project.

Before any adapter is promoted, require:

1. A new clean evaluation surface that did not drive the data round.
2. A same-run comparison against the fixed-weight architecture profiles.
3. Checks that audit separation, fail-closed behavior, and refusal authority
   remain outside the Main Agent.
4. A public benchmark or external sanity pass if making claims beyond local
   synthetic rows.
