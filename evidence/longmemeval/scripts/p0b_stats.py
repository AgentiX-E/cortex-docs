"""Significance tests for the P0-b same-instant A/B (4 control vs 3 treatment)."""
import itertools, math

def mean(xs): return sum(xs)/len(xs)

# run-level values (feature system accuracy, %)
IE = {"control": [89.33, 90.67, 89.33, 92.00], "treatment": [96.00, 95.33, 94.00]}
OV = {"control": [77.60, 79.00, 77.20, 78.20], "treatment": [80.20, 79.80, 79.60]}
KU = {"control": [75.00, 75.00, 75.00, 73.61], "treatment": [79.17, 76.39, 79.17]}
MR = {"control": [65.29, 68.60, 65.29, 66.94], "treatment": [62.81, 66.12, 65.29]}
TR = {"control": [71.65, 72.44, 70.87, 70.08], "treatment": [74.02, 71.65, 72.44]}

def perm_p(values_c, values_t):
    """Exact permutation p-value for the mean difference (all C(n,k) splits)."""
    allv = values_c + values_t
    k = len(values_t)
    obs = mean(values_t) - mean(values_c)
    cnt = 0; tot = 0
    for combo in itertools.combinations(range(len(allv)), k):
        t = [allv[i] for i in combo]
        c = [allv[i] for i in range(len(allv)) if i not in combo]
        s = mean(t) - mean(c)
        tot += 1
        if abs(s) >= abs(obs) - 1e-9:
            cnt += 1
    return obs, cnt/tot

print("== exact permutation tests on run-level accuracy (C(7,3)=35 splits) ==")
for name, d in (("IE", IE), ("Overall", OV), ("KU", KU), ("MR", MR), ("TR", TR)):
    obs, p = perm_p(d["control"], d["treatment"])
    print(f"  {name:<8} control {[f'{x:.2f}' for x in d['control']]}  "
          f"treatment {[f'{x:.2f}' for x in d['treatment']]}  "
          f"delta {obs:+.2f}pp  p={p:.4f}")

# pooled two-proportion test on preference abstention
print()
print("== preference abstention: pooled two-proportion test ==")
# control: 4 runs x 29 questions = 116 obs, 22.41% abstained -> count
c_abst = round(0.2241 * 116)  # 26
# treatment: 3 runs x 29 = 87 obs, 0 abstained
t_abst = 0
n1, n2 = 116, 87
p1 = c_abst/n1; p2 = t_abst/n2
pbar = (c_abst + t_abst)/(n1 + n2)
se = math.sqrt(pbar*(1-pbar)*(1/n1 + 1/n2))
z = (p1 - p2)/se
# two-sided p
from math import erf
def norm_cdf(x): return 0.5*(1+erf(x/math.sqrt(2)))
p = 2*(1-norm_cdf(abs(z)))
print(f"  control {c_abst}/{n1} = {p1*100:.2f}%   treatment {t_abst}/{n2} = {p2*100:.2f}%")
print(f"  z = {z:.3f}   two-sided p = {p:.3e}")
# Wilson CI for treatment 0/87
import math
def wilson(k, n, z=1.96):
    if n == 0: return (0,0)
    p = k/n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n))/denom
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/denom
    return (max(0,center-half), min(1,center+half))
lo, hi = wilson(t_abst, n2)
print(f"  treatment Wilson 95% CI: [{lo*100:.2f}%, {hi*100:.2f}%]")
