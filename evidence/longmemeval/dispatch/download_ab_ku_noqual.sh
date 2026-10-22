#!/usr/bin/env bash
# Download the KU no-qualifier A/B artifacts.
#
# Every artifact must validate before it is accepted: a workflow run that dies
# early still uploads a ~2 KB stub, and analysing a stub silently produces a
# comparison against nothing. `validate()` therefore requires both per-question
# diagnostics files AND questionCount == 500.
set -euo pipefail

cd /workspace/cortex
export GH_TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"

OUT=/workspace/analysis/ab_ku_noqual
mkdir -p "$OUT/control" "$OUT/treatment"

ORDER_FILE=/workspace/analysis/ab_ku_noqual_dispatch_order.tsv
if [ ! -s "$ORDER_FILE" ]; then
  echo "missing dispatch order file: $ORDER_FILE" >&2
  exit 1
fi

REQUIRED=(
  "benchmark-report.json"
  "benchmark-single-session-diagnostics.json"
  "benchmark-mr-diagnostics.json"
)

validate() {
  local dir="$1"
  for f in "${REQUIRED[@]}"; do
    [ -s "$dir/$f" ] || return 1
  done
  local n
  n="$(python3 -c "import json,sys; print(json.load(open('$dir/benchmark-report.json')).get('questionCount', 0))" 2>/dev/null || echo 0)"
  [ "$n" = "500" ] || return 1
}

reachable() {
  curl -fsS -o /dev/null --max-time 8 https://github.com 2>/dev/null
}

# Map dispatch timestamps onto run ids. The workflow exposes no correlation id,
# so the arm is recovered from the head branch the run executed on.
# Runs are selected by CREATION TIME, not just branch: `master` also carries the
# earlier TR two-event experiment, and downloading one of those stalls on an
# expired artifact instead of failing fast.
SINCE="${SINCE:-2026-09-05T02:00:00Z}"
pick() {
  gh run list --workflow=benchmark.yml --limit 40 \
    --json databaseId,headBranch,createdAt \
    --jq --arg since "$SINCE" \
      '.[] | select(.headBranch == $branch) | select(.createdAt >= $since) | .databaseId'
}
mapfile -t CONTROL_IDS < <(gh run list --workflow=benchmark.yml --limit 40 \
  --json databaseId,headBranch,createdAt \
  --jq --arg since "$SINCE" \
    '.[] | select(.headBranch == "ku-no-qualifier-control") | select(.createdAt >= $since) | .databaseId')
mapfile -t TREATMENT_IDS < <(gh run list --workflow=benchmark.yml --limit 40 \
  --json databaseId,headBranch,createdAt \
  --jq --arg since "$SINCE" \
    '.[] | select(.headBranch == "master") | select(.createdAt >= $since) | .databaseId')

echo "control ids  : ${CONTROL_IDS[*]}"
echo "treatment ids: ${TREATMENT_IDS[*]}"

fetch() {
  local arm="$1"; shift
  local -a ids=("$@")
  for id in "${ids[@]}"; do
    local dir="$OUT/$arm/run_$id"
    if [ -d "$dir" ] && validate "$dir"; then
      echo "[$arm] $id already complete"
      continue
    fi
    mkdir -p "$dir"
    for try in $(seq 1 40); do
      if reachable; then
        if gh run download "$id" -n longmemeval-s-report -D "$dir" >/dev/null 2>&1; then
          break
        fi
      else
        printf "."
      fi
      sleep 3
    done
    printf "\n"
    if validate "$dir"; then
      echo "[$arm] $id OK"
    else
      echo "[$arm] $id INCOMPLETE (stub or failed run)" >&2
    fi
  done
}

fetch control "${CONTROL_IDS[@]}"
fetch treatment "${TREATMENT_IDS[@]}"

echo ""
echo "=== summary ==="
for arm in control treatment; do
  n=0
  for d in "$OUT/$arm"/run_*; do
    [ -d "$d" ] || continue
    if validate "$d"; then n=$((n + 1)); fi
  done
  echo "$arm: $n complete run(s)"
done
