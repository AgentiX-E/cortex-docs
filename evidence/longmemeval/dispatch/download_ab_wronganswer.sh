#!/usr/bin/env bash
# Download the wrong-answer diagnostic runs by known run ids.
set -euo pipefail

cd /workspace/cortex
export GH_TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"

OUT=/workspace/analysis/ab_wronganswer
mkdir -p "$OUT"

IDS_FILE=/workspace/analysis/ab_wronganswer_run_ids.tsv
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

mapfile -t IDS < <(awk -F'\t' 'NR>1{print $1}' "$IDS_FILE")
for id in "${IDS[@]}"; do
  dir="$OUT/run_$id"
  if [ -d "$dir" ] && validate "$dir"; then
    echo "$id already complete"
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
    echo "$id OK"
  else
    echo "$id INCOMPLETE" >&2
  fi
done

echo "=== summary ==="
for d in "$OUT"/run_*; do
  [ -d "$d" ] || continue
  n=$(python3 -c "import json; print(json.load(open('$d/benchmark-report.json')).get('questionCount', 0))" 2>/dev/null || echo 0)
  echo "$(basename "$d"): questionCount=$n"
done
