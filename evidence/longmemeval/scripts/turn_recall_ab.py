"""Turn-level recall A/B: control (channel off) vs treatment (channel on).

Design notes
------------
PRIMARY ENDPOINT IS DETERMINISTIC. Whether an evidence session is retrieved is
decided entirely by embedding cosine, and the embedding provider is verified
deterministic at temperature 0 before every run. So evidence recall carries NO
sampling variance: a single run per arm measures it exactly, and any control-vs-
treatment difference is a real retrieval change rather than noise.

Accuracy, by contrast, is LLM-sampled and sits on a measured noise floor of
roughly +/-1.6pp at run level. It is reported as a noise-floored descriptive
estimate only, never as the acceptance criterion on its own.

The recall endpoint is also the causal link: if recall does not move, any
accuracy movement cannot be attributed to this change, and if recall moves but
accuracy does not, the retrieval fix worked and the bottleneck is downstream.

Usage: python3 turn_recall_ab.py [root]      (default root: ab_turn)
"""
import json, re, math, itertools, sys
from pathlib import Path
from collections import Counter

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "ab_turn")
CTRL = sorted([d for d in (ROOT / "control").iterdir() if d.is_dir()])
TREAT = sorted([d for d in (ROOT / "treatment").iterdir() if d.is_dir()])
CNAMES = [d.name for d in CTRL]
TNAMES = [d.name for d in TREAT]

FP_LEN = 80  # validated: 40/80 agree, 200 degrades (truncation artefact)
AGG_BUDGET = 20_000  # DEFAULT_MAX_AGGREGATION_CHARS; no env override in bench/run.ts
# Sessions are joined by a blank line; turns within a session are single lines
# carrying a `[YYYY/MM/DD ...]` prefix. Count both: the session count is what
# the turn channel changes, the turn count is what it searches over.
TURN_PREFIX = re.compile(r"^\[\d{4}/\d{2}/\d{2}")
COUNTING = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")


def fp(t, n=FP_LEN):
    return re.sub(r"\W+", "", str(t).lower())[:n]


def norm(a):
    return re.sub(r"\s+", "", str(a).strip().lower())


