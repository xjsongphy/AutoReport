import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os

# 文件列表（根据实际路径调整）
files = [
    "D:\大二下\近代物理实验\C-V法\\2300011419_2025-05-14 - txt\D_2 Phi-V 933_C-Vb_17h08m07s_1.txt",
    "D:\大二下\近代物理实验\C-V法\\2300011419_2025-05-14 - txt\D_2 Phi-V 1033_C-Vb_16h50m00s_1.txt",
    "D:\大二下\近代物理实验\C-V法\\2300011419_2025-05-14 - txt\D_2 Phi-V_C-Vb_16h36m57s_1.txt",
    "D:\大二下\近代物理实验\C-V法\\2300011419_2025-05-14 - txt\D_2 Phi-V 1233_C-Vb_16h52m57s_1.txt",
    "D:\大二下\近代物理实验\C-V法\\2300011419_2025-05-14 - txt\D_2 Phi-V 1333_C-Vb_16h55m52s_1.txt",
    "D:\大二下\近代物理实验\C-V法\\2300011419_2025-05-14 - txt\D_2 Phi-V 1433_C-Vb_16h58m42s_1.txt",
    "D:\大二下\近代物理实验\C-V法\\2300011419_2025-05-14 - txt\D_2 Phi-V 1533_C-Vb_17h01m56s_1.txt",
    "D:\大二下\近代物理实验\C-V法\\2300011419_2025-05-14 - txt\D_2 Phi-V 1633_C-Vb_17h05m03s_1.txt"
]

# 存储所有数据：键为频率，值为(Vb_set, theta_2ω)
data_dict = {}

for file in files:
    with open(file, 'r') as f:
        frequency = None
        # 提取频率
        for line in f:
            if line.startswith('#\tFrequency: '):
                frequency = int(line.split()[2])
                break
        # 读取数据
        df = pd.read_csv(f, comment='#', sep=',', skip_blank_lines=True,
                        names=['time(s)', 'vt(V)', 'Vb_set(V)', 'Vb_meas(V)',
                               'R_1ω(V)', 'theta_1ω(deg)', 'R_2ω(V)', 'theta_2ω(deg)'])
        data_dict[frequency] = (df['Vb_set(V)'], df['theta_1ω(deg)'])

# 绘制二维多曲线图
plt.figure(figsize=(10, 6))
colors = plt.cm.viridis(np.linspace(0, 1, len(data_dict)))

for idx, (freq, (vb_set, theta)) in enumerate(sorted(data_dict.items())):
    plt.plot(vb_set, theta, 
             color=colors[idx], 
             label=f'{freq} Hz',
             linewidth=1.5)

plt.xlabel('Vb_set (V)', fontsize=12)
plt.ylabel('theta_1ω (deg)', fontsize=12)
plt.title('Phase (theta_1ω) vs Bias Voltage (Vb_set) at Different Frequencies', fontsize=14)
plt.grid(True, linestyle='--', alpha=0.6)
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', title='Frequency')
plt.tight_layout()
plt.show()

# 可选：绘制三维图
fig = plt.figure(figsize=(12, 8))
ax = fig.add_subplot(111, projection='3d')

for freq, (vb_set, theta) in data_dict.items():
    ax.plot(vb_set, [freq]*len(vb_set), theta, 
            linewidth=1.5, 
            label=f'{freq} Hz')

ax.set_xlabel('Vb_set (V)', fontsize=10)
ax.set_ylabel('Frequency (Hz)', fontsize=10)
ax.set_zlabel('theta_1ω (deg)', fontsize=10)
ax.set_title('3D Phase-Frequency-Bias Relationship', fontsize=14)
plt.legend(bbox_to_anchor=(1.1, 1), loc='upper left')
plt.tight_layout()
plt.show()