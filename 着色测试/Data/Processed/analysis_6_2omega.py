"""Part 6: 2nd harmonic analysis - R_2w vs v_t at Vb=4V and Vb=5V."""
import numpy as np, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from analysis_constants import *
from data_loader import load_data_file

DATA_DIR, PROC_DIR = os.path.join(os.path.dirname(__file__), '..'), os.path.dirname(__file__)

for label, fname in [('Vb4V','D_2 2omega R_2omega-V_t Vb = 4V_C-vt_17h29m58s_1.txt'),
                      ('Vb5V','D_2 2omega R_2omega-V_t_C-vt_17h25m17s_1.txt')]:
    data = load_data_file(os.path.join(DATA_DIR, fname))
    vt, R1w, R2w = data[:,1], data[:,4], data[:,6]
    mask = vt>0.01
    logv, logR = np.log(vt[mask]), np.log(R2w[mask])
    c = np.polyfit(logv, logR, 1)
    print(f"\n=== D_2 2nd Harmonic: {label} ===")
    print(f"  R2w ~ vt^{c[0]:.3f}  (theory=2 for pure C-V nonlinearity)")
    print(f"  vt=0.05V: R2w={R2w[5]:.6e}V, ratio={R2w[5]/R1w[5]:.4e}")
    print(f"  vt=0.50V: R2w={R2w[-1]:.6e}V, ratio={R2w[-1]/R1w[-1]:.4e}")
    with open(os.path.join(PROC_DIR, f'D2_2omega_{label}.csv'), 'w', encoding='utf-8') as f:
        f.write("vt(V),R_1w(V),R_2w(V),R2w/R1w\n")
        for i in range(len(vt)):
            f.write(f"{vt[i]:.4f},{R1w[i]:.6e},{R2w[i]:.6e},{R2w[i]/R1w[i] if R1w[i]>1e-15 else 0:.6e}\n")
