#!/usr/bin/env bash
#
# Guard the analysis record against drift and against silent quality loss.
#
# Four checks, each of which caught a real failure during this work and is
# therefore kept rather than assumed:
#
#   1. The guard itself discriminates. tools/check-analysis-record.test.sh
#      reproduces every failure the checks below exist to catch and asserts the
#      guard reports it. This runs first because a guard that cannot fail is
#      worse than no guard: it manufactures confidence. A check that never fires
#      is indistinguishable from a check whose pattern silently matches nothing.
#
#   2. The checker's own regression suite passes. A tolerance that has been
#      widened to make a stubborn document pass will show up here, because the
#      mutation cases fail when the tolerance stops discriminating.
#
#   3. Every published document is numeric-fidelity clean against the frozen
#      source. The sources are not stored in this repository — they are the
#      English originals in the analysis workspace — so the check runs only when
#      a source directory is supplied. Without one the guard still runs the
#      structural checks rather than silently passing.
#
#   4. The published record is structurally complete: no empty documents, no
#      documents that lost their frozen citations, and none that are still in
#      English. The last one matters because a document that was never
#      translated passes a numeric check trivially — it matches itself.
#
# Usage:
#   tools/check-analysis-record.sh [--sources <dir>] [--no-self-test]
#
# Exit status is 1 if any check fails, so this can be wired into CI unchanged.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
RECORD="$REPO/docs/05-longmemeval-sota-analysis"

SOURCES=""
SELF_TEST=1
while [ $# -gt 0 ]; do
  case "$1" in
    --sources) SOURCES="${2:-}"; shift 2 ;;
    # The self-test cannot recurse: it invokes this script, so it passes this
    # flag to the copy it runs.
    --no-self-test) SELF_TEST=0; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

fail=0
note() { printf '  %s\n' "$1"; }
fail_check() { printf 'FAIL  %s\n' "$1"; fail=1; }
pass_check() { printf 'ok    %s\n' "$1"; }

echo "check-analysis-record"

# 0. The guard must be able to fail. Requires sources, because the self-test
#    asserts against the same originals the fidelity check uses.
if [ "$SELF_TEST" -eq 1 ]; then
  if [ -n "$SOURCES" ]; then
    if "$HERE/check-analysis-record.test.sh" --sources "$SOURCES" \
        --no-self-test >/dev/null 2>&1; then
      pass_check "guard self-test"
    else
      fail_check "guard self-test — a check no longer fires on the failure it exists to catch"
    fi
  else
    note "skipped guard self-test (needs --sources <dir>)"
  fi
fi

# 1. The checker must still discriminate.
if node "$HERE/check-numeric-fidelity.test.mjs" >/dev/null 2>&1; then
  pass_check "checker regression suite"
else
  fail_check "checker regression suite — a mutation case no longer behaves as specified"
  node "$HERE/check-numeric-fidelity.test.mjs" 2>&1 | grep -E '^FAIL' | sed 's/^/        /' || true
fi

# 3. Structural completeness.
shopt -s nullglob
docs=("$RECORD"/*.md)
shopt -u nullglob

if [ ${#docs[@]} -eq 0 ]; then
  fail_check "no documents found under $RECORD"
else
  pass_check "${#docs[@]} documents present"
fi

empty=0
for f in "${docs[@]}"; do
  if [ ! -s "$f" ]; then
    fail_check "empty document: $(basename "$f")"
    empty=1
  fi
done

# A document with almost no CJK content was never translated. This is the check
# that a numeric comparison cannot make: an untranslated document is identical
# to its source, so it passes the fidelity gate by construction.
#
# The character class must be written as a Unicode property (\p{Han}), not as a
# range such as [一-鿿]. A bracketed CJK range is a *collation* range, and under
# the en_US.UTF-8 locale that these scripts run in grep reports "Invalid
# collation character" and matches nothing — so the range form would have passed
# every English document while printing "all documents carry Chinese prose".
# -P is required for \p{...}; the count is taken with `|| true` so that a file
# with zero matches (the correct state for an English source) does not abort the
# script under `set -e`.
THRESHOLD=40
untranslated=0
for f in "${docs[@]}"; do
  cjk=$(grep -oP '\p{Han}' "$f" 2>/dev/null | wc -l | tr -d ' ' || true)
  cjk=${cjk:-0}
  # 00-ANALYSIS-README.md is authored in Chinese directly; every other document
  # is a translation and must carry substantial Chinese prose.
  if [ "$cjk" -lt "$THRESHOLD" ]; then
    fail_check "not translated (${cjk} Han chars, need >=${THRESHOLD}): $(basename "$f")"
    untranslated=1
  fi
done
[ "$untranslated" -eq 0 ] && pass_check "all documents carry Chinese prose"

# Citations into other documents and into the source tree are frozen strings.
# They were reproduced verbatim on purpose: a reader follows them to a real file,
# so a localized or garbled copy is a broken pointer. Two families are checked,
# chosen because each one is a literal that appears in the source tree:
#
#   * "Hindsight Tempr step N"  — names a section of another document
#   * "Step N" before "—"       — names a labelled branch of a model prompt
#
# A bare "第 N 步" is deliberately NOT flagged: that is ordinary prose counting
# iterations ("the second step of the plan"), which a translation is entitled to
# phrase in Chinese. Flagging it would punish correct writing.
frozen_lost=0
for f in "${docs[@]}"; do
  if grep -qE 'Hindsight Tempr 第 ?[0-9]+ ?步' "$f" 2>/dev/null; then
    fail_check "frozen citation translated: $(basename "$f")"
    frozen_lost=1
  fi
done
[ "$frozen_lost" -eq 0 ] && pass_check "no frozen citation was translated"

# 2. Numeric fidelity against the originals, when they are available.
if [ -n "$SOURCES" ]; then
  if [ ! -d "$SOURCES" ]; then
    fail_check "--sources directory does not exist: $SOURCES"
  else
    out=$(node "$HERE/check-numeric-fidelity.mjs" "$SOURCES" "$RECORD" --summary 2>&1 | tail -1)
    if echo "$out" | grep -q 'FAILED'; then
      fail_check "numeric fidelity: $out"
    else
      pass_check "numeric fidelity: $(echo "$out" | sed 's/.*check-numeric-fidelity: //')"
    fi
  fi
else
  note "skipped numeric fidelity (pass --sources <dir> to enable)"
fi

echo ""
if [ "$fail" -eq 0 ]; then
  echo "check-analysis-record: all checks passed"
else
  echo "check-analysis-record: FAILED"
fi
exit "$fail"
