"""Deep audit: what does deterministic aggregation actually recover on MR?

The plan assumed "sum the enumerated values" fixes the 70% arithmetic errors.
Before coding, measure exactly which error modes a deterministic aggregation can
fix on the real MR raw outputs, and which it would break (dedup, missing values).
"""
import json, re
from pathlib import Path

RUN = Path("ab_p0b/treatment/run_33746098162/benchmark-mr-diagnostics.json")
rows = json.loads(RUN.read_text())

COUNT = re.compile(r"\b(how many|number of|count)\b", re.I)
SUM = re.compile(r"\b(how much|total (money|cost|amount)|in total)\b", re.I)
DUR = re.compile(r"\bhow many (hours|days|weeks|months|minutes|years)\b", re.I)
LEADING_NUM = re.compile(r"^[^\d$]*(\$?\s*\d[\d,]*(?:\.\d+)?)")
NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)")

def norm(a):
    return re.sub(r"\s+", " ", str(a).strip().lower())

def bullets(raw):
    out = []
    for line in raw.split("\n"):
        s = line.strip()
        if re.match(r"^[-*•]\s", s):
            out.append(re.sub(r"^[-*•]\s*", "", s))
    return out

def lead_number(s):
    # leading number after optional $ and leading words like "about", "around"
    m = LEADING_NUM.search(s)
    if not m:
        return None
    return float(m.group(1).replace("$","").replace(",",""))

def item_label(b):
    # strip the value/action/date columns; keep the item noun for dedup
    # drop leading <...> and trailing | ... |
    parts = b.split("|")
    return parts[0].strip().strip("<>").strip()

def gt_num(s):
    m = NUM.search(str(s))
    return float(m.group(1).replace(",","")) if m else None

# ---- classify errors ----
stats = {"count": {"n":0, "model_right":0, "det_right":0, "det_wrong_model_right":0,
                   "det_right_model_wrong":0, "both_wrong":0, "dup":0, "no_bullets":0},
         "sum": {"n":0, "model_right":0, "det_right":0, "det_wrong_model_right":0,
                 "det_right_model_wrong":0, "both_wrong":0, "dup":0, "no_val":0, "no_bullets":0}}

for x in rows:
    dec = x["decision"] or {}
    raw = dec.get("llmRaw") or ""
    q = x["question"]
    gt = x["ground_truth"]
    model = dec.get("answer")
    is_count = bool(COUNT.search(q)) and not DUR.search(q)
    is_sum = bool(SUM.search(q)) or bool(DUR.search(q))
    key = "count" if is_count else ("sum" if is_sum else None)
    if key is None:
        continue
    s = stats[key]
    s["n"] += 1
    gtn = gt_num(gt)
    # model correctness: normalized equality (numeric if numeric GT)
    model_right = False
    if gtn is not None:
        mn = gt_num(model) if model is not None else None
        model_right = (mn == gtn)
    else:
        model_right = norm(model) == norm(gt)
    bs = bullets(raw)
    if not bs:
        s["no_bullets"] += 1
        continue
    if key == "count":
        # deterministic COUNT = distinct item labels (dedup by label)
        labels = [item_label(b) for b in bs]
        has_dup = len(labels) != len(set(labels))
        if has_dup:
            s["dup"] += 1
        det = len(set(labels))
        det_right = (det == gtn)
    else:
        # deterministic SUM = sum of leading numbers (dedup'd by label)
        pairs = []
        seen = set()
        has_dup = False
        no_val = 0
        for b in bs:
            v = lead_number(b)
            if v is None:
                no_val += 1
                continue
            lab = item_label(b)
            if lab in seen:
                has_dup = True
                continue
            seen.add(lab)
            pairs.append(v)
        if has_dup:
            s["dup"] += 1
        if no_val > 0:
            s["no_val"] += 1
        det = sum(pairs) if pairs else None
        det_right = (det == gtn) if det is not None else False
    # tally
    if model_right:
        s["model_right"] += 1
    if det_right:
        s["det_right"] += 1
    if det_right and not model_right:
        s["det_right_model_wrong"] += 1
    if model_right and not det_right:
        s["det_wrong_model_right"] += 1
    if not det_right and not model_right:
        s["both_wrong"] += 1

for k, s in stats.items():
    n = s["n"]
    print(f"== {k} (n={n}) ==")
    print(f"  model correct: {s['model_right']}/{n} = {s['model_right']/n*100:.1f}%")
    print(f"  deterministic correct: {s['det_right']}/{n} = {s['det_right']/n*100:.1f}%")
    print(f"  det fixes (det right, model wrong): {s['det_right_model_wrong']}")
    print(f"  det breaks (det wrong, model right): {s['det_wrong_model_right']}")
    print(f"  both wrong: {s['both_wrong']}")
    print(f"  rows with duplicate bullets: {s['dup']}")
    print(f"  rows with a bullet lacking a value: {s.get('no_val',0)}")
    print(f"  rows with no bullets: {s['no_bullets']}")
    print(f"  NET gain (fixes - breaks): {s['det_right_model_wrong'] - s['det_wrong_model_right']}")
    print()
