#!/usr/bin/env bash
# Download the TR date-anchored recall A/B artifacts (4 control + 4 treatment).
set -euo pipefail

cd /workspace/cortex
TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
export GH_TOKEN="$TOKEN"

ROOT=/workspace/analysis/ab_tr_date
IDS=/workspace/analysis/run-ids/ab_tr_date_run_ids.tsv
mkdir -p "$ROOT"

validate() {
  local dir="$1"
  local qc
  qc=$(python3 -c "import json,glob,sys; f=glob.glob('$dir/*/benchmark-report.json'); print(json.load(open(f[0])).get('questionCount',0) if f else 0)" 2>/dev/null || echo 0)
  [ "$qc" = "500" ]
}

while IFS=$'\t' read -r arm run_id ref; do
  [ "$arm" = "arm" ] && continue
  dir="$ROOT/run_${run_id}"
  if [ -d "$dir" ] && validate "$dir"; then
    echo "skip $arm $run_id (already valid)"
    continue
  fi
  mkdir -p "$dir"
  echo "downloading $arm $run_id"
  gh run download "$run_id" --dir "$dir" >/dev/null 2>&1 || {
    echo "  download failed, retrying once"; sleep 3
    gh run download "$run_id" --dir "$dir" >/dev/null 2>&1 || echo "  STILL FAILED $run_id"
  }
  validate "$dir" && echo "  ok ($arm)" || echo "  INVALID $arm $run_id"
done < "$IDS"
echo "done"
