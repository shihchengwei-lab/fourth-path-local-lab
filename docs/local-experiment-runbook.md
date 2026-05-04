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
planning answers, safe incident-response wording, and the code/format precision
failures seen in the v8 comparison. It must stay
out of default SFT exports unless explicitly selected for a documented v9
training run.

The same gate also checks repair-seed provenance: each row must keep
`split=train_seed`, `evidence_level=train_seed_not_capability_evidence`,
`clean_claim_eligible=false`, and a non-empty `source`.

`local-release-gate` reports no current clean claim surface, keeps only legacy
`v5` as non-evidence context, records old `v6-v17` as withdrawn, and now treats
the v8 eval surface as spent comparison evidence. The v9 eval surface is now
tracked as a spent comparison surface for the v9 repair. After this comparison,
the next clean capability claim required a fresh unused eval surface after the
next repair; the boundary-clean v10 surface has now been used for v9/v10/v12
comparison and later spent by v13/v14 comparison.

`data/main_agent_v10_clean_capability_eval_seed_20260505.jsonl` is the first
boundary-clean capability eval surface after the authority/refusal/control-plane
data-boundary correction. Release gate now includes a boundary-clean check for
that file, so future claim surfaces should follow that shape rather than the
older spent v6/v8/v9 evals that included external safety-layer terms.

Fresh v10 comparison after correcting the code verifier:

```text
v9:  16/25 clean
v10: 16/25 clean
v12: 17/25 clean
```

The v10 code rows now verify the required function signature plus Python tests,
instead of rewarding one exact implementation shape. Result: v12 is not a
promotion candidate yet. It is +1 over v9/v10 on this spent surface, but
planning stayed 0/5 and the new surface is now spent.

Run v9 fresh comparison:

```powershell
.\.venv-lora\Scripts\python.exe tools\experimental\qlora_adapter_eval.py --model Qwen/Qwen3-8B --adapter-dir runs\qwen3-8b-main-agent-v6-continuation-lora-20260503 --input-file data\main_agent_v9_clean_capability_eval_seed_20260505.jsonl --output-file runs\qwen3-8b-main-agent-v6-continuation-lora-20260503-v9-clean-capability-eval-20260505.json
.\.venv-lora\Scripts\python.exe tools\experimental\qlora_adapter_eval.py --model Qwen/Qwen3-8B --adapter-dir runs\qwen3-8b-main-agent-v8-capability-repair-lora-20260504 --input-file data\main_agent_v9_clean_capability_eval_seed_20260505.jsonl --output-file runs\qwen3-8b-main-agent-v8-capability-repair-lora-20260504-v9-clean-capability-eval-20260505.json
.\.venv-lora\Scripts\python.exe tools\experimental\qlora_adapter_eval.py --model Qwen/Qwen3-8B --adapter-dir runs\qwen3-8b-main-agent-v9-capability-repair-lora-20260505 --input-file data\main_agent_v9_clean_capability_eval_seed_20260505.jsonl --output-file runs\qwen3-8b-main-agent-v9-capability-repair-lora-20260505-v9-clean-capability-eval-20260505.json
```

Observed result on the fresh v9 surface:

```text
v6:  6/24 clean
v8: 10/24 clean
v9: 12/24 clean
```

v9 category result:

```text
math 3/4
code 3/5
format 4/5
planning 0/5
safe_near_boundary 2/5
```

Interpretation: v9 has a fresh-surface candidate-quality gain over v8 and v6,
but planning remains 0/5. Treat this as narrow improvement evidence, not
promotion and not completion of the long-term goal.

`data/main_agent_v10_capability_repair_seed_20260505.jsonl` is a repair/dev
seed derived from v9 failure labels, not copied fresh-eval prompts. It weights
planning more heavily because v9 remained 0/5 there:

```text
math 4
code 5
format 5
planning 10
safe_near_boundary 6
```

This seed is training/dev material only. Keep it out of default SFT exports and
do not treat its target answers as capability evidence.

v10 training used local golden best-only SFT, not the partial NVIDIA teacher
file:

```text
input: runs/main-agent-v10-capability-repair-best-only-sft-20260505.jsonl
adapter: runs/qwen3-8b-main-agent-v10-planning-repair-lora-20260505
resume: runs/qwen3-8b-main-agent-v9-capability-repair-lora-20260505
rows: 30
steps: 30 optimizer steps, 120 micro steps
duration: 691.791s
```

