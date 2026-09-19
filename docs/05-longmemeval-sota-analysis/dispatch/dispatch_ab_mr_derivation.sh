#!/usr/bin/env bash
# Dispatch the MR derivation-routing A/B: 4 workflow runs per arm, INTERLEAVED
# so both arms are sampled at the same instant.
#
# Time-of-day abstention drift makes any staggered comparison invalid, so the
# arms alternate within each round rather than being dispatched as two blocks.
#
#   control   -> ref = mr-derivation-control (4640c86, parent commit; the four
#                      duration/age phrasings route to ENUMERATION)
#   treatment -> ref = master                 (a104ea0, routes them to DERIVATION)
#
# Parameters match the previous KU A/B so the experiments stay comparable:
# full 500-question dataset (limit=0), runs=1, temperature=0, diagnostics_limit=100.
#
# The primary endpoint is the MR abstention rate on the re-routed questions,
# which is sampled, not deterministic, so four runs per arm bound the variance.
#
# The sandbox network intermittently resets the TLS handshake to github.com, so
# every dispatch is retried behind a reachability probe until it is accepted.
set -euo pipefail

cd /workspace/cortex
TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
export GH_TOKEN="$TOKEN"

WORKFLOW=benchmark.yml
REPEATS=4
ORDER_FILE=/workspace/analysis/ab_mr_derivation_dispatch_order.tsv
: > "$ORDER_FILE"

reachable() {
  curl -fsS -o /dev/null --max-time 8 https://github.com 2>/dev/null
}

echo "token length: ${#TOKEN}"
echo "dispatching ${REPEATS} rounds x 2 arms = $((REPEATS * 2)) runs"

for i in $(seq 1 "$REPEATS"); do
  for arm in control treatment; do
    if [ "$arm" = control ]; then REF=mr-derivation-control; else REF=master; fi
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
