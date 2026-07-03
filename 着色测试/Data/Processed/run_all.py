"""Master analysis runner: executes all C-V analysis steps."""
import subprocess, os, sys

scripts = [
    'analysis_1_noise.py',
    'analysis_2_calibration.py',
    'analysis_3_cv_all.py',
    'analysis_4_phase.py',
    'analysis_5_impurity.py',
    'analysis_6_2omega.py',
]

base = os.path.dirname(__file__)

for s in scripts:
    spath = os.path.join(base, s)
    print(f"\n{'='*60}")
    print(f"Running: {s}")
    print('='*60)
    result = subprocess.run([sys.executable, spath], cwd=base,
                           capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    if result.returncode != 0:
        print(f"WARNING: {s} exited with code {result.returncode}")
