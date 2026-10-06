#!/usr/bin/env bash
#
# Self-test for check-analysis-record.sh.
#
# A guard that only ever prints "ok" is indistinguishable from a guard whose
# checks have silently stopped working. Every check in the guard was written
# after a real failure, so this suite reproduces each failure against a
# throwaway copy of the record and asserts that the guard reports it.
#
# The regression check in particular is verified with a *maximally* broken
# checker (one that fails every comparison) rather than a syntactically broken
# one: a trailing comment or a stray newline leaves the module's behaviour
# untouched, so corrupting the file text would prove nothing.
#
# Usage: tools/check-analysis-record.test.sh [--sources <dir>]
#
# Exit status is 1 if any expectation is unmet.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
RECORD_REL="docs/05-longmemeval-sota-analysis"

SOURCES=""
NO_SELF_TEST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --sources) SOURCES="${2:-}"; shift 2 ;;
    # Forwarded to the guard under test. The guard calls this script when its
    # own self-test runs, so without this flag the two would recurse.
    --no-self-test) NO_SELF_TEST=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$SOURCES" ] || [ ! -d "$SOURCES" ]; then
  echo "check-analysis-record.test: --sources <dir> is required (the English originals)"
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

failures=0
total=0

# Copy the record into a scratch tree so a mutation cannot touch the repo.
fresh() {
  rm -rf "$WORK/repo"
  cp -a "$REPO" "$WORK/repo"
}

# run <label> <expected-status> <args...>
# Runs the guard in the scratch tree and asserts on its exit status.
run() {
  local label="$1" expected="$2"; shift 2
  total=$((total + 1))
  local status=0
  local extra=()
  [ "$NO_SELF_TEST" -eq 1 ] && extra=(--no-self-test)
  ( cd "$WORK/repo" && ./tools/check-analysis-record.sh "${extra[@]}" "$@" \
      >/dev/null 2>&1 ) || status=$?
  if [ "$status" -eq "$expected" ]; then
    printf 'ok    %s (exit=%s)\n' "$label" "$status"
  else
    printf 'FAIL  %s (exit=%s, expected=%s)\n' "$label" "$status" "$expected"
    failures=$((failures + 1))
  fi
}

echo "check-analysis-record.test"

# 0. The unmodified record must pass. If this fails, every result below is
#    meaningless, because the guard is not measuring what the others assume.
fresh
run "clean record passes" 0 --sources "$SOURCES"

# 1. An untranslated document. This is the failure the numeric gate cannot see:
#    the file matches its own source exactly, so fidelity reports 94/94.
#
#    The fixture must be built from the English original in "$SOURCES", not
#    copied out of the record. Until this was fixed the line below read
#    `cp "$SOURCES/<doc>" "$WORK/repo/$RECORD_REL/<doc>"`, and that source file
#    does not exist: the guard's own record holds the same path, already
#    translated. `cp` failed, `set -e` did not abort because the copy is
#    followed by the `run` call rather than and-ed to it, and the record was
#    left clean -- so the case reported "exit=0, expected=1", which read as
#    this check being broken while it was in fact working correctly and the
#    fixture was wrong. It is the mirror image of the case it sits beside: the
#    mutation has to actually be applied, or the assertion is about nothing.
fresh
printf '# LongMemEval-S SOTA research notes\n\nA wholly untranslated document.\n' \
  > "$WORK/repo/$RECORD_REL/longmemeval-sota-research.md"
run "untranslated document is caught" 1 --sources "$SOURCES"

# 2. A frozen citation that was localized. "Hindsight Tempr step N" points at a
#    section of another document; the Chinese form points at nothing.
#    -CSD keeps perl in UTF-8 so the replacement does not emit a wide-character
#    warning and, more importantly, so the bytes written are UTF-8 like the rest
#    of the file rather than raw code points.
fresh
perl -CSD -pi -e 's/Hindsight Tempr step 3/Hindsight Tempr \x{7b2c} 3 \x{6b65}/' \
  "$WORK/repo/$RECORD_REL/tr-occurrence-verdict.md" 2>/dev/null
run "localized frozen citation is caught" 1 --sources "$SOURCES"

# 3. An empty document.
fresh
: > "$WORK/repo/$RECORD_REL/mr-dcg-verdict.md"
run "empty document is caught" 1 --sources "$SOURCES"

# 4. A document that lost its Chinese prose (truncated to a stub).
fresh
printf '# stub\n\n中文。\n' > "$WORK/repo/$RECORD_REL/mr-dcg-verdict.md"
run "stub document is caught" 1 --sources "$SOURCES"

# 5. A checker whose tolerance has collapsed: it rejects everything. Half the
#    mutation cases expect a pass, so this must surface.
fresh
cat > "$WORK/repo/tools/check-numeric-fidelity.mjs" <<'BROKEN'
#!/usr/bin/env node
// Self-test fixture: rejects every comparison. The mutation suite must notice,
// because its restatement cases are supposed to pass.
process.exit(1);
BROKEN
run "mis-calibrated checker is caught" 1 --sources "$SOURCES"

# 6. A missing source directory must not be mistaken for a clean run.
fresh
run "absent --sources directory is caught" 1 --sources "$WORK/does-not-exist"

echo ""
if [ "$failures" -eq 0 ]; then
  echo "check-analysis-record.test: ${total}/${total} cases behave as specified"
else
  echo "check-analysis-record.test: ${failures} of ${total} cases WRONG"
fi
exit $((failures == 0 ? 0 : 1))
