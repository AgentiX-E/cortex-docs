#!/usr/bin/env bash
# Download the `longmemeval-s-report` artifact of every run in the TR two-event
# A/B into analysis/ab_tr_two_event/<arm>/run_<id>/.
#
# Safe to re-run: a directory that already holds a benchmark-report.json is
# skipped, so a partially completed run is simply left for the next invocation.
set -uo pipefail

cd /workspace/cortex
export GH_TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
ARTIFACT=longmemeval-s-report
MANIFEST=/workspace/analysis/ab_tr_two_event_run_ids.tsv

# A failed run still uploads an artifact: the workflow's upload step runs on
# failure too, and the stub is ~2 KB. Accepting it would silently put an empty
# run into the analysis, so a download is only accepted once it contains the
# per-question diagnostics AND the report covers all 500 questions.
validate() {
  local d="$1"
  [ -f "$d/benchmark-report.json" ] || return 1
  [ -f "$d/benchmark-single-session-diagnostics.json" ] || return 1
  [ -f "$d/benchmark-mr-diagnostics.json" ] || return 1
  local n
  n=$(python3 -c "
import json,sys
try:
    print(json.load(open('$d/benchmark-report.json'))['questionCount'])
except Exception:
    print(0)
" 2>/dev/null)
  [ "$n" = "500" ] || return 1
  return 0
}

while IFS=$'\t' read -r arm id; do
  [ -z "${arm:-}" ] && continue
  dest="/workspace/analysis/ab_tr_two_event/$arm/run_$id"
  if validate "$dest"; then
    echo "skip  $arm $id (already downloaded and valid)"
    continue
  fi
  mkdir -p "$dest"
  if gh run download "$id" -n "$ARTIFACT" -D "$dest" >/dev/null 2>&1; then
    if validate "$dest"; then
      echo "ok    $arm $id  files: $(ls "$dest" | tr '\n' ' ')"
    else
      st=$(gh run view "$id" --json conclusion --jq .conclusion 2>/dev/null)
      echo "REJECT $arm $id (stub or incomplete, run conclusion=$st)"
      rm -rf "$dest"
    fi
  else
    echo "pend  $arm $id (artifact not ready yet)"
    rmdir "$dest" 2>/dev/null
  fi
done < "$MANIFEST"

echo "--- summary ---"
for arm in control treatment; do
  n=$(find "/workspace/analysis/ab_tr_two_event/$arm" -name benchmark-report.json 2>/dev/null | wc -l)
  echo "$arm: $n/4 downloaded"
done
