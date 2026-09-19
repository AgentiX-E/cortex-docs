#!/usr/bin/env bash
# Download the 8 TR time-range A/B artifacts (4 control + 4 treatment).
set -euo pipefail

RUN_IDS="/workspace/analysis/run-ids/ab_tr_timerange_run_ids.tsv"
OUT="/workspace/analysis/ab_tr_timerange"

cd /workspace/cortex
TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
export GH_TOKEN="$TOKEN"

mkdir -p "$OUT"
validate() {
  local dir="$1"
  local qc
  qc=$(python3 -c "import json,glob; f=glob.glob('$dir/*/benchmark-report.json'); print(json.load(open(f[0])).get('questionCount',0) if f else 0)" 2>/dev/null || echo 0)
  [ "$qc" = "500" ]
}

tail -n +2 "$RUN_IDS" | while IFS=$'\t' read -r arm run_id ref; do
  dir="$OUT/run_${run_id}"
  if [ -d "$dir" ] && validate "$dir"; then
    echo "skip $arm $run_id (already downloaded)"
    continue
  fi
  rm -rf "$dir"
  mkdir -p "$dir"
  echo "downloading $arm $run_id"
  for i in 1 2 3 4 5 6 7 8; do
    if gh run download "$run_id" --dir "$dir" >/tmp/dl_tr.log 2>&1; then
      break
    fi
    echo "retry $i: $(tail -1 /tmp/dl_tr.log)"; sleep 4
  done
  if ! validate "$dir"; then
    echo "FAILED to download valid artifacts for $run_id"
  else
    echo "ok $arm $run_id (questionCount=500)"
  fi
done
