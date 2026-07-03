"""Part 1: Noise analysis — quantify LIA noise suppression vs time constant."""
import numpy as np, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from analysis_constants import *
from data_loader import load_data_file

DATA_DIR = os.path.join(os.path.dirname(__file__), '..')

noise_files = [
    ('noise_1ms',   'noise_1ms_C-time_15h40m30s_1.txt'),
    ('noise_3ms',   'noise_3ms_C-time_15h41m53s_1.txt'),
    ('noise_10ms',  'noise_10ms_C-time_15h43m25s_1.txt'),
    ('noise_30ms',  'noise_30ms_C-time_15h44m49s_1.txt'),
    ('noise_100ms', 'noise_100ms_C-time_15h46m11s_1.txt'),
    ('noise_300ms', 'noise_300ms_C-time_15h47m43s_1.txt'),
    ('noise_1000ms','noise_1000ms_C-time_15h50m07s_1.txt'),
]

results = []
for label, fname in noise_files:
    fpath = os.path.join(DATA_DIR, fname)
    data = load_data_file(fpath)
    R1w = data[:, 4]
    sigma_R1w = np.std(R1w, ddof=1)
    mean_R1w = np.mean(R1w)
    with open(fpath, encoding='utf-8') as f:
        for line in f:
            if 'Tc:' in line:
                Tc = float(line.split(':')[1].strip().split()[0])
                break
    Delta_fN = 1.0 / (4.0 * Tc)
    results.append({
        'label': label, 'Tc': Tc, 'Tc_ms': Tc*1000,
        'mean_R1w': mean_R1w, 'sigma_R1w': sigma_R1w,
        'Delta_fN_Hz': Delta_fN, 'N_points': len(R1w),
    })

outpath = os.path.join(os.path.dirname(__file__), 'noise_analysis.csv')
with open(outpath, 'w') as f:
    f.write("Tc(ms),Tc(s),Δf_N(Hz),Mean_R1ω(V),σ_R1ω(V),σ/√Δf_N,N_points\n")
    for r in results:
        ratio = r['sigma_R1w']/np.sqrt(r['Delta_fN_Hz'])
        f.write(f"{r['Tc_ms']:.0f},{r['Tc']:.3f},{r['Delta_fN_Hz']:.3f},"
                f"{r['mean_R1w']:.6e},{r['sigma_R1w']:.6e},{ratio:.6e},{r['N_points']}\n")

print("=== Noise Analysis Results ===")
print(f"{'Tc':>10s}  {'Δf_N(Hz)':>10s}  {'σ(R1ω)(V)':>14s}  {'σ/√Δf_N':>12s}")
for r in results:
    ratio = r['sigma_R1w']/np.sqrt(r['Delta_fN_Hz'])
    print(f"{r['Tc_ms']:6.0f}ms  {r['Delta_fN_Hz']:10.3f}  {r['sigma_R1w']:14.6e}  {ratio:12.6e}")
print("\n(σ/√Δf_N ≈ constant → verifies white noise & Δf_N = 1/(4RC))")
print(f"Theoretical: σ ∝ √Δf_N ∝ 1/√Tc")
# Check scaling: compute ratio of σ at 1ms vs 1000ms
if len(results) >= 2:
    r1 = results[0]; r7 = results[-1]
    theo_ratio = np.sqrt(r7['Delta_fN_Hz']/r1['Delta_fN_Hz'])
    exp_ratio = r7['sigma_R1w']/r1['sigma_R1w']
    print(f"σ(1000ms)/σ(1ms) = {exp_ratio:.4f} (theory √(Δf_1000/Δf_1) = {theo_ratio:.4f})")
