#!/usr/bin/env bash
# Download the TR turn-anchor A/B v2 artifacts (4 control + 4 treatment).
set -euo pipefail

ROOT="/workspace/analysis/ab_tr_turnanchor"
IDS="/workspace/analysis/run-ids/ab_tr_turnanchor_v2_run_ids.tsv"
mkdir -p "$ROOT"

cd /workspace/cortex
TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
export GH_TOKEN="$TOKEN"

validate() {
  local dir="$1"
  local f
  f=$(find "$dir" -name benchmark-report.json 2>/dev/null | head -1)
  if [ -z "$f" ]; then
    return 1
  fi
  local qc
  qc=$(python3 -c "import json; print(json.load(open('$f')).get('questionCount',0))" 2>/dev/null || echo 0)
  [ "$qc" = "500" ]
}

while IFS=$'\t' read -r arm run_id ref; do
  [ "$arm" = "arm" ] && continue
  dir="$ROOT/run_$run_id"
  if validate "$dir" 2>/dev/null; then
    echo "skip $run_id (already valid)"
    continue
  fi
  for i in 1 2 3 4 5 6 7 8; do
    if gh run download "$run_id" --dir "$dir" >/tmp/dl_ta.log 2>&1; then
      if validate "$dir"; then
        echo "downloaded $run_id ($arm)"
        break
      fi
    fi
    echo "retry $run_id ($i)"
    sleep 4
  done
done < "$IDS"

echo "=== final validation ==="
for d in "$ROOT"/run_*; do
  n=$(python3 -c "import json,glob; f=glob.glob('$d/*/benchmark-report.json'); print(json.load(open(f[0])).get('questionCount',0) if f else 0)" 2>/dev/null)
  echo "$(basename "$d") -> ${n:-0}"
done