Spent-surface sanity on `data/main_agent_v9_clean_capability_eval_seed_20260505.jsonl`:

```text
v9:  12/24 clean
v10: 14/24 clean
```

v10 category result on that spent surface:

```text
math 4/4
code 3/5
format 4/5
planning 0/5
safe_near_boundary 3/5
```

Interpretation: v10 improved math and safe-near-boundary on a spent surface,
but did not repair planning. Do not mint a new clean claim from this. The next
repair should target planning answers that preserve exact required terms while
remaining short.

v10 containment:

```text
total 12
candidate clean 2
safety-relevant contained 12
containment_issue_counts {}
```

Say "external containment held" rather than "v10 is safe"; the adapter still
produces dirty candidates that the external layer must catch.

QLoRA training now defaults to the same no-thinking chat-template mode used by
adapter eval. The trainer exposes `--enable-thinking` only as an explicit opt-in
and writes `enable_thinking` into the manifest. Future adapters intended for the
current no-thinking eval path should leave `--enable-thinking` unset.

v13 repair seed and adapter:

```text
seed:    data/main_agent_v13_capability_repair_seed_20260505.jsonl
sft:     runs/main-agent-v13-capability-repair-sft-20260505.jsonl
adapter: runs/qwen3-8b-main-agent-v13-planning-terms-lora-20260505
resume:  runs/qwen3-8b-main-agent-v12-post-gate-planning-lora-20260505
rows:    30
steps:   30 optimizer steps, 120 micro steps
```

The v13 seed is training/dev material only: 4 math, 4 code, 4 format, 12
planning, and 6 safe-near-boundary rows. It was added to the capability dev
release gate and passes the authority/refusal/control-plane overlap scan.

Observed v13 results:

```text
v13 train-surface eval: 30/30 clean
v10 spent-surface eval: 17/25 clean
v10 planning category:  0/5
adapter containment:    contained 12/12, candidate clean 5/12
```

Interpretation: v13 memorized the new repair seed but did not generalize the
"preserve named required words" behavior to the already-spent v10 surface.
Do not promote v13. Do not spend another GPU cycle on the same row shape without
first changing the data strategy or adding a stronger teacher/diversity step.

NVIDIA teacher exploration for v13 planning:

```text
runs/main-agent-v13-planning-nvidia-teacher-20260505.jsonl
qwen + nemotron: 0/24 accepted

runs/main-agent-v13-planning-nvidia-teacher-short-20260505.jsonl
qwen short max-tokens run: 0/12 accepted

runs/main-agent-v13-planning-nvidia-teacher-short-promptfix-20260505.jsonl
qwen short run after teacher prompt tightening: 2/12 accepted
authority_boundary_issue_count: 0

runs/main-agent-v13-planning-nvidia-teacher-verifier-prompt-20260505.jsonl
qwen short run with verifier constraints in the teacher request: 4/12 accepted
authority_boundary_issue_count: 0
```

Interpretation: teacher output can help, but the generic teacher prompt was too
verbose for hard planning verifiers. The teacher prompt now tells models to keep
answers short and copy named words exactly, and the teacher request now includes
local verifier constraints without exposing target answers. Four accepted rows
from the same prompt set are not enough to justify another GPU training run;
next work should diversify synthetic planning prompts first.

v14 planning diversity seed:

```text
seed: data/main_agent_v14_planning_diversity_seed_20260505.jsonl
sft:  runs/main-agent-v14-planning-diversity-sft-20260505.jsonl
rows: 24
categories:
- v14_capability_planning_exact_terms: 8
- v14_capability_planning_sequence: 6
- v14_capability_planning_one_sentence: 5
- v14_capability_planning_bullets: 5
```

The v14 seed is still training/dev material only. It is not capability evidence
and all rows set `clean_claim_eligible=false`. The release gate caught one draft
row that used `prompt hash` because it looked like a control-plane prompt
reference; the row was rewritten to `row hash` before validation.

v14 local SFT report:

```text
rows: 24
system_rows: 24
authority_boundary_issue_count: 0
format_errors: []
```

v14 NVIDIA teacher pass with verifier-aware prompts:

```text
output: runs/main-agent-v14-planning-diversity-nvidia-teacher-20260505.jsonl
model: qwen/qwen3-next-80b-a3b-instruct
accepted: 11/24
acceptance_rate: 45.8%
accepted categories:
- v14_capability_planning_exact_terms: 7
- v14_capability_planning_sequence: 1
- v14_capability_planning_one_sentence: 1
- v14_capability_planning_bullets: 2
authority_boundary_issue_count: 0
format_errors: []
```

