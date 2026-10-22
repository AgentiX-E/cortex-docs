#!/usr/bin/env bash
# Re-dispatch the TR occurrence-date A/B v2: 4 control (13d6b15) + 4 treatment
# (master = 0e8aaae), interleaved, deepseek-v4-flash non-thinking. This doubles
# the sample from the v1 batch (n=4 -> n=8 per arm) to lift statistical power.
set -euo pipefail

CONTROL_REF="tr-occurrence-control"
TREATMENT_REF="master"
ORDER_TSV="/workspace/analysis/run-ids/ab_tr_occurrence_v2_dispatch_order.tsv"

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

# Baseline: latest run id per branch before dispatching, so we can detect the
# newly created run instead of racing on "latest".
baseline_run() {
  gh run list --workflow=benchmark.yml --branch "$1" --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null || echo ""
}

ORDER=1
dispatch() {
  local arm="$1" ref="$2"
  local before new run_id
  before="$(baseline_run "$ref")"
  gh workflow run benchmark.yml --ref "$ref" \
    -f limit=0 -f runs=1 -f temperature=0 -f diagnostics_limit=100 \
    -f model=deepseek-v4-flash -f thinking=disabled >/tmp/gh_v2.log 2>&1 || true
  run_id=""
  for try in $(seq 1 20); do
    sleep 3
    new="$(baseline_run "$ref")"
    if [ -n "$new" ] && [ "$new" != "$before" ]; then
      run_id="$new"
      break
    fi
  done
  echo "dispatched $arm ($ref) -> run $run_id (baseline was ${before:-none})"
  printf '%s\t%s\t%s\t%s\n' "$ORDER" "$arm" "$ref" "$run_id" >> "$ORDER_TSV"
  ORDER=$((ORDER+1))
}

for i in 1 2 3 4; do
  dispatch control "$CONTROL_REF"
  dispatch treatment "$TREATMENT_REF"
done

echo "=== dispatch order ==="
cat "$ORDER_TSV"
