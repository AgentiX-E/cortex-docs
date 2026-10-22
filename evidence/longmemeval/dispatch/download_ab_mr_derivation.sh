#!/usr/bin/env bash
# Download the MR derivation-routing A/B artifacts by the known run ids.
#
# Every artifact must validate before it is accepted: a workflow run that dies
# early still uploads a ~2 KB stub, and analysing a stub silently produces a
# comparison against nothing. `validate()` therefore requires both per-question
# diagnostics files AND questionCount == 500.
set -euo pipefail

cd /workspace/cortex
export GH_TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"

OUT=/workspace/analysis/ab_mr_derivation
mkdir -p "$OUT/control" "$OUT/treatment"

IDS_FILE=/workspace/analysis/ab_mr_derivation_run_ids.tsv
[ -s "$IDS_FILE" ] || { echo "missing $IDS_FILE" >&2; exit 1; }

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
  n="$(python3 -c "import json; print(json.load(open('$dir/benchmark-report.json')).get('questionCount', 0))" 2>/dev/null || echo 0)"
  [ "$n" = "500" ] || return 1
}

reachable() {
  curl -fsS -o /dev/null --max-time 8 https://api.github.com 2>/dev/null
}

fetch() {
  local arm="$1"; shift
  local -a ids=("$@")
  for id in "${ids[@]}"; do
    local dir="$OUT/$arm/run_$id"
    if [ -d "$dir" ] && validate "$dir"; then
      echo "[$arm] $id already complete"
      continue
    fi
    rm -rf "$dir"; mkdir -p "$dir"
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

mapfile -t CONTROL_IDS < <(awk -F'\t' '$1=="control"{print $2}' "$IDS_FILE")
mapfile -t TREATMENT_IDS < <(awk -F'\t' '$1=="treatment"{print $2}' "$IDS_FILE")

echo "control   : ${CONTROL_IDS[*]}"
echo "treatment : ${TREATMENT_IDS[*]}"

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