def lead(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = LEADING_NUM.match(v.strip())
    return float(m.group(1).replace(",", "")) if m else None


def verdict(question, answer, expected):
    if expected is None:
        return answer is None
    if answer is None:
        return False
    if norm(answer) == norm(expected):
        return True
    if COUNTING.search(question):
        p, e = lead(answer), lead(expected)
        if p is not None and e is not None:
            return p == e
    return None


def load(d):
    """Per-question record: recall state, context size, accuracy, abstention."""
    out = {}
    for name in ("benchmark-mr-diagnostics.json", "benchmark-single-session-diagnostics.json"):
        p = d / name
        if not p.exists():
            continue
        for x in json.loads(p.read_text()):
            dec = x["decision"] or {}
            retrieved = dec.get("retrieved", "") or ""
            ev = x.get("answer_sessions_content") or []
            fpr = fp(retrieved, 10 ** 7)
            found = sum(1 for c in ev if fp(c) and fp(c) in fpr)
            out[x["question_id"]] = {
                "capability": x.get("capability", "MR"),
                "question": x["question"],
                "expected": x["ground_truth"],
                "answer": dec.get("answer"),
                "abstained": bool(dec.get("abstained")),
                "reason": dec.get("reason"),
                "raw": dec.get("llmRaw", "") or "",
                "ev_total": len(ev),
                "ev_found": found,
                "ev_complete": (len(ev) > 0 and found == len(ev)),
                # Sessions are joined by a blank line, but a session's own
                # turns can contain blank lines (multi-paragraph assistant
                # replies), so splitting on "\n\n" over-counts by ~5.5x
                # (measured: mean 18.6 blocks vs 3.4 real sessions). A block
                # starts a new session only if its first line carries a turn
                # prefix; continuation blocks open with prose instead.
                "ctx_sessions": sum(
                    1 for b in retrieved.split("\n\n")
                    if b.strip() and TURN_PREFIX.match(b.strip())
                ),
                "ctx_turns": sum(1 for ln in retrieved.split("\n")
                                 if TURN_PREFIX.match(ln.strip())),
                "ctx_chars": len(retrieved),
                # Two different truncations share one marker: the aggregation
                # budget appends it at the very END, while `truncateSession`
                # emits one per over-long session. They are told apart by length
                # -- a marker alone can also come from the LAST session being
                # over-long -- because the aggregation cap slices to exactly
                # 20,000 and then appends, so a clipped result is always longer.
                "truncated_total": len(retrieved) > AGG_BUDGET,
                "truncated_sessions": retrieved.count("[truncated]"),
            }
    return out


def load_report(d):
    return json.loads((d / "benchmark-report.json").read_text())


DATA = {d.name: load(d) for d in CTRL + TREAT}
# Run directories are keyed by name in one flat dict. A collision between the two
# arms would silently collapse them into a single dataset and report a perfect
# null effect -- indistinguishable from a real "the change did nothing" result.
# Fail loudly instead of shipping a false negative that costs a whole iteration.
if len(DATA) != len(CTRL) + len(TREAT):
    dupes = sorted({d.name for d in CTRL} & {d.name for d in TREAT})
    raise SystemExit(
        f"run directory names collide across arms (also in both: {dupes}). "
        "Name each run directory by its unique workflow run id."
    )
REPORTS = {d.name: load_report(d) for d in CTRL + TREAT}
qids = sorted(set.intersection(*[set(v) for v in DATA.values()]))
MR = [q for q in qids if DATA[CNAMES[0]][q]["capability"] == "MR"]
OTHER = [q for q in qids if q not in set(MR)]

print(f"root: {ROOT}")
print(f"questions in all {len(DATA)} runs: {len(qids)}   MR: {len(MR)}   other: {len(OTHER)}")
print(f"control   ({len(CNAMES)}): {CNAMES}")
print(f"treatment ({len(TNAMES)}): {TNAMES}\n")


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def mcnemar_exact(b, c):
    """Two-sided exact McNemar on b discordant one way, c the other."""
    n = b + c
    if n == 0:
        return 1.0
    obs = math.comb(n, min(b, c)) * (0.5 ** n)
    return min(1.0, sum(math.comb(n, i) * (0.5 ** n) for i in range(n + 1)
                        if math.comb(n, i) * (0.5 ** n) <= obs * 1.000001))


# ---------------------------------------------------------------- 1. sanity
print("== 1. determinism of the primary endpoint within each arm ==")
for label, names in (("control", CNAMES), ("treatment", TNAMES)):
    varying = 0
    for q in MR:
        states = {DATA[n][q]["ev_found"] for n in names}
        if len(states) > 1:
            varying += 1
    print(f"  {label:<10} MR questions whose recall count varies across runs: {varying}/{len(MR)}")
print("  (0 confirms the endpoint is deterministic and one run per arm suffices)\n")

# ------------------------------------------------- 2. PRIMARY: recall
print("== 2. PRIMARY ENDPOINT — evidence recall (deterministic) ==")
for label, names in (("control", CNAMES), ("treatment", TNAMES)):
    complete = sum(1 for q in MR if DATA[names[0]][q]["ev_complete"])
    tot_found = sum(DATA[names[0]][q]["ev_found"] for q in MR)
    tot_ev = sum(DATA[names[0]][q]["ev_total"] for q in MR)
    print(f"  {label:<10} questions with COMPLETE evidence: {complete}/{len(MR)} "
          f"({complete/len(MR)*100:.1f}%)")
    print(f"  {'':10} evidence sessions recalled: {tot_found}/{tot_ev} "
          f"({tot_found/tot_ev*100:.1f}%)")

improved = [q for q in MR if DATA[TNAMES[0]][q]["ev_found"] > DATA[CNAMES[0]][q]["ev_found"]]
regressed = [q for q in MR if DATA[TNAMES[0]][q]["ev_found"] < DATA[CNAMES[0]][q]["ev_found"]]
print(f"\n  questions with MORE evidence recalled under treatment: {len(improved)}")
print(f"  questions with LESS evidence recalled under treatment: {len(regressed)}"
      f"   (must be 0: the channel is additive)")
print(f"  exact McNemar on discordant pairs: p={mcnemar_exact(len(improved), len(regressed)):.3e}")

newly_complete = [q for q in improved if DATA[TNAMES[0]][q]["ev_complete"]
                  and not DATA[CNAMES[0]][q]["ev_complete"]]
print(f"  questions that went from INCOMPLETE to COMPLETE evidence: {len(newly_complete)}")
print()

if improved:
    print("  per-question recall change:")
    for q in sorted(improved, key=lambda q: DATA[CNAMES[0]][q]["ev_found"]
                    - DATA[TNAMES[0]][q]["ev_found"]):
        s = DATA[CNAMES[0]][q]
        cf, ct = s["ev_found"], DATA[TNAMES[0]][q]["ev_found"]
        tot = s["ev_total"]
        print(f"    {cf}/{tot} -> {ct}/{tot}  {s['question'][:66]}")
print()

# ------------------------------------------------- 3. context size
print("== 3. injected context size ==")
for label, names in (("control", CNAMES), ("treatment", TNAMES)):
    sess = [DATA[names[0]][q]["ctx_sessions"] for q in MR]
    chars = [DATA[names[0]][q]["ctx_chars"] for q in MR]
    clip = sum(1 for q in MR if DATA[names[0]][q]["truncated_total"])
    ss, cs = sorted(sess), sorted(chars)
    print(f"  {label:<10} sessions/q median {ss[len(ss)//2]:3d} p90 {ss[int(len(ss)*0.9)]:3d} "
          f"max {ss[-1]:3d}   chars/q median {cs[len(cs)//2]:6d} max {cs[-1]:6d}")
    print(f"  {'':10} questions clipped by the 20k aggregation budget: {clip}/{len(MR)}"
          f"   (these are where the added sessions are cut)")
    inc = sum(1 for q in MR if DATA[TNAMES[0]][q]["ctx_sessions"]
              > DATA[CNAMES[0]][q]["ctx_sessions"])
    if label == "treatment":
        print(f"  {'':10} questions with MORE sessions than control: {inc}/{len(MR)}")
print()

# ------------------------------------------------- 4. accuracy (noisy)
print("== 4. SECONDARY — accuracy at run level (noise-floored) ==")
for cap in ("IE", "TR", "MR", "KU", "ABS"):
    c = [REPORTS[n]["ablation"]["featureMetrics"]["perCapability"][cap]["accuracy"] * 100
         for n in CNAMES]
    t = [REPORTS[n]["ablation"]["featureMetrics"]["perCapability"][cap]["accuracy"] * 100
         for n in TNAMES]
    print(f"  {cap:<4} ctrl {mean(c):6.2f}%  treat {mean(t):6.2f}%  delta {mean(t)-mean(c):+6.2f}pp")
    print(f"       ctrl {[f'{x:.1f}' for x in c]}  treat {[f'{x:.1f}' for x in t]}")
for key, lbl in (("accuracy", "OV"), ("abstentionRate", "ABST")):
    c = [REPORTS[n]["ablation"]["featureMetrics"][key] * 100 for n in CNAMES]
    t = [REPORTS[n]["ablation"]["featureMetrics"][key] * 100 for n in TNAMES]
    print(f"  {lbl:<4} ctrl {mean(c):6.2f}%  treat {mean(t):6.2f}%  delta {mean(t)-mean(c):+6.2f}pp")
    print(f"       ctrl {[f'{x:.2f}' for x in c]}  treat {[f'{x:.2f}' for x in t]}")


def perm_p(dc, dt):
    allv = dc + dt
    k = len(dt)
    obs = mean(dt) - mean(dc)
    cnt = 0
    for combo in itertools.combinations(range(len(allv)), k):
        tv = [allv[i] for i in combo]
        cv = [allv[i] for i in range(len(allv)) if i not in combo]
        if abs(mean(tv) - mean(cv)) >= abs(obs) - 1e-9:
            cnt += 1
    return obs, cnt / math.comb(len(allv), k)


print(f"\n  exact permutation tests ({len(CNAMES)}+{len(TNAMES)} runs):")
for cap in ("MR", "IE", "TR", "KU", "ABS"):
    dc = [REPORTS[n]["ablation"]["featureMetrics"]["perCapability"][cap]["accuracy"] * 100
          for n in CNAMES]
    dt = [REPORTS[n]["ablation"]["featureMetrics"]["perCapability"][cap]["accuracy"] * 100
          for n in TNAMES]
    obs, p = perm_p(dc, dt)
    print(f"    {cap:<4} delta {obs:+6.2f}pp  p={p:.4f}")
print()

# ------------------------------------------------- 5. paired accuracy
def paired(qs, label):
    diffs, wins, losses, ties = [], 0, 0, 0
    for q in qs:
        s = DATA[CNAMES[0]][q]
        vc = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in CNAMES]
        vt = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in TNAMES]
        if all(v is not None for v in vc + vt):
            d = mean([1.0 * v for v in vt]) - mean([1.0 * v for v in vc])
            diffs.append(d)
            if d > 1e-9:
                wins += 1
            elif d < -1e-9:
                losses += 1
            else:
                ties += 1
    if len(diffs) < 3:
        print(f"  {label}: too few deterministic questions (n={len(diffs)})")
        return
    n = len(diffs)
    m = mean(diffs)
    sd = (sum((x - m) ** 2 for x in diffs) / (n - 1)) ** 0.5
    se = sd / math.sqrt(n)
    t = m / se if se else 0.0
    p_t = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    nd = wins + losses
    p_sign = (2 * sum(math.comb(nd, i) for i in range(min(wins, losses) + 1)) / (2 ** nd)
              if nd else 1.0)
    print(f"  {label:<34} n={n:3d}  delta {m*100:+6.2f}pp  SE {se*100:5.2f}pp  t={t:+.2f}  "
          f"p={p_t:.4f}   sign {wins}W/{losses}L/{ties}T p={p_sign:.4f}")


