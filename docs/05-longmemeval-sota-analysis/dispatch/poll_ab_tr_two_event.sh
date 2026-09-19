#!/usr/bin/env bash
# Poll until all 8 A/B artifacts are downloaded, then stop.
set -uo pipefail
for i in $(seq 1 60); do
  /workspace/analysis/download_ab_tr_two_event.sh > /tmp/ab_tr_dl.log 2>&1
  c=$(find /workspace/analysis/ab_tr_two_event/control -name benchmark-report.json 2>/dev/null | wc -l)
  t=$(find /workspace/analysis/ab_tr_two_event/treatment -name benchmark-report.json 2>/dev/null | wc -l)
  echo "[poll $i $(date -u +%H:%M:%S)] control=$c/4 treatment=$t/4"
  if [ "$c" -ge 4 ] && [ "$t" -ge 4 ]; then
    echo "ALL 8 DOWNLOADED"
    break
  fi
  sleep 150
done
