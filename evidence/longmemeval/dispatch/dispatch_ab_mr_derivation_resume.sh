#!/usr/bin/env bash
# Resume the MR derivation-routing A/B dispatch after the control round-1 run
# (33953397813) already went out. This sends the remaining 7 runs in the same
# interleaved order, probing api.github.com (the host `gh` actually talks to)
# instead of github.com, whose TLS handshake resets intermittently in this
# sandbox even while git/gh work fine.
set -euo pipefail

cd /workspace/cortex
TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
export GH_TOKEN="$TOKEN"

WORKFLOW=benchmark.yml
ORDER_FILE=/workspace/analysis/ab_mr_derivation_dispatch_order.tsv

# Remaining dispatches, in the same interleaved order: after control r1, the
# script still owes treatment r1, then rounds 2..4 (control then treatment).
REMAINING=(
  "treatment:master"
  "control:mr-derivation-control"
  "treatment:master"
  "control:mr-derivation-control"
  "treatment:master"
  "control:mr-derivation-control"
  "treatment:master"
)

reachable() {
  curl -fsS -o /dev/null --max-time 8 https://api.github.com 2>/dev/null
}

echo "resuming: ${#REMAINING[@]} dispatches"
n=1
for entry in "${REMAINING[@]}"; do
  arm="${entry%%:*}"
  REF="${entry#*:}"
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
    echo "FAILED to dispatch $arm on $REF (log:)" >&2
    cat /tmp/gh_dispatch.log >&2 || true
    exit 1
  fi
  ts="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
  printf '%s\t%s\t%s\n' "$ts" "$arm" "$REF" >> "$ORDER_FILE"
  echo "[$n/${#REMAINING[@]}] dispatched $arm on $REF at $ts"
  n=$((n + 1))
done

echo "resume complete; order file:"
cat "$ORDER_FILE"
