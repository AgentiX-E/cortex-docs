#!/usr/bin/env bash
# Download the `longmemeval-s-report` artifact of every A/B run into
# analysis/ab_turn/<arm>/run_<id>/. Safe to re-run: a directory that already
# holds a benchmark-report.json is skipped, so partially completed runs are
# simply left for the next invocation.
set -uo pipefail

cd /workspace/cortex
export GH_TOKEN="$(git remote get-url origin | sed -E 's#https://x-access-token:([^@]+)@.*#\1#')"
ARTIFACT=longmemeval-s-report
MANIFEST=/workspace/analysis/ab_turn/run_ids.tsv

while IFS=$'\t' read -r arm id; do
  [ -z "${arm:-}" ] && continue
  dest="/workspace/analysis/ab_turn/$arm/run_$id"
  if [ -f "$dest/benchmark-report.json" ]; then
    echo "skip  $arm $id (already downloaded)"
    continue
  fi
  mkdir -p "$dest"
  if gh run download "$id" -n "$ARTIFACT" -D "$dest" >/dev/null 2>&1; then
    status=$(gh run view "$id" --json conclusion,status --jq '"\(.status)/\(.conclusion)"' 2>/dev/null)
    echo "ok    $arm $id  [$status]  files: $(ls "$dest" | tr '\n' ' ')"
  else
    echo "pend  $arm $id (artifact not ready yet)"
    rmdir "$dest" 2>/dev/null
  fi
done < "$MANIFEST"

echo "--- summary ---"
for arm in control treatment; do
  n=$(find "/workspace/analysis/ab_turn/$arm" -name benchmark-report.json 2>/dev/null | wc -l)
  echo "$arm: $n/4 downloaded"
done
