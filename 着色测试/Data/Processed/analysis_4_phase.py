"""Part 4: D_2 Phase vs V_R at 8 frequencies — leakage assessment."""
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

phi_files = [
    ('933',  'D_2 Phi-V 933_C-Vb_17h08m07s_1.txt'),
    ('1033', 'D_2 Phi-V 1033_C-Vb_16h50m00s_1.txt'),
    ('1133', 'D_2 Phi-V_C-Vb_16h36m57s_1.txt'),
    ('1233', 'D_2 Phi-V 1233_C-Vb_16h52m57s_1.txt'),
    ('1333', 'D_2 Phi-V 1333_C-Vb_16h55m52s_1.txt'),
    ('1433', 'D_2 Phi-V 1433_C-Vb_16h58m42s_1.txt'),
    ('1533', 'D_2 Phi-V 1533_C-Vb_17h01m56s_1.txt'),
    ('1633', 'D_2 Phi-V 1633_C-Vb_17h05m03s_1.txt'),
]

all_data = {}
outpath = os.path.join(PROC_DIR, 'D2_phase_combined.csv')
with open(outpath, 'w', encoding='utf-8') as fout:
    fout.write("freq(Hz),Vb_set(V),theta(deg),C_j(pF),R_2w(V)\n")
    for freq_str, fname in phi_files:
        data = load_data_file(os.path.join(DATA_DIR, fname))
        Vb, theta = data[:,2], data[:,5]
        C_j = R1w_to_C(data[:,4])
        R2w = data[:,6]
        all_data[freq_str] = {'Vb':Vb, 'theta':theta, 'C_j':C_j, 'R2w':R2w}
        for i in range(len(Vb)):
            fout.write(f"{freq_str},{Vb[i]:.4f},{theta[i]:.4f},{C_j[i]:.4f},{R2w[i]:.6e}\n")

print("=== D_2 Phase vs Frequency ===")
print(f"{'Freq':>8s}  th@0V    th@-4V   th@-10V    Cj@0V(pF)")
for freq_str in sorted(all_data.keys(), key=lambda x:int(x)):
    r=all_data[freq_str]
    i0=np.argmin(np.abs(r['Vb']-0)); i4=np.argmin(np.abs(r['Vb']+4)); i10=np.argmin(np.abs(r['Vb']+10))
    print(f"  {freq_str}Hz  {r['theta'][i0]:.2f}    {r['theta'][i4]:.2f}    {r['theta'][i10]:.2f}    {r['C_j'][i0]:.2f}")

# Leakage at 1133 Hz
r=all_data['1133']
Phi_0=-171.93; omega=2*np.pi*1133
print(f"\n--- D_2 Leakage (1133Hz, Phi_0={Phi_0}deg) ---")
print(f"{'Vb(V)':>8s}  th(deg)  Dth(deg)   Cj(pF)       R2w(V)     Rp(MOhm)")
for vt in [0,-1,-2,-4,-6,-8,-10]:
    idx=np.argmin(np.abs(r['Vb']-vt))
    dtheta=abs(r['theta'][idx]-Phi_0)
    CF=r['C_j'][idx]*1e-12
    rp_str=">1000" if dtheta<0.01 else f"{1.0/(omega*CF*np.tan(np.radians(dtheta)))*1e-6:.2f}"
    print(f"  {vt:+.0f}     {r['theta'][idx]:.2f}    {dtheta:.2f}    {r['C_j'][idx]:.2f}    {r['R2w'][idx]:.6e}    {rp_str}")
