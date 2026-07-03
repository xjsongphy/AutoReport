import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from scipy.stats import linregress

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
# 存储数据结构：{Vb_set: {freq: theta_1ω}}
data = {}
for file in files:
    with open(file, 'r') as f:
        freq = None
        # 提取频率
        for line in f:
            if line.startswith('#\tFrequency: '):
                freq = int(line.split()[2])
                break
        # 读取数据（使用theta_1ω列）
        df = pd.read_csv(f, comment='#', sep=',', 
                        names=['time','vt','Vb_set','Vb_meas',
                               'R_1ω','theta_1ω','R_2ω','theta_2ω'])
        for _, row in df.iterrows():
            Vb = row['Vb_set']
            theta = row['theta_1ω']
            if Vb not in data:
                data[Vb] = {}
            data[Vb][freq] = theta

# 按偏压分组，计算 Cx*Rx 乘积
results = []
for Vb in sorted(data.keys()):
    freqs = []
    thetas = []
    for f, theta in data[Vb].items():
        freqs.append(f)
        thetas.append(theta)
    
    # 转换为 1/f 和 tan(theta_1ω)
    inv_f = 1 / np.array(freqs)
    tan_theta = np.tan(np.deg2rad(np.array(thetas)))  # 角度转弧度后计算正切
    
    # 线性拟合：tan(theta_1ω) = slope * (1/f) + intercept
    slope, intercept, r_value, _, _ = linregress(inv_f, tan_theta)
    
    # 计算 Cx*Rx = 1/(2π*slope)
    if slope != 0:
        CxRx = 1 / (2 * np.pi * abs(slope))
        results.append((Vb, CxRx, r_value**2))

# 转换为DataFrame便于分析
df_results = pd.DataFrame(results, columns=['Vb_set(V)', 'CxRx(s)', 'R_squared'])

# 绘制CxRx随偏压变化
plt.figure(figsize=(10, 6))
plt.plot(df_results['Vb_set(V)'], df_results['CxRx(s)'], 
         'o-', color='#d7191c', linewidth=2)
plt.xlabel('Vb_set (V)', fontsize=12)
plt.ylabel('CₓRₓ (s)', fontsize=12)
plt.title('CₓRₓ Product from θ₁ω vs Bias Voltage', fontsize=14)
plt.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()

# 显示拟合质量
print("拟合结果摘要：")
print(df_results.round(3))
plt.show()