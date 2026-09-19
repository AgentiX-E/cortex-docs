#!/usr/bin/env bash
# Poll the 8 A/B workflow runs until every one has finished, then download their
# artifacts. Bounded so it can never hang forever.
set -uo pipefail

cd /workspace/cortex
export GH_TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
IDS=(33869168522 33869172544 33869177056 33869180832 33869184376 33869188968 33869193549 33869197057)
DEADLINE=$(( $(date +%s) + 7800 ))   # 130 min
INTERVAL=90

while true; do
  now=$(date +%s)
  if [ "$now" -gt "$DEADLINE" ]; then
    echo "DEADLINE REACHED - stopping poll"
    break
  fi
  line=""
  pending=0
  for id in "${IDS[@]}"; do
    st=$(gh run view "$id" --json status,conclusion --jq '"\(.status)/\(.conclusion // "-")"' 2>/dev/null)
    [ -z "$st" ] && st="unknown"
    case "$st" in
      completed/*) ;;
      *) pending=$((pending + 1)) ;;
    esac
    line="$line $st"
  done
  echo "$(date -u +%H:%M:%S) pending=$pending |$line"
  if [ "$pending" -eq 0 ]; then
    echo "ALL RUNS FINISHED"
    break
  fi
  sleep "$INTERVAL"
done

echo "=== downloading ==="
bash /workspace/analysis/download_ab_turn.sh