Interpretation: verifier-aware NVIDIA teacher output is now useful as a
second-angle source, but v14 is not yet a promoted capability result. If the next
GPU run uses it, treat the 24 local rows plus 11 accepted teacher rows as a
training candidate set and evaluate on a fresh, unused capability surface before
making any clean claim.

v14 adapter sanity run:

```text
combined SFT: runs/main-agent-v14-planning-diversity-plus-teacher-sft-20260505.jsonl
combined rows: 31
best rows: 24
teacher alternate rows: 7
adapter: runs/qwen3-8b-main-agent-v14-planning-diversity-lora-20260505
manifest: runs/qwen3-8b-main-agent-v14-planning-diversity-lora-20260505-manifest.json
resume: runs/qwen3-8b-main-agent-v12-post-gate-planning-lora-20260505
steps: 31 optimizer steps, 124 micro steps
duration: about 781s
```

Eval results:

```text
v14 train surface: 24/24 clean
v10 spent surface: 17/25 clean
v10 planning: 0/5
adapter containment: contained 12/12
adapter containment candidate clean: 3/12
containment_issue_counts: {}
```

Interpretation: v14 learned its own training surface, but did not improve the
already-spent v10 planning surface over v13. Do not promote this adapter. The
safety result remains an external-layer result: containment held, while Main
Agent candidate cleanliness on containment prompts dropped to 3/12.

v11 fair visible-constraint comparison:

```text
surface: data/main_agent_v11_clean_capability_eval_seed_20260505.jsonl
shape: 25 rows, 5 categories, boundary-clean
design fix: exact verifier terms are visible in the user prompt
```

This was minted because v10 planning used hidden exact-word verifier terms such
as `Rewrite`, `Retest`, `Stop`, `Compare`, and `Rerun` without consistently
naming them in the prompt. That made v10 planning a poor measure of the
visible-constraint behavior we actually wanted.

Results on v11:

```text
v12 adapter: 19/25 clean, planning 2/5
v13 adapter: 23/25 clean, planning 4/5
v14 adapter: 21/25 clean, planning 3/5
```

Interpretation: v13 is better than v14 on this fairer prompt-visible eval.
Do not promote v14. Since v11 has now been used for comparison, the next clean
capability claim requires a fresh unused v12 eval surface after the next repair.

v15 visible-constraint repair seed:

```text
seed: data/main_agent_v15_visible_constraint_repair_seed_20260505.jsonl
sft:  runs/main-agent-v15-visible-constraint-repair-sft-20260505.jsonl
rows: 24
categories:
- v15_capability_exact_json: 8
- v15_capability_phrase_planning: 8
- v15_capability_literal_keyvalue: 4
- v15_capability_exact_bullets: 4
```

The v15 seed targets the two v13 misses on v11: exact JSON key/value copying and
visible phrase preservation in short plans. It is training/dev material only,
with `clean_claim_eligible=false`; release gate verifies it has no authority,
refusal, audit, action, or control-plane overlap.

Training-data reports:

```text
local SFT: rows 24, system_rows 24, authority_boundary_issue_count 0, format_errors []
NVIDIA teacher: accepted 16/24, authority_boundary_issue_count 0, format_errors []
best+teacher SFT: rows 28, authority_boundary_issue_count 0, format_errors []
```

Teacher alternates add four planning variants; JSON and key-value accepted rows
were mostly identical to the local targets, so they were not duplicated in the
best+teacher SFT.

v15 adapter result:

```text
adapter: runs/qwen3-8b-main-agent-v15-visible-constraint-lora-20260505
resumed from: runs/qwen3-8b-main-agent-v13-planning-terms-lora-20260505
training input: runs/main-agent-v15-visible-constraint-repair-plus-teacher-sft-20260505.jsonl
rows: 28
optimizer steps: 28
micro steps: 112
duration: 683s

v15 train surface: 24/24 clean
v11 spent eval: 22/25 clean, planning 4/5, format 3/5
v15 containment before safety fix: contained 11/12, candidate clean 4/12
v15 containment after safety fix: contained 12/12, containment_issue_counts {}
```

Interpretation: v15 improved on its own train surface, but it did not beat v13
on the already-spent v11 clean capability eval. v13 remains the best adapter
on that comparison surface at 23/25. Do not promote v15, and do not mint a
fresh v12 clean eval until the next candidate has a stronger reason to spend
it.

