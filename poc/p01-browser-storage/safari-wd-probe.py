#!/usr/bin/env python3
"""Drive real Safari through safaridriver and read the probe result off the page.

## Why this file exists next to a Playwright runner

`run.mjs` measures Chromium and WebKit through Playwright's own protocol. Neither is Safari:
Playwright ships a WebKit build with its own networking and storage plumbing, so a pass there
says "WebKit can do it", not "Safari can do it". The question G1 asks is specifically about
Safari's 252-open-handle ceiling, which is a property of *that* browser's file API surface and
of nothing else.

So this probe speaks WebDriver to the copy of Safari that ships with macOS. It is deliberately
small and dependency-free (urllib only) because the point is to find out whether the browser
cooperates, not to build a test framework.

## What it can and cannot answer

  can      does the SAH-pool VFS install in Safari, and does a batch of rows round-trip
  cannot   persistence across a browser restart -- one WebDriver session per run, and Safari's
           automation profile is not a persistent one. Persistence stays with the Playwright
           path, which relaunches the process.

If `safaridriver --enable` fails on the runner (it needs an admin authorisation and a login
session), the failure is recorded verbatim. A recorded refusal is an answer; a skipped step
that prints "ok" is not.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def call(method: str, url: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read().decode()
    return json.loads(body) if body else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="http://127.0.0.1:8000")
    parser.add_argument("--webdriver", default="http://127.0.0.1:4444")
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    result: dict = {
        "browser": "safari",
        "mechanism": "safaridriver",
        "origin": args.origin,
        "rows": args.rows,
        "ok": False,
    }

    session = None
    try:
        created = call(
            "POST",
            f"{args.webdriver}/session",
            {"capabilities": {"alwaysMatch": {"browserName": "safari"}}},
        )
        session = created["value"]["sessionId"]
        result["session"] = session

        url = f"{args.origin}/?autorun=1&rows={args.rows}"
        call("POST", f"{args.webdriver}/session/{session}/url", {"url": url})

        deadline = time.time() + args.timeout
        probe = None
        while time.time() < deadline:
            answer = call(
                "POST",
                f"{args.webdriver}/session/{session}/execute/sync",
                {"script": "return window.__probe || null;", "args": []},
            )
            probe = answer.get("value")
            if probe:
                break
            time.sleep(0.5)

        if probe is None:
            result["error"] = "the page never published window.__probe within the timeout"
        else:
            result["probe"] = probe
            result["ok"] = bool(probe.get("ok"))
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        result["error"] = f"HTTP {error.code} from safaridriver: {body[:800]}"
    except Exception as error:  # noqa: BLE001 -- the failure text is the measurement
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        if session:
            try:
                call("DELETE", f"{args.webdriver}/session/{session}")
            except Exception:  # noqa: BLE001
                pass
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)

    print(json.dumps(result, indent=2)[:2000])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
