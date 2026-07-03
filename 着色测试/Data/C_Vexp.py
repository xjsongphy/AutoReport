import pandas as pd
import numpy as np

# 读取数据文件，跳过注释行
df = pd.read_csv("D:\大二下\近代物理实验\C-V法\\2300011419_2025-05-14 - txt\D_5 C-V_C-Vb_16h24m01s_1.txt", comment='#', sep=',', encoding='utf-8')

# 提取V_b（使用设定的Vb_set）和R_1ω的测量值
Vb = df['Vb_set(V)'].values
R = df['R_1ω(V)'].values

# 定义公式参数
k = 0.8304  # 单位：pF/μV
b = -2.651  # 单位：pF

# 将R从伏特转换为微伏，并计算C
R_microV = R * 1e6  # 1 V = 1e6 μV
C = k * R_microV + b  # 单位：pF
c = 1/C 
# 计算dC/dV_b（使用中心差分法）
dC_dVb = np.gradient(C, Vb)
#计算杂质浓度N
N = -C**3/dC_dVb
# 构建结果表格
result_df = pd.DataFrame({
    'V_b (V)': Vb,
    'C (pF)': C.round(3),  # 保留3位小数
    'dC/dV_b (pF/V)': dC_dVb.round(3),
    'w': c.round(4),
    'N':N
})

# 打印结果
print(result_df.to_string(index=False))