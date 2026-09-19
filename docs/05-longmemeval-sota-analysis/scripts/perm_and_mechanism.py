"""Distribution-free checks for the same-instant A/B.

Welch's t-test on n=3 per arm is underpowered and its p-values are fragile, so we
add (a) an exact permutation test on the mean difference and (b) a within-arm
correlation between abstention and accuracy, which is the mechanism the patch is
supposed to act on.
"""

import itertools
import statistics as st

RUNS = [
    # (arm, run_id, overall, abst)
    ("control",   287180, 77.80, 17.60),
    ("control",   290087, 78.60, 16.60),
    ("control",   293014, 76.20, 18.80),
    ("treatment", 298345, 78.20, 15.00),
    ("treatment", 302150, 78.20, 15.40),
    ("treatment", 307358, 78.40, 15.00),
]


def mean(xs):
    return sum(xs) / len(xs)


def exact_permutation(values, labels, stat):
    """Two-sided exact permutation p-value over all C(6,3) arm assignments."""
    n = len(values)
    k = labels.count("treatment")
    observed = stat(values, labels)
    counts = {"ge": 0, "total": 0}
    for combo in itertools.combinations(range(n), k):
        trial = ["treatment" if i in combo else "control" for i in range(n)]
        s = stat(values, trial)
        counts["total"] += 1
        if abs(s) >= abs(observed) - 1e-12:
            counts["ge"] += 1
    return observed, counts["ge"] / counts["total"]


def mean_diff(values, labels):
    t = [v for v, l in zip(values, labels) if l == "treatment"]
    c = [v for v, l in zip(values, labels) if l == "control"]
    return mean(t) - mean(c)


def min_diff(values, labels):
    """Worst-run statistic: the quantity the patch is claimed to lift."""
    t = [v for v, l in zip(values, labels) if l == "treatment"]
    c = [v for v, l in zip(values, labels) if l == "control"]
    return min(t) - min(c)


def range_ratio(values, labels):
    """Negative when the treatment arm is tighter than the control arm."""
    t = [v for v, l in zip(values, labels) if l == "treatment"]
    c = [v for v, l in zip(values, labels) if l == "control"]
    return (max(t) - min(t)) - (max(c) - min(c))


overall = [r[2] for r in RUNS]
abst = [r[3] for r in RUNS]
labels = [r[0] for r in RUNS]

print("== exact permutation tests (C(6,3) = 20 assignments, two-sided) ==")
for name, vals, fn in [
    ("overall mean", overall, mean_diff),
    ("overall worst run", overall, min_diff),
    ("overall range (treat-ctrl)", overall, range_ratio),
    ("abstention mean", abst, mean_diff),
    ("abstention range", abst, range_ratio),
]:
    obs, p = exact_permutation(vals, labels, fn)
    print(f"  {name:<28} observed={obs:+.3f}  p={p:.4f}")

print()
print("== mechanism: does abstention drive accuracy *within* an arm? ==")


def pearson(xs, ys):
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


for arm in ("control", "treatment"):
    a = [r[3] for r in RUNS if r[0] == arm]
    o = [r[2] for r in RUNS if r[0] == arm]
    print(f"  {arm:<10} abst={a}  overall={o}  r={pearson(a, o):+.3f}")

a_all = [r[3] for r in RUNS]
o_all = [r[2] for r in RUNS]
print(f"  pooled     r={pearson(a_all, o_all):+.3f}   (n=6)")

print()
print("== how much of the control arm's spread is explained by abstention? ==")
c_abst = [r[3] for r in RUNS if r[0] == "control"]
c_over = [r[2] for r in RUNS if r[0] == "control"]
r_c = pearson(c_abst, c_over)
print(f"  control: std(overall)={st.stdev(c_over):.3f}pp  r^2={r_c ** 2:.3f}"
      f"  -> abstention explains {100 * r_c ** 2:.1f}% of the run-to-run variance")
t_abst = [r[3] for r in RUNS if r[0] == "treatment"]
t_over = [r[2] for r in RUNS if r[0] == "treatment"]
r_t = pearson(t_abst, t_over)
print(f"  treatment: std(overall)={st.stdev(t_over):.3f}pp  r^2={r_t ** 2:.3f}")
