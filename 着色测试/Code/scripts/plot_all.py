"""
Comprehensive C-V data processing and publication-quality figure generation.
Processes raw data directly from Data/ and generates all 7 figures.
"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os

# ============================================================
# Global settings
# ============================================================
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman'],
    'font.size': 10,
    'axes.labelsize': 11,
    'axes.titlesize': 12,
    'legend.fontsize': 8,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'figure.dpi': 150,
    'savefig.dpi': 600,
    'savefig.bbox': 'tight',
    'axes.unicode_minus': False,
    'text.usetex': False,
})

# ============================================================
# Constants
# ============================================================
C0 = 5000.0           # pF, series capacitor
V_s = 49.47e-3        # V (RMS), LIA reference
C_stray = 1.4         # pF
q = 1.602e-19         # C
eps_si = 11.8
eps0 = 8.854e-14      # F/cm
eps_eps0 = eps_si * eps0  # 1.044772e-12 F/cm
A = 5.03e-3           # cm^2

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, '..', '..', 'Data')
FIG_DIR = os.path.join(BASE, '..', 'fig')
os.makedirs(FIG_DIR, exist_ok=True)

# ============================================================
# Data loader utility
# ============================================================
def load_data_file(filepath):
    """Load CSV data, skipping # comment lines and header row."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    data_start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('#') or 'time(s)' in s:
            continue
        if s:
            data_start = i
            break
    data = []
    for line in lines[data_start:]:
        s = line.strip()
        if s:
            data.append([float(x) for x in s.split(',')])
    return np.array(data)

def extract_header_param(filepath, param):
    """Extract a parameter from file header comments, e.g. '#\tTc: 0.001 s'."""
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') and param in line:
                val = line.split(':')[1].strip().split()[0]
                return float(val)
    return None

# ============================================================
# Helper functions
# ============================================================
def R1w_to_C(R1w):
    return C0 * R1w / V_s

def C_to_actual(C_x):
    return C_x - C_stray

def C_to_w(C_pF):
    return eps_eps0 * A / (C_pF * 1e-12)

def C_to_invC2(C_pF):
    return 1.0 / (C_pF * C_pF)

def compute_Nw(Vb_set, C_actual):
    """Compute N(w) via central difference of 1/C^2.
    Vb_set is 0 to -10 V; use V_R = -Vb_set (positive reverse bias).
    """
    V_R = -Vb_set
    invC2 = C_to_invC2(C_actual)
    N_arr = np.full(len(C_actual), np.nan)
    w_arr = C_to_w(C_actual)
    for i in range(1, len(C_actual) - 1):
        dV = V_R[i+1] - V_R[i-1]
        d_invC2 = (invC2[i+1] - invC2[i-1]) / dV
        N_arr[i] = 2.0 / (q * eps_eps0 * A**2 * d_invC2 * 1e24)
    return N_arr, w_arr

# ============================================================
# FIGURE 1: Noise suppression
# ============================================================
def fig1_noise():
    print("=== Figure 1: Noise Suppression ===")
    noise_files = [
        ('noise_1ms_C-time_15h40m30s_1.txt', 1),
        ('noise_3ms_C-time_15h41m53s_1.txt', 3),
        ('noise_10ms_C-time_15h43m25s_1.txt', 10),
        ('noise_30ms_C-time_15h44m49s_1.txt', 30),
        ('noise_100ms_C-time_15h46m11s_1.txt', 100),
        ('noise_300ms_C-time_15h47m43s_1.txt', 300),
        ('noise_1000ms_C-time_15h50m07s_1.txt', 1000),
    ]
    results = []
    for fname, _ in noise_files:
        fpath = os.path.join(DATA_DIR, fname)
        Tc = extract_header_param(fpath, 'Tc')
        data = load_data_file(fpath)
        R1w = data[:, 4]
        sigma = np.std(R1w, ddof=1)
        mean_val = np.mean(R1w)
        results.append({'Tc': Tc, 'sigma': sigma, 'mean': mean_val})
        print(f"  Tc={Tc*1000:.0f}ms: sigma={sigma:.6e} V, mean={mean_val:.6e} V")

    Tc_arr = np.array([r['Tc'] for r in results])
    sigma_arr = np.array([r['sigma'] for r in results])

    # Theory reference: sigma = A/sqrt(Tc)
    A_coeff = sigma_arr[0] * np.sqrt(Tc_arr[0])
    Tc_theo = np.logspace(np.log10(Tc_arr.min()*0.8), np.log10(Tc_arr.max()*1.2), 100)
    sigma_theo = A_coeff / np.sqrt(Tc_theo)

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.loglog(Tc_arr * 1000, sigma_arr, 'o', color='#2166AC', markersize=9,
              markeredgewidth=1.2, markeredgecolor='#053061',
              label=r'$\sigma(R_{1\omega})$ data')
    ax.loglog(Tc_theo * 1000, sigma_theo, '--', color='#B2182B', linewidth=1.5,
              label=r'$\sigma \propto 1/\sqrt{T_c}$ (theory)')
    ax.set_xlabel(r'$T_c$ (ms)')
    ax.set_ylabel(r'$\sigma(R_{1\omega})$ (V)')
    ax.set_title('Noise Suppression vs. Lock-in Time Constant')
    ax.legend(frameon=True, fancybox=False, edgecolor='gray')
    ax.grid(True, which='both', alpha=0.3, linewidth=0.5)
    ax.tick_params(which='both', direction='in', top=True, right=True)
    fig.tight_layout()
    outpath = os.path.join(FIG_DIR, 'noise_analysis.pdf')
    fig.savefig(outpath)
    plt.close(fig)
    print(f"  Saved: {outpath}\n")
    return Tc_arr, sigma_arr

