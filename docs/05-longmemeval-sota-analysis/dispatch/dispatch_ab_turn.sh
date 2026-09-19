#!/usr/bin/env bash
# Dispatch the MR turn-level recall A/B: 4 workflow runs per arm, interleaved so
# both arms are sampled at the same instant (time-of-day abstention drift makes
# staggered comparisons invalid).
#
#   control   -> ref = mr-turn-recall-control (183a3cc, no turn-recall channel)
#   treatment -> ref = master                (db92e62, turn-recall channel on)
#
# Full 500-question dataset (limit=0) so all 121 MR questions are in the primary
# deterministic evidence-recall endpoint; diagnostics stay capped at 100.
set -euo pipefail

cd /workspace/cortex
export GH_TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"

WORKFLOW=benchmark.yml
REPEATS=4
START_TS="$(date -u -d '-60 seconds' +%Y-%m-%dT%H:%M:%SZ)"
ORDER_FILE=/workspace/analysis/ab_turn_dispatch_order.tsv
: > "$ORDER_FILE"

echo "dispatch window starts at $START_TS"

for i in $(seq 1 "$REPEATS"); do
  for arm in control treatment; do
    if [ "$arm" = control ]; then REF=mr-turn-recall-control; else REF=master; fi
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    gh workflow run "$WORKFLOW" --ref "$REF" \
      -f limit=0 -f runs=1 -f temperature=0 -f diagnostics_limit=100
    printf '%s\t%s\t%s\n' "$ts" "$arm" "$REF" >> "$ORDER_FILE"
    echo "[$i] dispatched $arm on $REF at $ts"
  done
done

echo "all 8 dispatches sent; resolving run ids..."
