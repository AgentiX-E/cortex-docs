#!/usr/bin/env bash
# Dispatch the TR two-event temporal A/B: 4 workflow runs per arm, interleaved so
# that both arms are sampled at the same instant.
#
# Time-of-day abstention drift makes any staggered comparison invalid, so the
# arms alternate within each round rather than being dispatched as two blocks.
#
#   control   -> ref = tr-two-event-control (db92e62, measures to question date)
#   treatment -> ref = master              (d793db4, measures between the events)
#
# Full 500-question dataset (limit=0) so all 127 TR questions are in the sample;
# diagnostics stay capped at 100. temperature=0 throughout.
#
# Why 4 runs per arm even though the arithmetic is deterministic: the two-event
# answer depends on WHICH events the LLM extracts, and that step is sampled. The
# majority-vote bucket over 4 runs is the pre-registered unit of analysis.
set -euo pipefail

cd /workspace/cortex
export GH_TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"

WORKFLOW=benchmark.yml
REPEATS=4
ORDER_FILE=/workspace/analysis/ab_tr_two_event_dispatch_order.tsv
: > "$ORDER_FILE"

echo "dispatching ${REPEATS} rounds x 2 arms = $((REPEATS * 2)) runs"

for i in $(seq 1 "$REPEATS"); do
  for arm in control treatment; do
    if [ "$arm" = control ]; then REF=tr-two-event-control; else REF=master; fi
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    gh workflow run "$WORKFLOW" --ref "$REF" \
      -f limit=0 -f runs=1 -f temperature=0 -f diagnostics_limit=100
    printf '%s\t%s\t%s\n' "$ts" "$arm" "$REF" >> "$ORDER_FILE"
    echo "[$i] dispatched $arm on $REF at $ts"
  done
done

echo "all $((REPEATS * 2)) dispatches sent"
echo "order file: $ORDER_FILE"
