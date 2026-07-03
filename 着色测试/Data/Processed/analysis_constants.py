"""Constants and utilities for C-V analysis."""
import numpy as np

# Physical constants
q = 1.602e-19          # C, electron charge
eps0 = 8.854e-14       # F/cm, vacuum permittivity
eps = 11.8             # Si relative permittivity
eps_eps0 = eps * eps0  # 1.044772e-12 F/cm
A = 5.03e-3            # cm², junction area
C0 = 5000.0            # pF, series capacitor
C_stray = 1.4          # pF, stray capacitance
V_s = 49.47e-3         # V (RMS), LIA reference signal
v_t_amplitude = V_s * np.sqrt(2)  # V amplitude

def R1w_to_C(R1w):
    """Convert LIA R_1ω (V RMS) to capacitance C_x (pF). C_x = C0 * R1w / V_s"""
    return C0 * R1w / V_s

def C_to_C_actual(C_x):
    """Subtract stray capacitance."""
    return C_x - C_stray

def C_to_w(C):
    """Compute depletion width w (cm) from capacitance C (pF)."""
    return eps_eps0 * A / (C * 1e-12)

def C_to_invC2(C):
    """Compute 1/C² from C (pF), returns in pF⁻²."""
    return 1.0 / (C * C)

def compute_N_from_invC2_slope(slope):
    """Compute N_D from d(1/C²)/dV slope (pF⁻²/V).
    N = 2 / (q * eps_eps0 * A² * slope)
    slope must be in F⁻²/V converted: 1 pF⁻² = 1e24 F⁻²
    """
    return 2.0 / (q * eps_eps0 * A**2 * slope * 1e24)

def compute_VD_from_intercept(slope, intercept):
    """Compute V_D from 1/C² linear fit: 1/C² = slope * V_R + intercept.
    Physical: 1/C² = k*(V_D + V_R) where both V_D and V_R (reverse magnitude) are positive.
    Thus intercept = k*V_D, V_D = intercept/slope."""
    return intercept / slope

def compute_Nw_center_diff(V_R, C, idx):
    """Compute N(w) using central difference of 1/C²."""
    if idx == 0 or idx == len(C) - 1:
        return np.nan, np.nan
    invC2 = C_to_invC2(C)
    d_invC2_dV = (invC2[idx+1] - invC2[idx-1]) / (V_R[idx+1] - V_R[idx-1])
    N = compute_N_from_invC2_slope(d_invC2_dV)
    w = C_to_w(C[idx])
    return N, w
