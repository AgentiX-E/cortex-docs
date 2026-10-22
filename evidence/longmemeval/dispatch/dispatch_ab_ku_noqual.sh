#!/usr/bin/env bash
# Dispatch the KU no-qualifier A/B: 4 workflow runs per arm, INTERLEAVED so both
# arms are sampled at the same instant.
#
# Time-of-day abstention drift makes any staggered comparison invalid, so the
# arms alternate within each round rather than being dispatched as two blocks.
#
#   control   -> ref = ku-no-qualifier-control (d793db4, prompt without a
#                      no-qualifier Step 2 branch)
#   treatment -> ref = master                 (4640c86, prompt with the branch
#                      plus anti-abstention guardrails)
#
# Parameters are identical to the previous TR two-event A/B so the two
# experiments stay comparable: full 500-question dataset (limit=0), runs=1,
# temperature=0, diagnostics_limit=100.
#
# Why 4 runs per arm when the primary endpoint is a mechanism: the endpoint is
# KU abstention RATE, and which questions the model abstains on is sampled, not
# deterministic. Four runs per arm bounds that sampling variance.
#
# The sandbox network intermittently resets the TLS handshake to github.com, so
# every dispatch is retried behind a reachability probe until it is accepted.
set -euo pipefail

cd /workspace/cortex
export GH_TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"

WORKFLOW=benchmark.yml
REPEATS=4
ORDER_FILE=/workspace/analysis/ab_ku_noqual_dispatch_order.tsv
: > "$ORDER_FILE"

reachable() {
  curl -fsS -o /dev/null --max-time 8 https://github.com 2>/dev/null
}

echo "dispatching ${REPEATS} rounds x 2 arms = $((REPEATS * 2)) runs"

for i in $(seq 1 "$REPEATS"); do
  for arm in control treatment; do
    if [ "$arm" = control ]; then REF=ku-no-qualifier-control; else REF=master; fi
    ok=0
    for try in $(seq 1 60); do
      if reachable; then
        if gh workflow run "$WORKFLOW" --ref "$REF" \
             -f limit=0 -f runs=1 -f temperature=0 -f diagnostics_limit=100 2>&1 | tail -1; then
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
      exit 1
    fi
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    printf '%s\t%s\t%s\n' "$ts" "$arm" "$REF" >> "$ORDER_FILE"
    echo "[$i] dispatched $arm on $REF at $ts"
  done
done

echo "all $((REPEATS * 2)) dispatches sent"
echo "order file: $ORDER_FILE"
