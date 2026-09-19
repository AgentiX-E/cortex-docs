#!/usr/bin/env bash
# Dispatch the MR operand-expansion A/B: 4 workflow runs per arm, INTERLEAVED
# so both arms are sampled at the same instant.
#
#   control   -> ref = mr-operand-expansion-control (a104ea0; derivation
#                      questions expand into ACTIVITIES, so the user's age "32"
#                      operand is never recalled)
#   treatment -> ref = master                      (a45b32a; derivation questions
#                      expand into OPERANDS, including "my age"/"my birthday")
#
# Parameters match the previous A/Bs: full 500-question dataset (limit=0),
# runs=1, temperature=0, diagnostics_limit=100.
#
# The primary endpoint is whether the "32" operand reaches the retrieved window
# for the two age-at-event questions (and their abstention), which is sampled,
# so four runs per arm bound the variance.
set -euo pipefail

cd /workspace/cortex
TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
export GH_TOKEN="$TOKEN"

WORKFLOW=benchmark.yml
REPEATS=4
ORDER_FILE=/workspace/analysis/ab_mr_operand_dispatch_order.tsv
: > "$ORDER_FILE"

reachable() {
  curl -fsS -o /dev/null --max-time 8 https://api.github.com 2>/dev/null
}

echo "dispatching ${REPEATS} rounds x 2 arms = $((REPEATS * 2)) runs"

for i in $(seq 1 "$REPEATS"); do
  for arm in control treatment; do
    if [ "$arm" = control ]; then REF=mr-operand-expansion-control; else REF=master; fi
    ok=0
    for try in $(seq 1 60); do
      if reachable; then
        if gh workflow run "$WORKFLOW" --ref "$REF" \
             -f limit=0 -f runs=1 -f temperature=0 -f diagnostics_limit=100 >/tmp/gh_dispatch.log 2>&1; then
          ok=1
          break
        fi
      else
        printf "."
      fi
      sleep 2
    done
    printf "\n"
    if [ "$ok" != 1 ]; then
      echo "FAILED to dispatch $arm round $i" >&2
      cat /tmp/gh_dispatch.log >&2 || true
      exit 1
    fi
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    printf '%s\t%s\t%s\n' "$ts" "$arm" "$REF" >> "$ORDER_FILE"
    echo "[$i] dispatched $arm on $REF at $ts"
  done
done

echo "all $((REPEATS * 2)) dispatches sent"
echo "order file: $ORDER_FILE"
