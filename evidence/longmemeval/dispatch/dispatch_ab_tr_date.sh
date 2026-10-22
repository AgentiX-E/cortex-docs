#!/usr/bin/env bash
# Dispatch the TR date-anchored recall A/B: 4 runs per arm, INTERLEAVED.
#   control   -> ref = tr-date-control (afd5dd5, semantic/lexical recall only)
#   treatment -> ref = master          (c8e5257, date-proximity re-rank)
set -euo pipefail

cd /workspace/cortex
TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
export GH_TOKEN="$TOKEN"

WORKFLOW=benchmark.yml
REPEATS=4
ORDER_FILE=/workspace/analysis/run-ids/ab_tr_date_dispatch_order.tsv
: > "$ORDER_FILE"

reachable() {
  curl -fsS -o /dev/null --max-time 8 https://api.github.com 2>/dev/null
}

for i in $(seq 1 "$REPEATS"); do
  for arm in control treatment; do
    if [ "$arm" = control ]; then REF=tr-date-control; else REF=master; fi
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
      echo "FAILED $arm round $i" >&2
      cat /tmp/gh_dispatch.log >&2 || true
      exit 1
    fi
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    printf '%s\t%s\t%s\n' "$ts" "$arm" "$REF" >> "$ORDER_FILE"
    echo "[$i] $arm on $REF at $ts"
  done
done
echo "all $((REPEATS * 2)) dispatched"
