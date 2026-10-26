#!/usr/bin/env bash
# Run the five agent tasks against the configured OpenAI-compatible provider.
set -uo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PACK="$ROOT/agent-problem-pack"
CLI="${QWEN_CLI:-/home/mahesh/DAT/qwen-code-release/scripts/cli-entry.js}"
MODEL="${EVAL_MODEL:-Qwen3.6-27B}"
BASE_URL="${EVAL_BASE_URL:-http://127.0.0.1:9000/v1}"
RUN="qwen-$(date +%Y%m%d-%H%M%S)-$$"
REPORT="$ROOT/results/$RUN"

for command in node uv curl timeout python3 git; do
  command -v "$command" >/dev/null || { echo "Missing command: $command"; exit 1; }
done
[[ -f "$CLI" ]] || { echo "Qwen CLI not found: $CLI"; exit 1; }
echo "Checking model server: $BASE_URL"
if ! curl --fail --silent --show-error --max-time 20 \
  "$BASE_URL/models" >/dev/null; then
  echo "Model server unavailable. Start your SSH tunnel, then rerun this script."
  exit 1
fi

mkdir -p "$REPORT"
SUMMARY="$REPORT/summary.tsv"
printf 'TASK\tAGENT_EXIT\tTESTS\tFINAL_ANSWER\tARTIFACTS\n' > "$SUMMARY"
{
  printf 'run=%s\nmodel=%s\nendpoint=%s\ncli=%s\n' "$RUN" "$MODEL" "$BASE_URL" "$CLI"
  git -C "$ROOT" rev-parse HEAD
  node "$CLI" --version
} > "$REPORT/versions.txt" 2>&1

echo "Automatic tool approval is enabled for these task runs."
echo "Workspaces are separate directories, not security sandboxes."
echo "Results: $REPORT"

for PROBLEM in \
  problem-01-tokenizer-regression \
  problem-02-shell-command-injection \
  problem-03-cross-platform-task-path \
  problem-04-import-error-after-refactor \
  problem-05-mutable-default-cache
do
  printf '\n=== %s ===\n' "$PROBLEM"
  TASK="$PACK/runs/$PROBLEM/$RUN"
  if ! (cd "$PACK" && uv run python scripts/pack_tools.py prepare "$PROBLEM" "$RUN") \
    > "$REPORT/$PROBLEM-prepare.log" 2>&1; then
    printf '%s\t-\tPREPARE_ERROR\t-\t-\n' "$PROBLEM" >> "$SUMMARY"
    cat "$REPORT/$PROBLEM-prepare.log"
    continue
  fi

  (
    cd "$TASK/workspace" || exit 1
    timeout --kill-after=30s "${EVAL_TIMEOUT:-20m}" node "$CLI" \
      --model "$MODEL" --approval-mode yolo --output-format json \
      -p "$(cat "$TASK/artifacts/task-prompt.txt")"
  ) > "$TASK/artifacts/agent-output.json" 2> "$TASK/artifacts/agent-stderr.log"
  AGENT_EXIT=$?
  printf '%s\n' "$AGENT_EXIT" > "$TASK/artifacts/agent-exit-code.txt"

  (cd "$PACK" && timeout --kill-after=30s 10m uv run python scripts/pack_tools.py capture "$TASK") \
    > "$TASK/artifacts/capture.log" 2>&1
  CAPTURE_EXIT=$?

  RESULT=CAPTURE_ERROR
  if [[ -f "$TASK/artifacts/verification.txt" ]]; then
    if grep -qx 'exit_code=0' "$TASK/artifacts/verification.txt"; then
      RESULT=PASS
    else
      RESULT=FAIL
    fi
    cat "$TASK/artifacts/verification.txt"
  else
    echo "Capture failed (exit $CAPTURE_EXIT):"
    cat "$TASK/artifacts/capture.log"
  fi

  ANSWER=MISSING
  if [[ -s "$TASK/workspace/AGENT_FINAL_ANSWER.md" ]] && \
    ! grep -qx 'Write the final answer for this run here.' "$TASK/workspace/AGENT_FINAL_ANSWER.md"; then
    ANSWER=PRESENT
    printf '\nAgent explanation:\n'
    cat "$TASK/workspace/AGENT_FINAL_ANSWER.md"
  fi
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$PROBLEM" "$AGENT_EXIT" "$RESULT" "$ANSWER" "$TASK/artifacts" >> "$SUMMARY"
  if [[ "$AGENT_EXIT" != 0 ]]; then
    echo "Agent exit $AGENT_EXIT (124 = timeout); recent stderr:"
    tail -n 15 "$TASK/artifacts/agent-stderr.log"
  fi
done

python3 - "$SUMMARY" <<'PY'
import csv
import sys
from pathlib import Path

path = Path(sys.argv[1])
rows = list(csv.DictReader(path.open(), delimiter="\t"))
lines = ["TASK                                      AGENT_EXIT  TESTS          ANSWER"]
for row in rows:
    lines.append(f"{row['TASK']:<42}{row['AGENT_EXIT']:<12}{row['TESTS']:<15}{row['FINAL_ANSWER']}")
passed = sum(row["TESTS"] == "PASS" for row in rows)
lines += [f"\nTests passed: {passed}/{len(rows)}", "PASS refers to captured tests; review diffs for correctness and test changes.", "Token usage is not aggregated; raw agent JSON is saved per task."]
report = "\n".join(lines) + "\n"
path.with_suffix("txt").write_text(report)
print("\n" + report)
PY
echo "Summary: $REPORT/summary.txt"
echo "Full artifact paths: $SUMMARY"