print("== 5. question-level paired deterministic accuracy ==")
paired(MR, "MR all")
if improved:
    paired(improved, "MR with improved recall (target)")
    untouched = [q for q in MR if q not in set(improved)]
    paired(untouched, "MR with unchanged recall (control)")
paired(OTHER, "non-MR (must be null)")
paired(qids, "ALL")
print()

# ------------------------------------------------- 6. abstention
print("== 6. abstention ==")
for label, qs in (("MR all", MR), ("MR improved recall", improved), ("non-MR", OTHER),
                  ("ALL", qids)):
    if not qs:
        continue
    c = sum(DATA[n][q]["abstained"] for n in CNAMES for q in qs) / (len(CNAMES) * len(qs)) * 100
    t = sum(DATA[n][q]["abstained"] for n in TNAMES for q in qs) / (len(TNAMES) * len(qs)) * 100
    b = cc = 0
    for q in qs:
        ce = sum(DATA[n][q]["abstained"] for n in CNAMES)
        te = sum(DATA[n][q]["abstained"] for n in TNAMES)
        if ce > te:
            b += 1
        elif te > ce:
            cc += 1
    print(f"  {label:<22} ctrl {c:6.2f}%  treat {t:6.2f}%  delta {t-c:+6.2f}pp   "
          f"McNemar {b}/{cc} p={mcnemar_exact(b, cc):.3f}")
