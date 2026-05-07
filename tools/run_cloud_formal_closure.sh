#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${REPO_DIR:-/root/fourth-path-local-lab}"
BENCH_PY="${BENCH_PY:-/root/.venvs/fourth-path-bench/bin/python}"
MODEL_PY="${MODEL_PY:-/root/.venvs/fourth-path-lora/bin/python}"
HF_MODEL="${HF_MODEL:-Qwen/Qwen3-8B}"
ADAPTER_DIR="${ADAPTER_DIR:-runs/qwen3-8b-main-agent-v19-v18-failure-repair-lora-20260505}"
PROFILE="${PROFILE:-qwen3-8b-local-max}"
TASKS="${TASKS:-ifeval,gsm8k}"
PORT="${PORT:-8010}"
RUN_ID="${RUN_ID:-closure-formal-$(date -u +%Y%m%d-%H%M%S)}"
OUT_ROOT="${OUT_ROOT:-runs/closure-bench-cloud/${RUN_ID}}"
LOG_ROOT="${LOG_ROOT:-runs/cloud-logs/${RUN_ID}}"
AUDIT_ROOT="${AUDIT_ROOT:-runs/closure-bench-audit-cloud/${RUN_ID}}"
DEFAULT_MAX_NEW_TOKENS="${DEFAULT_MAX_NEW_TOKENS:-2048}"
HF_HOME="${HF_HOME:-/root/hf-cache}"
export HF_HOME
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1

cd "$REPO_DIR"
mkdir -p "$OUT_ROOT" "$LOG_ROOT" "$AUDIT_ROOT"

server_pid=""

stop_server() {
  if [[ -n "${server_pid:-}" ]]; then
    if kill -0 "$server_pid" 2>/dev/null; then
      kill "$server_pid" 2>/dev/null || true
      wait "$server_pid" 2>/dev/null || true
    fi
    server_pid=""
  fi
}

on_exit() {
  stop_server
}
trap on_exit EXIT

json_escape() {
  "$BENCH_PY" -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}

write_manifest() {
  {
    echo "run_id=$RUN_ID"
    echo "started_utc=$(date -u --iso-8601=seconds)"
    echo "repo_dir=$REPO_DIR"
    echo "hf_model=$HF_MODEL"
    echo "adapter_dir=$ADAPTER_DIR"
    echo "profile=$PROFILE"
    echo "tasks=$TASKS"
    echo "precision=bf16_or_fp16_no_4bit"
    echo "default_max_new_tokens=$DEFAULT_MAX_NEW_TOKENS"
    echo "out_root=$OUT_ROOT"
    echo "log_root=$LOG_ROOT"
    echo "audit_root=$AUDIT_ROOT"
    echo
    echo "[uname]"
    uname -a || true
    echo
    echo "[nvidia-smi]"
    nvidia-smi || true
    echo
    echo "[python]"
    "$BENCH_PY" --version || true
    "$MODEL_PY" --version || true
    echo
    echo "[packages]"
    "$MODEL_PY" - <<'PY' || true
import importlib
for name in ["torch", "transformers", "peft", "bitsandbytes", "numpy"]:
    module = importlib.import_module(name)
    print(f"{name}={getattr(module, '__version__', 'unknown')}")
PY
  } > "$LOG_ROOT/manifest.txt"
}

wait_health() {
  local deadline=$((SECONDS + 900))
  until curl -fsS "http://127.0.0.1:${PORT}/health" > "$LOG_ROOT/${case_name}.health.json"; do
    if (( SECONDS > deadline )); then
      echo "health timeout for ${case_name}" | tee -a "$LOG_ROOT/${case_name}.driver.log"
      return 1
    fi
    sleep 5
  done
}

run_case() {
  case_name="$1"
  mode="$2"
  alias="$3"
  use_adapter="$4"

  local started completed server_log out_dir adapter_args
  started="$(date -u --iso-8601=seconds)"
  server_log="$LOG_ROOT/${case_name}.server.log"
  out_dir="$OUT_ROOT/${case_name}"
  adapter_args=()
  if [[ "$use_adapter" == "yes" ]]; then
    adapter_args=(--adapter-dir "$ADAPTER_DIR")
  fi

  {
    echo "case=$case_name"
    echo "mode=$mode"
    echo "alias=$alias"
    echo "use_adapter=$use_adapter"
    echo "started_utc=$started"
    echo "out_dir=$out_dir"
    echo "server_log=$server_log"
    echo "command_server=$MODEL_PY tools/adapter_public_bench_server.py --model $HF_MODEL ${adapter_args[*]} --profile $PROFILE --mode $mode --port $PORT --model-alias $alias --runs-dir $AUDIT_ROOT/$case_name --default-max-new-tokens $DEFAULT_MAX_NEW_TOKENS --no-4bit"
  } | tee "$LOG_ROOT/${case_name}.driver.log"

  "$MODEL_PY" tools/adapter_public_bench_server.py \
    --model "$HF_MODEL" \
    "${adapter_args[@]}" \
    --profile "$PROFILE" \
    --mode "$mode" \
    --port "$PORT" \
    --model-alias "$alias" \
    --runs-dir "$AUDIT_ROOT/$case_name" \
    --default-max-new-tokens "$DEFAULT_MAX_NEW_TOKENS" \
    --no-4bit \
    > "$server_log" 2>&1 &
  server_pid=$!
  echo "server_pid=$server_pid" | tee -a "$LOG_ROOT/${case_name}.driver.log"

  wait_health
  echo "health_ok_utc=$(date -u --iso-8601=seconds)" | tee -a "$LOG_ROOT/${case_name}.driver.log"
  cat "$LOG_ROOT/${case_name}.health.json" | tee -a "$LOG_ROOT/${case_name}.driver.log"
  echo | tee -a "$LOG_ROOT/${case_name}.driver.log"

  "$BENCH_PY" -m lm_eval run \
    --model local-chat-completions \
    --model_args "model=${alias},base_url=http://127.0.0.1:${PORT}/v1/chat/completions,num_concurrent=1,max_retries=3,tokenized_requests=False" \
    --tasks "$TASKS" \
    --apply_chat_template \
    --output_path "$out_dir" \
    --log_samples \
    2>&1 | tee -a "$LOG_ROOT/${case_name}.driver.log"

  completed="$(date -u --iso-8601=seconds)"
  echo "completed_utc=$completed" | tee -a "$LOG_ROOT/${case_name}.driver.log"
  find "$out_dir" -maxdepth 3 -type f | sort | tee "$LOG_ROOT/${case_name}.artifacts.txt"

  tar -czf "$LOG_ROOT/${case_name}.artifacts.tgz" "$out_dir" "$LOG_ROOT/${case_name}.driver.log" "$server_log" "$AUDIT_ROOT/$case_name" 2>/dev/null || true
  stop_server
  nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader | tee -a "$LOG_ROOT/${case_name}.driver.log" || true
}

write_manifest

run_case "R0-C0-raw-b8" "raw" "R0-C0-raw-b8" "no"
run_case "M0-main-only-b8" "main" "M0-main-only-b8" "no"
run_case "S0-split-b8" "pipeline" "S0-split-b8" "no"
run_case "M1-main-only-adapter" "main" "M1-main-only-adapter" "yes"
run_case "S1-split-adapter" "pipeline" "S1-split-adapter" "yes"

echo "all_completed_utc=$(date -u --iso-8601=seconds)" | tee -a "$LOG_ROOT/manifest.txt"
