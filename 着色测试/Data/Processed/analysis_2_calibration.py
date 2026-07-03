"""Part 2: Fixed capacitor calibration — verify V_out ∝ C_x, compute sensitivity k."""
import numpy as np
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from analysis_constants import *

# From Data.txt: C (pF), V (μV), Phi (deg)
cal_data = [
    (20, 27.181, -163.22),
    (40, 52.32,  -163.03),
    (60, 74.11,  -162.98),
    (80, 99.80,  -162.96),
    (100,123.80, -162.96),
]

C_vals = np.array([d[0] for d in cal_data])
V_vals = np.array([d[1] for d in cal_data]) * 1e-6  # μV → V
phi_vals = np.array([d[2] for d in cal_data])

# Linear fit: V = k * C + b
coeffs = np.polyfit(C_vals, V_vals, 1)
k, b = coeffs  # k in V/pF
k_uV_per_pF = k * 1e6  # μV/pF

# R²
V_fit = np.polyval(coeffs, C_vals)
SS_res = np.sum((V_vals - V_fit)**2)
SS_tot = np.sum((V_vals - np.mean(V_vals))**2)
R2 = 1 - SS_res / SS_tot

# Theoretical: from v_i ≈ (C_x/C0) * v(t)
# k_theory = V_s / C0 = 49.47e-3 / 5000 = 9.894e-6 V/pF
k_theory = V_s / C0

# Also compute using amplitude:
# R_1ω = (C_x/C0) * V_s
# Verify with each point
C_predicted = C0 * V_vals / V_s  # what C would be without stray

lines = [
    "C_nominal(pF),V_out(μV),V_out(V),Phi(deg),C_predicted(pF),C_pred-C_nom(pF)",
]
for i in range(len(C_vals)):
    lines.append(f"{C_vals[i]},{V_vals[i]*1e6:.3f},{V_vals[i]:.6e},{phi_vals[i]:.2f},"
                 f"{C_predicted[i]:.3f},{C_predicted[i]-C_vals[i]:.3f}")

outpath = os.path.join(os.path.dirname(__file__), 'calibration.csv')
with open(outpath, 'w') as f:
    f.write('\n'.join(lines) + '\n')

print("=== Fixed Capacitor Calibration ===")
print(f"Linear fit: V_out = k·C_nominal + b")
print(f"  k = {k:.6e} V/pF = {k_uV_per_pF:.4f} μV/pF")
print(f"  b = {b:.6e} V = {b*1e6:.4f} μV")
print(f"  R² = {R2:.6f}")
print(f"Theoretical k = V_s/C0 = {k_theory:.6e} V/pF = {k_theory*1e6:.4f} μV/pF")
print(f"Ratio k_exp/k_theory = {k/k_theory:.4f}")
print(f"  Offset capacitance b/k = {b/k:.2f} pF (cf. C_stray=1.4 pF)")
print(f"\nC_predicted - C_nominal offsets (due to stray + system):")
for i in range(len(C_vals)):
    print(f"  {C_vals[i]:3.0f} pF: pred={C_predicted[i]:.2f} pF, Δ={C_predicted[i]-C_vals[i]:.3f} pF")

# Save calibration coefficients for other scripts
with open(os.path.join(os.path.dirname(__file__), 'cal_coeffs.txt'), 'w') as f:
    f.write(f"k_V_per_pF,{k:.12e}\nb_V,{b:.12e}\nk_theory,{k_theory:.12e}\n")
