#!/usr/bin/env python3
"""
Recover the diagnostics blobs that the benchmark workflow printed into its log.

Artifact download is broken in this sandbox (the redirect target resolves into a
sinkhole), but the workflow also pretty-prints each diagnostics array to stdout,
one JSON token per log line, each wrapped in the Actions log prefix

    <job name>\t<step>\t<timestamp>Z <content>

so the blob can be rebuilt by stripping that prefix and re-parsing. The log is
UTF-8 with a BOM, hence utf-8-sig.
"""
import json
import re
import sys

# The run directory is an argument, not a constant. It was a constant, and
# re-running the script for a second run silently overwrote the first run's
# diagnostics -- the baseline every comparison is made against. Making it a
# parameter is what stops a second analysis from destroying the first.
RUN_DIR = sys.argv[1] if len(sys.argv) > 1 else '/workspace/analysis/ab_retry/run_34791592602'
LOG = f'{RUN_DIR}/run.log'
# Two log shapes appear depending on how the archive was fetched. `gh run view
# --log` emits `<job>\t<step>\t<timestamp>Z <content>`; the REST archive emits
# `<timestamp>Z <content>`. Strip whichever prefix is present, and leave a line
# alone when it carries neither -- guessing would eat real content.
PREFIX = re.compile(r'^(?:[^\t]*\t[^\t]*\t)?\d{4}-\d{2}-\d{2}T[\d:.\-]+Z ')

raw = open(LOG, encoding='utf-8-sig', errors='replace').read()

# Section markers the bench prints before each blob.
sections = []
for m in re.finditer(r'=== ([A-Za-z\- ]*diagnostics) ===', raw):
    sections.append((m.group(1), m.end()))
sections.append(('__end__', len(raw)))
print('sections:', [s[0] for s in sections], file=sys.stderr)

out = {}
for (name, start), (_, end) in zip(sections, sections[1:]):
    chunk = raw[start:end]
    buf = []
    for line in chunk.split('\n'):
        if not line.strip():
            continue
        # A UTF-8 BOM can appear mid-stream, not just at the file head: the log is
        # assembled from several writer flushes and one of them re-emits the BOM.
        # Line-wise prefix stripping then fails on exactly that line, and because
        # the failure is silent the blob is truncated rather than rejected -- the
        # JSON parser reports it far away, at the point where the balance breaks.
        line = line.lstrip('\ufeff')
        buf.append(PREFIX.sub('', line))
    text = '\n'.join(buf)
    # Trim to the balanced top-level array/object, skipping brackets and braces
    # that occur inside JSON string values (LLM output is full of them).
    depth = 0
    stop = None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in '[{':
            depth += 1
        elif ch in ']}':
            depth -= 1
            if depth == 0:
                stop = i + 1
                break
    if stop is None:
        print(f'{name}: no balanced blob', file=sys.stderr)
        continue
    blob = text[:stop]
    try:
        data = json.loads(blob)
    except Exception as e:
        print(f'{name}: parse failed {e}; first 200 chars: {blob[:200]!r}', file=sys.stderr)
        continue
    key = name.strip().replace(' ', '_')
    out[key] = data
    print(f'{key}: {len(data)} records', file=sys.stderr)

for key, data in out.items():
    path = f'{RUN_DIR}/{key}.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    print(f'wrote {path}', file=sys.stderr)
