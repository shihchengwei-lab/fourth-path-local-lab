# Cloud Closure Benchmark Runbook

This runbook moves the formal closure benchmark off the local RTX 4060 Laptop
8 GB machine. Do not use the local laptop for no-cap or full adapter closure
runs.

## Objective

Run the closure matrix on a cloud GPU and produce a report that separates:

- candidate capability,
- user-visible product-path capability,
- architecture tax,
- adapter gain,
- safety-layer containment evidence.

The final matrix is:

| Case | Meaning |
| --- | --- |
| R0/C0 raw B8 | Direct raw B8 baseline and operational coupled-safety baseline. |
| M0 main-only B8 | Observed candidate-only route capability over direct raw B8. |
| S0 split B8 | User-visible capability and safety after reconnecting the external architecture. |
| M1 main-only adapter | Adapter-backed candidate capability. |
| S1 split adapter | Adapter-backed product path with the external architecture reconnected. |

The report answers:

| Delta | Question |
| --- | --- |
| M0 - R0/C0 | Observed gain of the candidate-only route over direct raw B8, including prompt-shape and runtime-wrapper effects. |
| S0 - R0/C0 | Net user-visible gain after reconnecting the split safety architecture. |
| M0 - S0 | Architecture tax. |
| M1 - M0 | Adapter candidate gain. |
| S1 - S0 | Adapter product-path net gain. |
| S0/S1 safety | Whether the external safety layer holds. |

## Cloud Machine

Minimum practical target:

- 1 GPU with at least 40 GB VRAM: A100 40 GB or better.
- 64 GB system RAM minimum; 128 GB preferred.
- 200 GB local SSD minimum; 300 GB preferred if keeping full samples and HF
  cache.
- Ubuntu 22.04 or 24.04.
- CUDA-capable PyTorch environment.

Recommended target:

- 1x H100 80 GB or A100 80 GB for the formal full run.
- 2x GPUs only if running cases in parallel with isolated ports and separate
  output directories. Sequential single-GPU runs are easier to audit.

Avoid for the formal run:

- 8 GB laptop GPUs.
- 24 GB GPUs for no-cap adapter full runs unless a smoke run proves stable
  throughput and memory headroom.
- Spot/preemptible instances unless output syncing is automated after each case.

## Cost Envelope

Prices change. Check the cloud console before launch and record the observed
price in the benchmark report.

Current public reference points checked on 2026-05-06:

- Lambda lists 1x A100 40 GB at about USD 1.99/GPU-hour, 1x H100 PCIe 80 GB at
  about USD 3.29/GPU-hour, and 1x H100 SXM 80 GB at about USD 4.29/GPU-hour:
  https://lambda.ai/pricing
- RunPod documentation says Pods are billed by the second, no data ingress or
  egress fees are charged for Pods, and latest GPU pricing should be checked in
  the deployment console:
  https://docs.runpod.io/pods/pricing

Planning budget for one formal matrix:

| GPU | Planning time | Cost envelope before tax/storage |
| --- | ---: | ---: |
| A100 40 GB | 12-24 GPU-hours | about USD 24-48 at USD 1.99/hr |
| H100 PCIe 80 GB | 8-16 GPU-hours | about USD 26-53 at USD 3.29/hr |
| H100 SXM 80 GB | 6-14 GPU-hours | about USD 26-60 at USD 4.29/hr |

Add setup/debug budget:

- first cloud setup: 1-3 extra GPU-hours,
- first main-only and adapter smoke: 1-2 extra GPU-hours,
- rerun reserve: 25-50% of the formal-run budget.

## Local Results To Carry As Appendix

Completed local diagnostics:

| Local run | Status | Result path | Use |
| --- | --- | --- | --- |
| A0 raw B8 | full complete | `runs/closure-bench/A0-raw-b8-20260505-194336/qwen3__8b/results_2026-05-06T01-43-06.877264.json` | R0/C0 local appendix. |
| A1 split B8 | full complete | `runs/closure-bench/A1-split-b8-20260506-014323/A1-split-b8/results_2026-05-06T04-51-09.721315.json` | S0 local appendix. |
| A2 raw adapter bounded16 | full bounded complete | `runs/closure-bench/A2-raw-b8-adapter-20260506-052436/A2-raw-b8-adapter/results_2026-05-06T08-07-11.899807.json` | Raw/direct adapter mismatch diagnostic only. |
| A3 split adapter bounded16 | full bounded complete | `runs/closure-bench/A3-split-b8-adapter-20260506-080714/A3-split-b8-adapter/results_2026-05-06T17-17-16.177740.json` | Bounded S1-like appendix only. |
| A4 main-only B8 | `--limit 1` smoke complete | `runs/closure-bench/A4-main-only-b8-20260506-171758/A4-main-only-b8/results_2026-05-06T17-21-09.722241.json` | M0 path validation only. |
| A5 main-only adapter | `--limit 1` smoke complete, no cap | `runs/closure-bench/A5-main-only-b8-adapter-20260506-172117/A5-main-only-b8-adapter/results_2026-05-06T17-46-39.794745.json` | M1 path validation only. |

Stopped local work:

```text
runs/closure-bench/closure-bench-A4-20260506-174726-ifeval-gsm8k-full.stderr.log
```

That A4 full local run was stopped at 438/1860 requests and has no aggregate
result. Do not use it as a score.

## Setup

Use Linux paths on cloud. The current PowerShell runner can still be used from
PowerShell Core if explicit Linux Python paths are passed.

```bash
sudo apt-get update
sudo apt-get install -y git git-lfs curl jq rsync python3-venv python3-pip

# Install PowerShell Core if the image does not include pwsh.
# Use the provider image docs for the exact package source on Ubuntu.
```

