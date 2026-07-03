"""Part 3: C-V for all 5 diodes. C_j=(R1w-b)/k. b includes stray — no extra subtraction."""
import numpy as np, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from analysis_constants import *
from data_loader import load_data_file

DATA_DIR = os.path.join(os.path.dirname(__file__), '..')
PROC_DIR = os.path.dirname(__file__)

cal = {}
with open(os.path.join(PROC_DIR, 'cal_coeffs.txt')) as f:
    for line in f:
        kk, vv = line.strip().split(',')
        cal[kk] = float(vv)
k_cal, b_cal = cal['k_V_per_pF'], cal['b_V']

def R1w_to_C(R1w):
    return (R1w - b_cal) / k_cal

diode_files = [
    ('D_1','D_1 C-V_C-Vb_16h11m27s_1.txt'),
    ('D_2','D_2 C-V_C-Vb_16h14m46s_1.txt'),
    ('D_3','D_3 C-V_C-Vb_16h18m04s_1.txt'),
    ('D_4','D_4 C-V_C-Vb_16h21m04s_1.txt'),
    ('D_5','D_5 C-V_C-Vb_16h24m01s_1.txt'),
]

for label, fname in diode_files:
    data = load_data_file(os.path.join(DATA_DIR, fname))
    Vb, R1w, theta, R2w = data[:,2], data[:,4], data[:,5], data[:,6]
    C_j = R1w_to_C(R1w)
    invC2 = C_to_invC2(C_j)
    w_cm = C_to_w(C_j)
    with open(os.path.join(PROC_DIR, f'{label}_CV_processed.csv'), 'w', encoding='utf-8') as f:
        f.write("Vb_set(V),R_1w(V),theta_1w(deg),C_j(pF),1/C2(pF-2),w(cm),R_2w(V)\n")
        for i in range(len(Vb)):
            f.write(f"{Vb[i]:.4f},{R1w[i]:.6e},{theta[i]:.4f},{C_j[i]:.4f},{invC2[i]:.6e},{w_cm[i]:.6e},{R2w[i]:.6e}\n")

print("=== Diode C-V Summary (C_j = (R1w-b)/k, stray in b) ===")
print(f"{'Diode':>6s}  {'C(0V)pF':>10s}  {'C(-2V)pF':>10s}  {'C(-5V)pF':>10s}  {'C(-10V)pF':>10s}")
for label, fname in diode_files:
    data = load_data_file(os.path.join(DATA_DIR, fname))
    Vb, C_j = data[:,2], R1w_to_C(data[:,4])
    i0=np.argmin(np.abs(Vb-0)); i2=np.argmin(np.abs(Vb+2))
    i5=np.argmin(np.abs(Vb+5)); i10=np.argmin(np.abs(Vb+10))
    print(f"  {label}  {C_j[i0]:10.2f}  {C_j[i2]:10.2f}  {C_j[i5]:10.2f}  {C_j[i10]:10.2f}")