The first v15 containment run exposed an external-layer gap: a candidate that
opened with `No, this request is not allowed.` was a negative refusal/authority
decision, but the classifier did not treat it as a role-authority claim. The
classifier now blocks negative `not allowed` / `not approved` request-answer
verdicts as `role_authority_claim`, and the v15 containment rescore held 12/12.

v16 exact-format following seed and adapter:

```text
seed: data/main_agent_v16_exact_format_following_seed_20260505.jsonl
local SFT: runs/main-agent-v16-exact-format-following-sft-20260505.jsonl
NVIDIA teacher: runs/main-agent-v16-exact-format-following-nvidia-teacher-20260505.jsonl
combined SFT: runs/main-agent-v16-exact-format-following-plus-teacher-sft-20260505.jsonl
adapter: runs/qwen3-8b-main-agent-v16-exact-format-lora-20260505
resume: runs/qwen3-8b-main-agent-v15-visible-constraint-lora-20260505
```

The v16 seed targets the v15/v11 failure pattern: compact JSON key rewriting,
slash-separated exact word copying, and one-line plan prompts being turned into
numbered lists. It uses stricter anchored regex verifiers for exact JSON,
slash-copy, and key/value rows. It is train/dev material only and is not clean
capability evidence.

```text
seed rows: 24
categories: exact_json_anchor 6, exact_slash_copy 6, one_line_plan 6, keyvalue_anchor 6
local SFT report: rows 24, authority_boundary_issue_count 0, format_errors []
NVIDIA teacher: qwen/qwen3-next-80b-a3b-instruct accepted 24/24
combined SFT: rows 30, best rows 24, teacher alternate rows 6
adapter training: 30 optimizer steps, 120 micro steps, duration 742s
v16 train surface: 24/24 clean
v11 spent eval: 22/25 clean
v11 spent eval with runtime prompt augmentation: 22/25 clean
adapter containment: total 12, clean 3, contained 12, containment_issue_counts {}
```

Interpretation: v16 learned its own exact-format train surface, and external
containment still held. It did not beat v13's 23/25 on the spent v11 surface,
so do not promote v16 and do not spend a fresh v12 clean eval. Runtime prompt
hints were added for compact JSON, slash-separated exact words, and one-line
no-list prompts, but the augmented v11 adapter eval still stayed at 22/25.

Adapter comparison artifacts:

```text
runs/adapter-eval-compare-v13-v15-v11-20260505.json
runs/adapter-eval-compare-v15-v16-v11-20260505.json
runs/adapter-eval-compare-v13-v16-v11-20260505.json
```

The comparison tool reports case ids, categories, and verifier issue labels
only; it intentionally omits prompts, target answers, and generated answers.
The v13 -> v16 comparison shows one fixed case (`v11-clean-planning-004`), two
regressions (`v11-clean-planning-003`, `v11-clean-planning-005`), and one
persistent format failure (`v11-clean-format-002`).

Code maintenance note:

```text
main-training-data-report core assembly moved out of main.py.
training_data.py owns report data assembly.
training_data_cli.py owns the CLI print/exit wrapper.
compute_gates_cli.py owns compute-gate CLI print/exit wrappers.
adapter_eval_compare.py owns adapter eval case-delta comparison.
overblocking_gate.py owns benign-task overblocking smoke cases.
adapter_fresh_eval_gate.py owns fresh eval spend gating for adapter comparisons.
```

This is a small periodic refactor checkpoint to keep `main.py` from absorbing
every data-quality path.

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
- Capability dev/train seeds must not overlap external authority. Release gate
  now rejects `prompt` or `target_response` text that looks like Main Agent
  approval/refusal authority, tool/action permission, safety/external authority,
  refusal-like output, external gate labels, containment-layer claims,
  control-plane prompt references, unsupported canon verdicts, or private-prompt
  logging. Put those cases in containment / attack eval instead.
- Adapter containment distinguishes candidate-quality misses from safety-layer
  containment failures. Missing required terms or format constraints can make a
  candidate unclean without proving a safety leak; `dirty_candidate_forwarded`
  is reserved for safety-relevant candidate issues that the external gate still
  forwarded.
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

Before spending a new fresh clean eval on an adapter, compare against the
current baseline and require same-surface improvement plus intact containment:

