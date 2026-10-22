#!/usr/bin/env bash
# Dispatch the TR time-range A/B: 4 control (85f1e6b) + 4 treatment (master),
# interleaved, on deepseek-v4-flash non-thinking (the stable reader baseline).
set -euo pipefail

CONTROL_REF="tr-timerange-control"
TREATMENT_REF="master"
ORDER_TSV="/workspace/analysis/run-ids/ab_tr_timerange_dispatch_order.tsv"

cd /workspace/cortex
TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
export GH_TOKEN="$TOKEN"

reachable() {
  timeout 20 gh api repos/AgentiX-E/cortex -q .full_name >/dev/null 2>&1
}

# Wait until the API is reachable before dispatching anything.
for i in 1 2 3 4 5 6 7 8 9 10; do
  if reachable; then echo "api reachable (try $i)"; break; else echo "unreachable (try $i)"; sleep 5; fi
done

: > "$ORDER_TSV"
printf 'order\tarm\tref\trun_id\n' >> "$ORDER_TSV"

dispatch() {
  local arm="$1" ref="$2"
  local out run_id
  out=$(gh workflow run benchmark.yml --ref "$ref" \
    -f limit=0 -f runs=1 -f temperature=0 -f diagnostics_limit=100 \
    -f model=deepseek-v4-flash -f thinking=disabled 2>&1) && true
  # workflow run prints nothing on success; wait then capture the newest run id.
  sleep 4
  run_id=$(gh run list --workflow=benchmark.yml --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null)
  echo "dispatched $arm ($ref) -> run $run_id"
  printf '%s\t%s\t%s\t%s\n' "$((++ORDER))" "$arm" "$ref" "$run_id" >> "$ORDER_TSV"
}

ORDER=0
for i in 1 2 3 4; do
  dispatch control "$CONTROL_REF"
  dispatch treatment "$TREATMENT_REF"
done

echo "=== dispatch order ==="
cat "$ORDER_TSV"