# ============================================================
# FIGURE 2: Calibration linearity
# ============================================================
def fig2_calibration():
    print("=== Figure 2: Calibration Linearity ===")
    C_nom = np.array([20, 40, 60, 80, 100])
    V_uV = np.array([27.181, 52.32, 74.11, 99.80, 123.80])
    V_out = V_uV * 1e-6

    coeffs = np.polyfit(C_nom, V_out, 1)
    k, b = coeffs
    V_fit = np.polyval(coeffs, C_nom)
    SS_res = np.sum((V_out - V_fit)**2)
    SS_tot = np.sum((V_out - np.mean(V_out))**2)
    R2 = 1 - SS_res / SS_tot

    k_theory = V_s / C0
    print(f"  Fit: V_out = ({k:.6e})*C + ({b:.6e})")
    print(f"  k = {k*1e6:.4f} uV/pF, k_theory = {k_theory*1e6:.4f} uV/pF")
    print(f"  R2 = {R2:.6f}, k_exp/k_theory = {k/k_theory:.4f}")

    C_fit = np.linspace(15, 105, 100)
    V_line = np.polyval(coeffs, C_fit)

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(C_nom, V_out * 1e6, 'o', color='#2166AC', markersize=10,
            markeredgewidth=1.2, markeredgecolor='#053061', label='Data')
    eq_str = (f'Linear fit: $V_{{\\rm out}} = {k*1e6:.3f}\\,C + {b*1e6:.3f}$')
    ax.plot(C_fit, V_line * 1e6, '-', color='#B2182B', linewidth=1.5, label=eq_str)
    ax.text(0.55, 0.15,
            f'$R^2 = {R2:.5f}$\n$k_{{\\rm exp}}/k_{{\\rm theo}} = {k/k_theory:.3f}$',
            transform=ax.transAxes, fontsize=9,
            bbox=dict(boxstyle='round,pad=0.3', facecolor='wheat', alpha=0.6))
    ax.set_xlabel(r'$C_{\rm nominal}$ (pF)')
    ax.set_ylabel(r'$V_{\rm out}$ ($\mu$V)')
    ax.set_title(r'Lock-in Amplifier Calibration: $V_{\rm out}$ vs. $C_{\rm nominal}$')
    ax.legend(frameon=True, fancybox=False, edgecolor='gray', fontsize=9)
    ax.grid(True, alpha=0.3, linewidth=0.5)
    ax.tick_params(which='both', direction='in', top=True, right=True)
    ax.set_xlim(12, 108)
    fig.tight_layout()
    outpath = os.path.join(FIG_DIR, 'calibration_linearity.pdf')
    fig.savefig(outpath)
    plt.close(fig)
    print(f"  Saved: {outpath}\n")
    return k, b, R2