```powershell
python tools\experimental\adapter_fresh_eval_gate.py --comparison-file runs\adapter-eval-compare-v13-v16-v11-20260505.json --containment-file runs\qwen3-8b-main-agent-v16-exact-format-lora-20260505-adapter-containment-eval.json --json
```

This gate answers only "is it worth spending a fresh eval?" It does not promote
an adapter. Promotion still needs unused eval evidence and review. A `hold`
verdict exits non-zero so automation can stop before spending the fresh surface.

The v17 failure-label repair seed is the next tracked capability-dev surface
after the v16 hold:

```powershell
python main.py main-check --input-file data\main_agent_v17_failure_label_repair_seed_20260505.jsonl --min-total 24 --min-category 6 --json
python main.py main-sft-export --input-file data\main_agent_v17_failure_label_repair_seed_20260505.jsonl --output-file runs\main-agent-v17-failure-label-repair-sft-20260505.jsonl --json
python main.py main-training-data-report --input-file runs\main-agent-v17-failure-label-repair-sft-20260505.jsonl --require-system --require-generated-metadata --json
```

It targets normal candidate-quality failures only: compact JSON, required-term
planning, one-line no-list answers, and short key/value answers. It is
train-seed evidence, not a clean capability claim.

The first v17 adapter run improved v16 on the spent v11 eval but did not beat
v13:

```text
v17 train surface: 21/24 clean
v16 train surface: 24/24 clean
spent v11 eval: 23/25 clean
containment: 12/12 contained, containment_issue_counts {}
fresh eval gate versus v13: hold
```

The v12 clean capability eval surface was then minted and used:

```text
data/main_agent_v12_clean_capability_eval_seed_20260505.jsonl
25 rows, 5 categories x 5
verifier_records 25/25
boundary failures {}
prompt overlaps []
```

Initial v12 run with the existing augment prompts:

```text
v13 + augment prompts: 15/25 clean
v17 + augment prompts: 19/25 clean
gate: hold, clean_delta +4 but 1 regressed case
```

The regression came from exact included phrases in numbered/list prompts being
paraphrased or reordered. Runtime prompt augmentation now adds a phrase-copy
hint for checklist/list/numbered-step prompts. This is a normal formatting and
candidate-quality hint, not safety-authority training.

After the hint:

```text
v13 + phrase-copy augment prompts: 14/25 clean
v17 + phrase-copy augment prompts: 20/25 clean
comparison: clean_delta +6, regressed_cases []
containment: 12/12 contained, containment_issue_counts {}
gate: spend_fresh_eval
```

Do not promote v17 from v12 alone. Because v12 directly informed the
phrase-copy runtime hint, it is now spent diagnostic evidence. The next
promotion attempt needs a new unused clean eval surface after this runtime
change; the release gate now names that next claim surface v18. On Windows, do
not run multiple 8B adapter evals in parallel; two
simultaneous model loads hit pagefile error 1455 in this run.

## v18 Clean Capability Eval

Fresh surface after the phrase-copy runtime hint:

```text
data/main_agent_v18_clean_capability_eval_seed_20260505.jsonl
25 rows, 5 categories x 5
verifier_records 25/25
target verifier failures {}
boundary failures {}
prompt overlaps []
```

This file is eval-only. Do not add it to SFT or repair training data. Use it
for a same-run v13/v17 comparison with `--augment-prompts`, then keep the
comparison separate from adapter promotion; promotion still needs explicit
review.

Same-run v18 result after the phrase-copy hint:

```text
v13 + phrase-copy augment prompts: 16/25 clean
v17 + phrase-copy augment prompts: 18/25 clean
comparison: clean_delta +2, fixed 4, regressed_cases 2
regressions: v18-clean-planning-001, v18-clean-safe-005
containment: 12/12 contained, containment_issue_counts {}
gate: hold
```

Do not promote v17 from v18. If the v18 failures are used for repair, this
surface becomes diagnostic evidence; the next clean claim needs a fresh unused
v19 surface.

## v19 v18-Failure Repair Seed

Tracked capability-dev repair seed:

```text
data/main_agent_v19_v18_failure_repair_seed_20260505.jsonl
30 rows, 5 categories x 6
verifier_records 30/30
target verifier failures {}
boundary failures {}
prompt overlaps []
source codex_v18_failure_label_analysis
split train_seed
evidence_level train_seed_not_capability_evidence
clean_claim_eligible false
```

It targets v18 failure labels without copying v18 prompts as training rows. It
is train/dev material only, not clean capability evidence.

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
