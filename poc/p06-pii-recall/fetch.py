#!/usr/bin/env python3
"""Fetch a public, human-annotated PII corpus and reduce it to rows our policy must call private.

## Why a corpus at all, and why this one

G2 asked how to tighten the false-share bound without labelling 600 sentences by hand. The
answer is not "ask a model": the model is one of the two objects under comparison, and the
external evidence on exactly this judgement is that a model's answer varies 25% across repeats
of one prompt. The answer is to find human annotation that already exists and transfer it.

`pii-masking-200k` (ai4privacy) annotates PII spans in real text with labels — EMAIL, TEL,
CREDIT_CARD, SSN, STREET and so on. That gives a *machine-checkable* positive set: if a sentence
contains a human-annotated credit-card number, then our published policy says the sentence is
private, and a rule layer that lets it through is wrong by its own definition. No new human
labour, and the labels are not ours.

## What is deliberately excluded

Only rows whose **every** annotated span falls in the deterministic categories are kept. A row
that also contains a person's name is dropped, because our policy does not make "a name" private
on its own (it becomes private through `third-party` only when framed as someone else's
information). Keeping those rows would score the rule layer against a policy it does not claim.

## Why the output is a file rather than a measurement

Fetching needs the Hub; measuring must not. Splitting them means the measurement can be re-run
offline against a frozen `candidates.json`, which is what makes the number reviewable at all.
"""

from __future__ import annotations

import argparse
import json
import os

CANDIDATES = [
    ("ai4privacy/pii-masking-200k", "train"),
    ("Isotonic/pii-masking-200k", "train"),
]

# Labels that force "private" under the published rule table (docs/02 section 5.3). Anything not
# listed here is *not* a policy violation if it goes out, so it must not enter the denominator.
FORCING = {
    "credential": ("password", "passwd", "api", "key", "secret", "token", "pin", "passphrase"),
    "strong-pii": (
        "email",
        "mail",
        "tel",
        "phone",
        "credit",
        "card",
        "iban",
        "bank",
        "account",
        "ssn",
        "social",
        "idcard",
        "id_card",
        "idnumber",
        "passport",
        "driver",
        "licence",
        "license",
        "street",
        "address",
        "postal",
        "zip",
    ),
}


def category_of(label: str) -> str | None:
    lowered = label.lower().replace("-", "_").replace(" ", "_")
    for category, needles in FORCING.items():
        if any(needle in lowered for needle in needles):
            return category
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3000)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    errors: list[str] = []
    try:
        from datasets import load_dataset  # noqa: PLC0415 -- optional dependency, CI only
    except Exception as error:  # noqa: BLE001
        payload = {"status": "unavailable", "reason": f"datasets not importable: {error}", "errors": errors}
        json.dump(payload, open(args.out, "w", encoding="utf-8"), indent=2)
        print(json.dumps(payload, indent=2))
        return 0

    token = os.environ.get("HF_TOKEN") or None
    dataset = None
    used = None
    for name, split in CANDIDATES:
        try:
            dataset = load_dataset(name, split=split, streaming=True, token=token)
            used = name
            break
        except Exception as error:  # noqa: BLE001
            errors.append(f"{name}: {type(error).__name__}: {error}")

    if dataset is None:
        payload = {"status": "unavailable", "reason": "no candidate dataset could be opened", "errors": errors}
        json.dump(payload, open(args.out, "w", encoding="utf-8"), indent=2)
        print(json.dumps(payload, indent=2)[:3000])
        return 0

    kept: list[dict] = []
    seen: set[str] = set()
    scanned = 0
    label_census: dict[str, int] = {}
    dropped_mixed = 0

    for row in dataset:
        scanned += 1
        text = row.get("source_text") or row.get("unmasked_text") or ""
        spans = row.get("privacy_mask") or row.get("privacy_mask_labels") or []
        if not text or not spans:
            if scanned > args.limit * 40:
                break
            continue

        labels = []
        for span in spans:
            label = span.get("label") if isinstance(span, dict) else str(span)
            if label:
                labels.append(label)
                label_census[label] = label_census.get(label, 0) + 1
        if not labels:
            continue

        categories = [category_of(label) for label in labels]
        if any(category is None for category in categories):
            dropped_mixed += 1
            continue
        if text in seen:
            continue
        seen.add(text)
        kept.append(
            {
                "id": f"pii{len(kept):05d}",
                "text": " ".join(text.split()),
                "labels": sorted(set(labels)),
                "category": "credential" if "credential" in categories else "strong-pii",
            }
        )
        if len(kept) >= args.limit:
            break

    payload = {
        "status": "ok" if kept else "empty",
        "dataset": used,
        "scanned": scanned,
        "kept": len(kept),
        "droppedMixed": dropped_mixed,
        "labelCensus": dict(sorted(label_census.items(), key=lambda kv: -kv[1])[:40]),
        "errors": errors,
        "rows": kept,
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
