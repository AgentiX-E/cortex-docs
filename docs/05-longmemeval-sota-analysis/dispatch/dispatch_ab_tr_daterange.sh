#!/usr/bin/env bash
# Dispatch the TR date-range recall A/B: 4 control (eb610a0) + 4 treatment
# (master = 4a7c7ce), interleaved, on deepseek-v4-flash non-thinking.
set -euo pipefail

CONTROL_REF="tr-daterange-control"
TREATMENT_REF="master"
ORDER_TSV="/workspace/analysis/run-ids/ab_tr_daterange_dispatch_order.tsv"

cd /workspace/cortex
TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
export GH_TOKEN="$TOKEN"

reachable() {
  timeout 20 gh api repos/AgentiX-E/cortex -q .full_name >/dev/null 2>&1
}

for i in 1 2 3 4 5 6 7 8 9 10; do
  if reachable; then echo "api reachable (try $i)"; break; else echo "unreachable (try $i)"; sleep 5; fi
done

: > "$ORDER_TSV"
printf 'order\tarm\tref\trun_id\n' >> "$ORDER_TSV"

ORDER=1
dispatch() {
  local arm="$1" ref="$2"
  local run_id
  gh workflow run benchmark.yml --ref "$ref" \
    -f limit=0 -f runs=1 -f temperature=0 -f diagnostics_limit=100 \
    -f model=deepseek-v4-flash -f thinking=disabled >/tmp/gh_td.log 2>&1 || true
  sleep 4
  run_id=$(gh run list --workflow=benchmark.yml --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null)
  echo "dispatched $arm ($ref) -> run $run_id"
  printf '%s\t%s\t%s\t%s\n' "$ORDER" "$arm" "$ref" "$run_id" >> "$ORDER_TSV"
  ORDER=$((ORDER+1))
}

for i in 1 2 3 4; do
  dispatch control "$CONTROL_REF"
  dispatch treatment "$TREATMENT_REF"
done

echo "=== dispatch order ==="
cat "$ORDER_TSV"