# ============================================================
# FIGURES 3 & 4: C-V and 1/C^2-V for all diodes
# ============================================================
def fig3_4_cv():
    print("=== Figures 3 & 4: C-V and 1/C^2-V ===")
    diode_files = [
        (r'D$_1$', 'D_1 C-V_C-Vb_16h11m27s_1.txt'),
        (r'D$_2$', 'D_2 C-V_C-Vb_16h14m46s_1.txt'),
        (r'D$_3$', 'D_3 C-V_C-Vb_16h18m04s_1.txt'),
        (r'D$_4$', 'D_4 C-V_C-Vb_16h21m04s_1.txt'),
        (r'D$_5$', 'D_5 C-V_C-Vb_16h24m01s_1.txt'),
    ]
    colors = ['#2166AC', '#B2182B', '#4DAF4A', '#FF7F00', '#984EA3']
    markers = ['o', 's', '^', 'D', 'v']
    all_data = {}

    # --- Figure 3: C-V ---
    fig3, ax3 = plt.subplots(figsize=(6, 4.5))
    for (label, fname), c, m in zip(diode_files, colors, markers):
        data = load_data_file(os.path.join(DATA_DIR, fname))
        Vb_set = data[:, 2]
        V_R = -Vb_set
        R1w = data[:, 4]
        C_actual = C_to_actual(R1w_to_C(R1w))
        all_data[label] = {'Vb': Vb_set, 'V_R': V_R, 'R1w': R1w, 'C_actual': C_actual}
        sort_idx = np.argsort(V_R)
        ax3.plot(V_R[sort_idx], C_actual[sort_idx], '-', color=c, linewidth=1.2,
                 marker=m, markersize=5, markevery=max(1, len(V_R)//10),
                 markerfacecolor='none', markeredgewidth=1.0, label=label)
        print(f"  {label}: C(0V)={C_actual[np.argmin(np.abs(V_R))]:.2f} pF, "
              f"C(10V)={C_actual[np.argmin(np.abs(V_R-10))]:.2f} pF")

    ax3.set_xlabel(r'$V_R$ (V)')
    ax3.set_ylabel(r'$C$ (pF)')
    ax3.set_title(r'C--V Characteristics of All Diodes')
    ax3.legend(frameon=True, fancybox=False, edgecolor='gray')
    ax3.grid(True, alpha=0.3, linewidth=0.5)
    ax3.tick_params(which='both', direction='in', top=True, right=True)
    fig3.tight_layout()
    fig3.savefig(os.path.join(FIG_DIR, 'CV_all_diodes.pdf'))
    plt.close(fig3)
    print("  Saved: CV_all_diodes.pdf")

    # --- Figure 4: 1/C^2-V ---
    fig4, ax4 = plt.subplots(figsize=(6, 4.5))
    for (label, _), c, m in zip(diode_files, colors, markers):
        d = all_data[label]
        invC2 = C_to_invC2(d['C_actual'])
        sort_idx = np.argsort(d['V_R'])
        ax4.plot(d['V_R'][sort_idx], invC2[sort_idx], '-', color=c, linewidth=1.2,
                 marker=m, markersize=5, markevery=max(1, len(d['V_R'])//10),
                 markerfacecolor='none', markeredgewidth=1.0, label=label)

    ax4.set_xlabel(r'$V_R$ (V)')
    ax4.set_ylabel(r'$1/C^2$ (pF$^{-2}$)')
    ax4.set_title(r'$1/C^2$--$V_R$ Characteristics of All Diodes')
    ax4.legend(frameon=True, fancybox=False, edgecolor='gray')
    ax4.grid(True, alpha=0.3, linewidth=0.5)
    ax4.tick_params(which='both', direction='in', top=True, right=True)
    fig4.tight_layout()
    fig4.savefig(os.path.join(FIG_DIR, 'invC2_all_diodes.pdf'))
    plt.close(fig4)
    print("  Saved: invC2_all_diodes.pdf\n")
    return all_data

# ============================================================
# FIGURE 5: D_2 Phase vs V_R at 8 frequencies
# ============================================================
def fig5_phase():
    print("=== Figure 5: D_2 Phase Analysis ===")
    phase_files = [
        ('933 Hz',  'D_2 Phi-V 933_C-Vb_17h08m07s_1.txt'),
        ('1033 Hz', 'D_2 Phi-V 1033_C-Vb_16h50m00s_1.txt'),
        ('1133 Hz', 'D_2 Phi-V_C-Vb_16h36m57s_1.txt'),
        ('1233 Hz', 'D_2 Phi-V 1233_C-Vb_16h52m57s_1.txt'),
        ('1333 Hz', 'D_2 Phi-V 1333_C-Vb_16h55m52s_1.txt'),
        ('1433 Hz', 'D_2 Phi-V 1433_C-Vb_16h58m42s_1.txt'),
        ('1533 Hz', 'D_2 Phi-V 1533_C-Vb_17h01m56s_1.txt'),
        ('1633 Hz', 'D_2 Phi-V 1633_C-Vb_17h05m03s_1.txt'),
    ]

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    cmap = plt.cm.viridis
    colors = [cmap(i/7) for i in range(8)]

    for i, (label, fname) in enumerate(phase_files):
        data = load_data_file(os.path.join(DATA_DIR, fname))
        V_R = -data[:, 2]
        theta = data[:, 5]
        sort_idx = np.argsort(V_R)
        ax.plot(V_R[sort_idx], theta[sort_idx], '-', color=colors[i], linewidth=1.2,
                marker='.', markersize=3, label=label)

    ax.set_xlabel(r'$V_R$ (V)')
    ax.set_ylabel(r'$\theta_{1\omega}$ (deg)')
    ax.set_title(r'D$_2$ Phase $\theta_{1\omega}$ vs. Bias at Various Frequencies')
    ax.legend(frameon=True, fancybox=False, edgecolor='gray', ncol=2, fontsize=8)
    ax.grid(True, alpha=0.3, linewidth=0.5)
    ax.tick_params(which='both', direction='in', top=True, right=True)
    fig.tight_layout()
    outpath = os.path.join(FIG_DIR, 'D2_phase_vs_Vb.pdf')
    fig.savefig(outpath)
    plt.close(fig)
    print(f"  Saved: {outpath}\n")

# ============================================================
# FIGURE 6: N(w) impurity profiles
# ============================================================
def fig6_nw(all_data):
    print("=== Figure 6: N(w) Impurity Profiles ===")
    colors = ['#2166AC', '#B2182B', '#4DAF4A', '#FF7F00', '#984EA3']
    markers = ['o', 's', '^', 'D', 'v']

    fig, ax = plt.subplots(figsize=(6, 4.5))
    any_plotted = False
    for (label, d), c, m in zip(all_data.items(), colors, markers):
        N_arr, w_arr = compute_Nw(d['Vb'], d['C_actual'])
        valid = ~np.isnan(N_arr) & (N_arr > 0)
        if valid.sum() < 3:
            print(f"  {label}: insufficient valid N(w) points, skipping")
            continue
        any_plotted = True
        sort_idx = np.argsort(w_arr[valid])
        ax.plot(w_arr[valid][sort_idx] * 1e4, N_arr[valid][sort_idx], '-', color=c,
                linewidth=1.2, marker=m, markersize=5,
                markevery=max(1, valid.sum()//8), markerfacecolor='none',
                markeredgewidth=1.0, label=label)
        print(f"  {label}: w = {w_arr[valid].min()*1e4:.2f}--{w_arr[valid].max()*1e4:.2f} um, "
              f"N = {N_arr[valid].min():.2e}--{N_arr[valid].max():.2e} cm-3")

    ax.set_xlabel(r'$w$ ($\mu$m)')
    ax.set_ylabel(r'$N(w)$ (cm$^{-3}$)')
    ax.set_title(r'Impurity Concentration Profiles $N(w)$')
    ax.set_yscale('log')
    if any_plotted:
        ax.legend(frameon=True, fancybox=False, edgecolor='gray')
    ax.grid(True, which='both', alpha=0.3, linewidth=0.5)
    ax.tick_params(which='both', direction='in', top=True, right=True)
    fig.tight_layout()
    outpath = os.path.join(FIG_DIR, 'Nw_profiles.pdf')
    fig.savefig(outpath)
    plt.close(fig)
    print(f"  Saved: {outpath}\n")

# ============================================================
# FIGURE 7: 1/C^2 extrapolation for all diodes
# ============================================================
def fig7_extrapolation(all_data):
    print("=== Figure 7: 1/C^2 Extrapolation ===")
    colors = ['#2166AC', '#B2182B', '#4DAF4A', '#FF7F00', '#984EA3']

    n_diodes = len(all_data)
    ncols = min(3, n_diodes)
    nrows = int(np.ceil(n_diodes / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.3*ncols, 3.0*nrows))
    if n_diodes == 1:
        axes = np.array([[axes]])
    axes = np.atleast_2d(axes)

    qualified = []
    for idx, (label, d) in enumerate(all_data.items()):
        ax = axes[idx // ncols][idx % ncols]
        V_R = d['V_R']
        C_actual = d['C_actual']
        invC2 = C_to_invC2(C_actual)

        # Linear region: V_R = 2 to 10 V
        mask = (V_R >= 2.0) & (V_R <= 10.0)
        V_lin = V_R[mask]
        invC2_lin = invC2[mask]

        fit_success = False
        if len(V_lin) >= 5:
            coeffs = np.polyfit(V_lin, invC2_lin, 1)
            slope, intercept = coeffs
            V_fit = np.polyval(coeffs, V_lin)
            SS_res = np.sum((invC2_lin - V_fit)**2)
            SS_tot = np.sum((invC2_lin - np.mean(invC2_lin))**2)
            R2 = 1 - SS_res / SS_tot if SS_tot > 0 else 0
            V_D = intercept / slope   # 1/C^2 = slope*(V_R + V_D)
            N_D = 2.0 / (q * eps_eps0 * A**2 * slope * 1e24)

            if R2 > 0.99 and V_D > 0:
                fit_success = True
                qualified.append((label, slope, intercept, V_D, N_D, R2))
            print(f"  {label}: V_D={V_D:.4f} V, N_D={N_D:.2e} cm-3, R2={R2:.5f}"
                  + (" [qualified]" if fit_success else ""))

        # Plot all data points
        sort_idx = np.argsort(V_R)
        ax.plot(V_R[sort_idx], invC2[sort_idx], '.', color=colors[idx],
                markersize=4, label='Data')

        if fit_success:
            V_ext = np.linspace(-0.5, 11, 100)
            ax.plot(V_ext, np.polyval([slope, intercept], V_ext), '-',
                    color='#B2182B', linewidth=1.5, label='Linear fit')
            ax.axvline(x=V_D, color='gray', linestyle=':', linewidth=1.0)
            ax.plot(V_D, 0, 'r*', markersize=10, markeredgewidth=0.8,
                    markeredgecolor='darkred')
            ax.text(0.95, 0.88,
                    f'$V_D = {V_D:.3f}$ V\n$N_D = {N_D:.2e}$ cm$^{{-3}}$\n$R^2 = {R2:.4f}$',
                    transform=ax.transAxes, fontsize=8, ha='right',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='wheat', alpha=0.7),
                    verticalalignment='top')

        ax.set_xlabel(r'$V_R$ (V)')
        ax.set_ylabel(r'$1/C^2$ (pF$^{-2}$)')
        ax.set_title(f'{label}', fontsize=11)
        ax.legend(frameon=True, fancybox=False, edgecolor='gray', fontsize=7)
        ax.grid(True, alpha=0.3, linewidth=0.5)
        ax.tick_params(which='both', direction='in', top=True, right=True)

    # Hide unused subplots
    for idx in range(len(all_data), nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    fig.suptitle(r'$1/C^2$--$V_R$ Linear Extrapolation for $V_D$ Determination',
                 fontsize=12, y=1.01)
    fig.tight_layout()
    outpath = os.path.join(FIG_DIR, 'invC2_extrapolation.pdf')
    fig.savefig(outpath)
    plt.close(fig)
    print(f"  Saved: {outpath}")
    print(f"\n  Qualified diodes: {[q[0] for q in qualified]}")
    return qualified

# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("C-V Data Processing & Figure Generation")
    print("=" * 60)
    print(f"Data directory: {DATA_DIR}")
    print(f"Figure directory: {FIG_DIR}\n")

    Tc_arr, sigma_arr = fig1_noise()
    k_cal, b_cal, R2_cal = fig2_calibration()
    all_diode_data = fig3_4_cv()
    fig5_phase()
    fig6_nw(all_diode_data)
    qualified = fig7_extrapolation(all_diode_data)

    print("\n" + "=" * 60)
    print("All figures generated successfully!")
    print(f"Figures saved to: {FIG_DIR}")
    print("=" * 60)