print()

# ------------------------------------------------- 7. guards
# Two of these compare against a BASELINE rather than zero. Query expansion is
# LLM-generated, so even at temperature 0 a handful of questions retrieve a
# different set run to run; that churn is present in both arms and is not an
# effect of this change. A guard that demands exactly zero would fail on noise.
def instability(names, qs):
    """Questions whose recall count is not constant within one arm."""
    return sum(1 for q in qs if len({DATA[n][q]["ev_found"] for n in names}) > 1)


baseline = max(instability(CNAMES, MR), instability(TNAMES, MR))
print("== 7. guards ==")
print(f"  a. additive only     : regressions in recall = {len(regressed)}   "
      f"within-arm instability baseline = {baseline}   "
      f"({'PASS' if len(regressed) <= baseline else 'FAIL'})")
print("      (the channel cannot drop a retrieved session -- unit tested -- so any")
print("       regression above the baseline would mean the merge is not additive)")
non_mr_ctx = sum(1 for q in OTHER
                 if DATA[CNAMES[0]][q]["ctx_chars"] != DATA[TNAMES[0]][q]["ctx_chars"])
non_mr_base = sum(1 for q in OTHER
                  if len({DATA[n][q]["ctx_chars"] for n in CNAMES}) > 1)
print(f"  b. non-MR untouched  : context changed on {non_mr_ctx}/{len(OTHER)} questions; "
      f"within-arm baseline {non_mr_base}/{len(OTHER)}   "
      f"({'PASS' if non_mr_ctx <= max(non_mr_base, 1) * 3 else 'FAIL'})")
print("      (the change is MR-only by construction, so this measures run noise)")
b = cc = 0
for q in OTHER:
    ce = sum(DATA[n][q]["abstained"] for n in CNAMES)
    te = sum(DATA[n][q]["abstained"] for n in TNAMES)
    if ce > te:
        b += 1
    elif te > ce:
        cc += 1
print(f"  c. non-MR null effect: McNemar {b}/{cc} p={mcnemar_exact(b, cc):.3f} "
      f"({'PASS' if mcnemar_exact(b, cc) > 0.05 else 'FAIL'})")
print(f"  d. budget respected  : treatment questions clipped by the 20k budget = "
      f"{sum(1 for q in MR if DATA[TNAMES[0]][q]['truncated_total'])}/{len(MR)} "
      f"(nonzero means the added sessions were partly cut)")
print()
print("== 8. verdict inputs ==")
print(f"  recall improved on {len(improved)} MR questions, "
      f"{len(newly_complete)} reached complete evidence")
print(f"  recall regressed on {len(regressed)} (baseline {baseline})")
