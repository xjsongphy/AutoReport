"""Part 5&6: N(w) impurity profile + 1/C2 linear fit, VD extraction (corrected)."""
import numpy as np, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from analysis_constants import *

PROC_DIR = os.path.dirname(__file__)

for d_label in ['D_1','D_2','D_3','D_4','D_5']:
    fpath = os.path.join(PROC_DIR, f'{d_label}_CV_processed.csv')
    data = np.loadtxt(fpath, delimiter=',', skiprows=1)
    Vb, C_j, invC2, w_cm = data[:,0], data[:,3], data[:,4], data[:,5]
    V_R = -Vb

    # N(w) via central difference of 1/C2
    Nw = np.full(len(Vb), np.nan)
    for i in range(1, len(Vb)-1):
        d_invC2 = (invC2[i+1]-invC2[i-1])/(V_R[i+1]-V_R[i-1])
        if d_invC2 > 1e-30:
            Nw[i] = compute_N_from_invC2_slope(d_invC2)

    # Full range fit
    mf = V_R >= 0.2
    cf = np.polyfit(V_R[mf], invC2[mf], 1)
    ND_f = compute_N_from_invC2_slope(cf[0])
    VD_f = compute_VD_from_intercept(cf[0], cf[1])
    ff = np.polyval(cf, V_R[mf])
    R2_f = 1-np.sum((invC2[mf]-ff)**2)/np.sum((invC2[mf]-np.mean(invC2[mf]))**2)

    # Depletion fit 2-10V
    md = (V_R>=2.0)&(V_R<=10.0)
    if np.sum(md)>=5:
        cd = np.polyfit(V_R[md], invC2[md], 1)
        ND_d = compute_N_from_invC2_slope(cd[0])
        VD_d = compute_VD_from_intercept(cd[0], cd[1])
        fd = np.polyval(cd, V_R[md])
        R2_d = 1-np.sum((invC2[md]-fd)**2)/np.sum((invC2[md]-np.mean(invC2[md]))**2)
    else:
        cd=[np.nan,np.nan]; ND_d=VD_d=R2_d=np.nan

    with open(os.path.join(PROC_DIR, f'{d_label}_Nw_profile.csv'), 'w', encoding='utf-8') as f:
        f.write("Vb_set(V),V_R(V),C_j(pF),1/C2(pF-2),w(cm),N(w)(cm-3)\n")
        for i in range(len(Vb)):
            ns = f"{Nw[i]:.6e}" if not np.isnan(Nw[i]) else "nan"
            f.write(f"{Vb[i]:.4f},{V_R[i]:.4f},{C_j[i]:.4f},{invC2[i]:.6e},{w_cm[i]:.6e},{ns}\n")

    print(f"\n=== {d_label} ===")
    print(f"  Full:  slope={cf[0]:.4e}/pF2/V, ND={ND_f:.3e}/cm3, VD={VD_f:.3f}V, R2={R2_f:.4f}")
    if not np.isnan(R2_d):
        print(f"  2-10V: slope={cd[0]:.4e}/pF2/V, ND={ND_d:.3e}/cm3, VD={VD_d:.3f}V, R2={R2_d:.4f}")
    vv = ~np.isnan(Nw)
    if np.sum(vv)>0:
        print(f"  N(w): {np.min(Nw[vv]):.3e}~{np.max(Nw[vv]):.3e}/cm3, w: {np.min(w_cm):.4e}~{np.max(w_cm):.4e}cm")

print("\n"+"="*60)
print("=== DIODE QUALIFICATION ===")
print("Criteria: R2(2-10V)>0.99, VD=0.3~1.0V, C monotonic decrease")
for d_label in ['D_1','D_2','D_3','D_4','D_5']:
    d = np.loadtxt(os.path.join(PROC_DIR,f'{d_label}_CV_processed.csv'), delimiter=',', skiprows=1)
    C_j, invC2, V_R = d[:,3], d[:,4], -d[:,0]
    md = (V_R>=2.0)&(V_R<=10.0)
    if np.sum(md)>=5:
        cd = np.polyfit(V_R[md], invC2[md], 1)
        ND_d = compute_N_from_invC2_slope(cd[0])
        VD_d = compute_VD_from_intercept(cd[0], cd[1])
        fd = np.polyval(cd, V_R[md])
        R2_d = 1-np.sum((invC2[md]-fd)**2)/np.sum((invC2[md]-np.mean(invC2[md]))**2)
        C_mono = np.all(np.diff(C_j)<0)
        qual = (R2_d>0.99 and 0.3<VD_d<1.0 and C_mono)
        tag = "QUALIFIED" if qual else "FAILED"
        print(f"  {d_label}: R2={R2_d:.4f}, VD={VD_d:.3f}V, ND={ND_d:.3e}/cm3, mono={C_mono} -> {tag}")
        if not qual:
            reasons=[]
            if R2_d<=0.99: reasons.append(f"R2={R2_d:.4f}<=0.99")
            if not(0.3<VD_d<1.0): reasons.append(f"VD={VD_d:.3f}V")
            if not C_mono: reasons.append("C not monotonic")
            print(f"       Reasons: {', '.join(reasons)}")
