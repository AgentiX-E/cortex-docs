#!/usr/bin/env python3
"""Attribute MR errors to retrieval vs. extraction, offline and without an LLM.

Why this exists
---------------
MR sits at 79-84% and nobody has established *where* the remaining error lives.
Two very different stories fit the same headline number:

  1. The answer sessions never reach the model, so the enumeration it performs
     is over the wrong evidence. Remedy: retrieval.
  2. The sessions arrive, but the enumerated timeline is misread (double
     counting, missing an item, arithmetic). Remedy: extraction.

Telling them apart needs no judge and no API call. Every MR instance carries
`answer_session_ids`, and the diagnostics record the rendered `retrieved`
string. A gold session is either present in the retrieved text or it is not.
We can therefore separate:

  - MISSING   : at least one gold session absent  -> retrieval-caused, the model
                could not have answered correctly from what it was given.
  - PRESENT   : every gold session present        -> the evidence was in hand;
                any error here is extraction (or grading).

The comparison is deliberately conservative about what counts as "present":
sessions are rendered as `[timestamp] role: text`, and we test for a long
verbatim span of the session body rather than its id, because ids are not
rendered into the prompt.

Usage:
  mr_attribution.py RUN_DIR
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _session_bodies(instance: dict) -> list[tuple[str, str]]:
    """Pair each gold session id with its rendered content."""
    ids = instance.get("answer_session_ids") or []
    contents = instance.get("answer_sessions_content") or []
    return list(zip(ids, contents))


def _is_present(body: str, retrieved: str, window: int = 200) -> bool:
    """Test whether a gold session appears in the retrieved text.

    The prompt renders whole sessions, so a verbatim window taken from the
    middle of the session body is a robust probe. We normalise whitespace
    on both sides because the renderer collapses newlines.
    """
    if not body:
        return False
    norm_retrieved = " ".join(retrieved.split())
    # Probe several disjoint windows; a single one can straddle a truncation
    # boundary and produce a false negative.
    body_flat = " ".join(body.split())
    if len(body_flat) <= window:
        return body_flat in norm_retrieved
    step = max(1, len(body_flat) // 4)
    probes = [body_flat[i : i + window] for i in range(0, len(body_flat) - window + 1, step)]
    return any(p in norm_retrieved for p in probes)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    run_dir = Path(argv[1])
    diag_path = run_dir / "benchmark-mr-diagnostics.json"
    records = json.loads(diag_path.read_text())

    buckets = {"MISSING": [], "PRESENT": []}
    for r in records:
        retrieved = r.get("decision", {}).get("retrieved") or ""
        pairs = _session_bodies(r)
        if not pairs:
            continue
        missing = [sid for sid, body in pairs if not _is_present(body, retrieved)]
        key = "MISSING" if missing else "PRESENT"
        buckets[key].append((r, missing))

    total = sum(len(v) for v in buckets.values())
    print(f"# MR error attribution -- {run_dir.name}")
    print(f"\nInstances with a gold session list: {total}\n")
    print("| evidence state | n | correct | accuracy |")
    print("|---|---|---|---|")
    for key in ("PRESENT", "MISSING"):
        rows = buckets[key]
        if not rows:
            continue
        n = len(rows)
        c = sum(1 for r, _ in rows if r["correct"])
        print(f"| {key} | {n} | {c} | {100 * c / n:.1f}% |")

    correct = sum(1 for r in records if r["correct"])
    print(f"\nOverall: {correct}/{len(records)} = {100 * correct / len(records):.1f}%")

    # How much of the remaining error is retrieval-attributable?
    missing_errors = sum(1 for r, _ in buckets["MISSING"] if not r["correct"])
    all_errors = len(records) - correct
    print(
        f"Errors: {all_errors}. Retrieval-attributable (>=1 gold session absent): "
        f"{missing_errors} ({100 * missing_errors / all_errors:.1f}% of errors)."
    )

    # Abstentions are a distinct failure mode: the system declined to answer.
    abst = [r for r in records if r.get("decision", {}).get("abstained")]
    print(f"Abstentions: {len(abst)} (correct among them: {sum(1 for r in abst if r['correct'])})")

    # Show a few PRESENT-but-wrong examples, where extraction is implicated.
    print("\n## PRESENT but wrong (extraction-attributable) -- first 8")
    shown = 0
    for r, _ in buckets["PRESENT"]:
        if r["correct"]:
            continue
        print(
            f"- gold={r['ground_truth']!r} predicted={r['decision']['answer']!r} "
            f"| {r['question'][:90]}"
        )
        shown += 1
        if shown >= 8:
            break

    print("\n## MISSING and wrong (retrieval-attributable) -- first 8")
    shown = 0
    for r, missing in buckets["MISSING"]:
        if r["correct"]:
            continue
        print(
            f"- missing {len(missing)} session(s) | gold={r['ground_truth']!r} "
            f"predicted={r['decision']['answer']!r} | {r['question'][:80]}"
        )
        shown += 1
        if shown >= 8:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
