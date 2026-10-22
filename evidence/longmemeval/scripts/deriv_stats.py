"""Power calibration and difference-in-differences for the derivation-prompt A/B.

The target set is only 24 questions. That caps what ANY test can resolve, so the
p-values must be read against the design's minimum attainable p, not against .05.
"""
import json, re, math, itertools
from pathlib import Path
exec(open("deriv_ab_analysis.py").read().split('print("== run-level')[0])

MR = [q for q in qids if DATA[CNAMES[0]][q]["capability"] == "MR"]
DER = [q for q in MR if DERIV.search(DATA[CNAMES[0]][q]["question"])]
NON = [q for q in MR if q not in set(DER)]

def mean(xs): return sum(xs)/len(xs) if xs else 0.0
def sd(xs):
    m = mean(xs); return (sum((x-m)**2 for x in xs)/(len(xs)-1))**0.5 if len(xs) > 1 else 0.0
def ncdf(x): return 0.5*(1+math.erf(x/math.sqrt(2)))

print("== 1. the design's floor: minimum attainable p at this target-set size ==")
print("   McNemar with 5 discordant questions: p_min = 2 * 2^-5 = 0.0625")
print("   -> p<0.05 is UNREACHABLE by McNemar here no matter how large the effect.")
print("   The abstention endpoint must therefore be tested on PER-QUESTION RATES.")
print()

# paired t on per-question abstention-rate difference (n=24)
d_abst = [sum(DATA[n][q]["abstained"] for n in CNAMES)/4
          - sum(DATA[n][q]["abstained"] for n in TNAMES)/4 for q in DER]
m = mean(d_abst); s = sd(d_abst); se = s/math.sqrt(len(d_abst))
t = m/se if se else 0.0
print("== 2. paired t on per-question abstention rate (n=24 questions) ==")
print(f"   mean reduction {m*100:+.2f}pp   SD {s*100:.2f}pp   SE {se*100:.2f}pp   t={t:+.3f}")
# exact permutation of the SIGN of each question's difference (paired, exchangeable)
obs = abs(mean(d_abst))
cnt = tot = 0
for signs in itertools.product([1, -1], repeat=len(d_abst)):
    tot += 1
    if abs(mean([sg*abs(v) for sg, v in zip(signs, d_abst)])) >= obs - 1e-12:
        cnt += 1
print(f"   exact sign-flip permutation p = {cnt/tot:.5f}   ({cnt}/{tot})")
print()

# 3. difference-in-differences: target set vs provably-untouched set within MR
print("== 3. difference-in-differences (cancels run-level drift) ==")
def paired_delta(q):
    s = DATA[CNAMES[0]][q]
    vc = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in CNAMES]
    vt = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in TNAMES]
    if all(v is not None for v in vc+vt):
        return sum(1.0*v for v in vt)/4 - sum(1.0*v for v in vc)/4
    return None
dD = [d for d in (paired_delta(q) for q in DER) if d is not None]
dN = [d for d in (paired_delta(q) for q in NON) if d is not None]
mD, mN = mean(dD), mean(dN)
sD, sN = sd(dD), sd(dN)
se_did = math.sqrt(sD**2/len(dD) + sN**2/len(dN))
t_did = (mD - mN)/se_did if se_did else 0.0
p_did = 2*(1-ncdf(abs(t_did)))
print(f"   target (derivable)  n={len(dD):3d}  delta {mD*100:+6.2f}pp  SD {sD*100:.1f}pp")
print(f"   control (non-deriv) n={len(dN):3d}  delta {mN*100:+6.2f}pp  SD {sN*100:.1f}pp")
print(f"   DiD estimate {100*(mD-mN):+.2f}pp   SE {100*se_did:.2f}pp   t={t_did:+.2f}   p={p_did:.4f}")
print()

# 4. per-question abstention DID (bigger n, all 121 questions available)
aD = [sum(DATA[n][q]["abstained"] for n in CNAMES)/4
      - sum(DATA[n][q]["abstained"] for n in TNAMES)/4 for q in DER]
aN = [sum(DATA[n][q]["abstained"] for n in CNAMES)/4
      - sum(DATA[n][q]["abstained"] for n in TNAMES)/4 for q in NON]
se_a = math.sqrt(sd(aD)**2/len(aD) + sd(aN)**2/len(aN))
t_a = (mean(aD)-mean(aN))/se_a if se_a else 0.0
print(f"== 4. abstention DiD (all {len(MR)} MR questions, no grading needed) ==")
print(f"   target  reduction {mean(aD)*100:+.2f}pp   control {mean(aN)*100:+.2f}pp")
print(f"   DiD {100*(mean(aD)-mean(aN)):+.2f}pp   SE {100*se_a:.2f}pp   t={t_a:+.2f}   "
      f"p={2*(1-ncdf(abs(t_a))):.5f}")
print()

# 5. power: how many runs would the target set need?
print("== 5. power: runs needed for the abstention endpoint ==")
sd_q = sd(aD)  # per-question SD of the abstention difference at 4 runs/arm
print(f"   per-question SD of the abstention difference (4 runs/arm) = {sd_q*100:.2f}pp")
print(f"   observed DiD = {100*(mean(aD)-mean(aN)):+.2f}pp")
for runs in (4, 6, 8, 12):
    # averaging over `runs` shrinks per-question noise by sqrt(4/runs)
    se_r = math.sqrt((sd_q*math.sqrt(4.0/runs))**2/len(aD) + (sd(aN)*math.sqrt(4.0/runs))**2/len(aN))
    mdd = 2.0 * se_r * 100
    print(f"   {runs:2d} runs/arm -> SE {100*se_r:.2f}pp   mean-detectable (80% power) {mdd:.2f}pp")
print()

# 6. run-level variance (the "three hits" stability read)
print("== 6. run-level stability ==")
fm = lambda r: r["ablation"]["featureMetrics"]
for label, names in (("control", CNAMES), ("treatment", TNAMES)):
    ov = [fm(REPORTS[n])["accuracy"]*100 for n in names]
    mr = [fm(REPORTS[n])["perCapability"]["MR"]["accuracy"]*100 for n in names]
    print(f"   {label:<10} overall {min(ov):.2f}-{max(ov):.2f} (sd {sd(ov):.2f})   "
          f"MR {min(mr):.2f}-{max(mr):.2f} (sd {sd(mr):.2f})")
print()
ov_c = [fm(REPORTS[n])["accuracy"]*100 for n in CNAMES]
ov_t = [fm(REPORTS[n])["accuracy"]*100 for n in TNAMES]
print(f"   overall separation: min(treatment)={min(ov_t):.2f}  vs  max(control)={max(ov_c):.2f}"
      f"   -> {'COMPLETE SEPARATION' if min(ov_t) > max(ov_c) else 'overlap'}")