Clone and create environments:

```bash
git clone <repo-url> fourth-path-local-lab
cd fourth-path-local-lab

python3 -m venv .venv-bench
./.venv-bench/bin/python -m pip install -U pip
./.venv-bench/bin/python -m pip install "lm-eval[api,ifeval]"

python3 -m venv .venv-lora
./.venv-lora/bin/python -m pip install -U pip
./.venv-lora/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/cu124
./.venv-lora/bin/python -m pip install transformers accelerate peft bitsandbytes sentencepiece protobuf
```

Sync the selected adapter:

```bash
rsync -av --progress user@local:/path/to/fourth-path-local-lab/runs/qwen3-8b-main-agent-v19-v18-failure-repair-lora-20260505/ \
  runs/qwen3-8b-main-agent-v19-v18-failure-repair-lora-20260505/
```

Record environment:

```bash
nvidia-smi | tee runs/cloud-nvidia-smi.txt
./.venv-bench/bin/python -m pip freeze | tee runs/cloud-bench-pip-freeze.txt
./.venv-lora/bin/python -m pip freeze | tee runs/cloud-lora-pip-freeze.txt
git rev-parse HEAD | tee runs/cloud-git-commit.txt
```

## Preflight

Run only smoke tests before spending full benchmark time:

```bash
./.venv-bench/bin/python main.py local-release-gate --json | tee runs/cloud-preflight-release-gate.json
./.venv-bench/bin/python -m unittest discover -s tests -v | tee runs/cloud-preflight-unittest.log

pwsh -NoProfile -ExecutionPolicy Bypass -File tools/run-closure-bench.ps1 \
  -Case A4 -Tasks ifeval,gsm8k -Limit 1 \
  -Python ./.venv-bench/bin/python \
  -AdapterPython ./.venv-lora/bin/python \
  -OutputRoot runs/closure-bench-cloud

pwsh -NoProfile -ExecutionPolicy Bypass -File tools/run-closure-bench.ps1 \
  -Case A5 -Tasks ifeval,gsm8k -Limit 1 \
  -Python ./.venv-bench/bin/python \
  -AdapterPython ./.venv-lora/bin/python \
  -OutputRoot runs/closure-bench-cloud
```

For A4/A5 smoke, scan `resps` and `filtered_resps` for forbidden pipeline
surface text before full runs:

```text
Cold Eyes
Action Gate
fixed refusal
refusal module
pipeline audit
audit verdict
canon_clause
```

## Formal Run Order

Do not use `-Case closure-plus-main` for the formal report because it includes
legacy diagnostic cases.

For the formal cloud run, use the single Linux runner so all cases share the
same backend, port, precision, task list, output cap policy, and lm-eval
settings:

```bash
RUN_ID="closure-formal-$(date -u +%Y%m%d-%H%M%S)" \
  nohup ./tools/run_cloud_formal_closure.sh \
  > "/root/${RUN_ID}.nohup.log" 2>&1 &
echo "$RUN_ID" > /root/formal_closure.run_id
```

The runner executes cases sequentially:

```text
R0-C0-raw-b8
M0-main-only-b8
S0-split-b8
M1-main-only-adapter
S1-split-adapter
```

Do not change concurrency, output cap, precision, task list, model path, or
adapter path mid-run. If a rerun is needed, record it as a separate run id.

R0/C0 is one operational run, not two. Use the direct raw B8 case for both the
base capability reference and the coupled-safety baseline. Do not add a special
in-band C0 safety prompt; that would measure prompt design instead of the
direct coupled baseline.

Actual per-case server commands are recorded in
`runs/cloud-logs/<run-id>/<case>.driver.log`. Use those driver logs, not the
runbook prose, as the authoritative command evidence for the final report.

## Safety Evidence For S0 And S1

Run safety-layer checks after the benchmark cases, and again after any wrapper
change:

```bash
./.venv-bench/bin/python main.py local-release-gate --json \
  | tee runs/cloud-post-release-gate.json

./.venv-bench/bin/python main.py architecture-adversarial-eval \
  --profile qwen3-8b-local-max \
  --input-file data/architecture_containment_pressure_seed.jsonl \
  --json --timeout 900 --min-pass-rate 1.0 \
  | tee runs/cloud-containment-pressure.json

./.venv-bench/bin/python main.py architecture-adversarial-eval \
  --profile qwen3-8b-local-max \
  --input-file data/architecture_strong_pressure_seed.jsonl \
  --json --timeout 900 --min-pass-rate 1.0 \
  | tee runs/cloud-strong-pressure.json
```

If S1 uses the HF adapter server instead of Ollama, document exactly how the S1
safety path is served before treating the safety evidence as S1 evidence.

## Output Sync

Sync outputs after every case, not only at the end:

```bash
tar -czf closure-bench-cloud-$(date +%Y%m%d-%H%M%S).tgz \
  runs/closure-bench-cloud \
  runs/closure-bench-audit \
  runs/public-bench-audit \
  runs/cloud-*.txt \
  runs/cloud-*.json \
  runs/cloud-*.log

rsync -av --progress runs/ user@local:/path/to/fourth-path-local-lab/runs-cloud-copy/
```

Keep raw samples and audit logs private unless a later review asks for sanitized
publication.

After syncing, generate a reproducible score table:

```bash
python tools/summarize_closure_run.py --run-id <run-id>
```

The summary script reads only `results_*.json`, per-task sample files, and
driver logs. It does not call the model.

## Stop Rules

Stop the cloud job and sync partial logs if:

- any no-cap adapter case exceeds the approved budget by 50%,
- GPU memory errors occur,
- a server returns pipeline/audit/refusal text in M0 or M1 response bodies,
- any formal command uses an unreported output cap.
