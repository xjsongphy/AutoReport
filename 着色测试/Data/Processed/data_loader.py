"""Robust data loader — handles comment headers."""
import numpy as np

def load_data_file(filepath):
    """Load experimental data file, skipping all # comments and header row."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # Find the first data line (not starting with # and not containing 'time(s)')
    data_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('#') or 'time(s)' in stripped:
            continue
        if stripped:  # non-empty, non-comment, non-header
            data_start = i
            break
    # Parse from data_start
    data_lines = []
    for line in lines[data_start:]:
        stripped = line.strip()
        if stripped:
            parts = [float(x) for x in stripped.split(',')]
            data_lines.append(parts)
    return np.array(data_lines)
