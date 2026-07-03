# Markdown 语法着色测试文件

颜色注释格式: `← 应显示为 XXX 色`

---

## 标题 (md_heading: 深色 #569CD6 / 浅色 #800000)

以下标题的 `#` 标记及标题文字应显示为蓝色/深红色：

# H1 一级标题          ← # 标记 + 标题文字 → md_heading 蓝色/深红色
## H2 二级标题         ← ## 标记 + 标题文字 → md_heading 蓝色/深红色
### H3 三级标题        ← ### 标记 + 标题文字 → md_heading 蓝色/深红色
#### H4 四级标题       ← #### 标记 + 标题文字 → md_heading 蓝色/深红色
##### H5 五级标题      ← ##### 标记 + 标题文字 → md_heading 蓝色/深红色
###### H6 六级标题     ← ###### 标记 + 标题文字 → md_heading 蓝色/深红色

---

## 水平线 (md_hr: 深色 #6A9955 / 浅色 #008000)

上面和下面的 `---` 应显示为绿色（与注释同色）：

---                       ← --- 水平线 → md_hr 绿色

***

___                      ← ___ 和 *** 也是水平线 → md_hr 绿色

---

## 粗体 (md_bold: 深色 #569CD6 / 浅色 #000080)

**双星号粗体**             ← **...** 整体 → md_bold 蓝色/深蓝色
__双下划线粗体__           ← __...__ 整体 → md_bold 蓝色/深蓝色

## 斜体 (md_italic: 深色 #569CD6 / 浅色 #000080)

*单星号斜体*               ← *...* 整体 → md_italic 蓝色/深蓝色
_单下划线斜体_             ← _..._ 整体 → md_italic 蓝色/深蓝色

## 粗斜体组合

**_星号粗斜体_**           ← 最外层 ** → md_bold，内层 * → md_italic
*__下划线粗斜体__*         ← 最外层 * → md_italic，内层 __ → md_bold
***三星号粗斜体***         ← QScintilla 可能将 *** 视为粗体+斜体

## 删除线 (md_strikethrough: 深色 #808080 / 浅色 #555555)

~~这段文字已删除~~         ← ~~...~~ 整体 → md_strikethrough 灰色

## 行内代码 (md_code: 深色 #CE9178 / 浅色 #0451A5)

单反引号 `np.array([1, 2, 3])`  ← `...` 整体 → md_code 橙色/蓝色

双反引号 `` `nested` ``       ← `` `...` `` 用于包裹含反引号的内容 → md_code

## 链接 (md_link: 深色 #4CB9FF / 浅色 #0451A5)

[AutoReport 仓库](https://github.com/xjsongphy/AutoReport)
 ← [方括号链接文字] → md_link 亮蓝/蓝色
 ← (圆括号URL) 由 QScintilla 处理

引用式链接: [参考标签][ref1]
 ← [参考标签] → md_link，[ref1] → md_link

[ref1]: https://example.com
 ← 链接定义中的 [ref1] → md_link

## 图片语法

![图片替代文字](image.png)
 ← ! 和 [] 和 () 由 QScintilla 各自处理，[] 内文字可能为 md_link

## 无序列表 (md_list: 深色 #6796E6 / 浅色 #0451A5)

以下 `-` `*` `+` 标记应显示为亮蓝色：

- 减号列表项             ← - 标记 → md_list 亮蓝
- 减号列表项二           ← - 标记 → md_list 亮蓝
  - 嵌套减号列表         ← - 标记 → md_list 亮蓝
* 星号列表项             ← * 标记 → md_list 亮蓝
+ 加号列表项             ← + 标记 → md_list 亮蓝

## 有序列表 (md_list: 深色 #6796E6 / 浅色 #0451A5)

以下数字及 `.` 标记应显示为亮蓝色：

1. 有序列表第一项        ← 1. 标记 → md_list 亮蓝
2. 有序列表第二项        ← 2. 标记 → md_list 亮蓝
   1. 嵌套有序列表       ← 1. 标记 → md_list 亮蓝
3. 有序列表第三项        ← 3. 标记 → md_list 亮蓝

## 引用 (md_quote: 深色 #6A9955 / 浅色 #008000)

以下 `>` 标记应显示为绿色：

> 这是一段引用文字       ← > 标记 → md_quote 绿色
>
> 引用可以有多行         ← > 标记 → md_quote 绿色
> 和多段                 ← > 标记 → md_quote 绿色
>> 嵌套引用              ← >> 标记 → md_quote 绿色

## 转义字符

反斜杠转义: \*这不是斜体\* \`这不是代码\` \# 不是标题
 ← 反斜杠和紧随的转义字符 → 正文色 editor_fg

## HTML 实体

版权符号: &copy;  注册商标: &reg;  与号: &amp;
 ← HTML 实体通常为正文色 editor_fg

---

## 围栏代码块 (嵌入语言语法高亮)

### Python 代码块
```python
import numpy as np
# ↑ import → syntax_keyword 紫色，numpy → editor_fg

def hello(name: str) -> str:
    """测试 Python 语法高亮"""
    # ↑ def → syntax_keyword，hello → syntax_function 金色
    # ↑ """...""" → syntax_string 橙色
    return f"Hello, {name}!"
    # ↑ return → syntax_keyword，f"..." → syntax_string

data = np.array([1, 2, 3])
# ↑ 1, 2, 3 → syntax_number 浅绿

print(hello("World"))
# ↑ print → syntax_function 金色
```

### JSON 代码块
```json
{
    "name": "AutoReport",
    "version": "0.1.0",
    "python": ">=3.12",
    "dependencies": {
        "PyQt6": "^6.0",
        "numpy": "^1.24"
    }
}
```

### YAML 代码块
```yaml
name: AutoReport
version: "0.1.0"
dependencies:
  - PyQt6>=6.0
  - numpy>=1.24
```

---

## 混合场景 — 来自实际报告

根据实验数据，**噪声抑制效果**在 $T_c = 1000\ \rm ms$ 时最佳，
 ← **...** → md_bold 蓝色，`$...$` 无 markdown 语义 → 正文色

$\sigma \propto 1/\sqrt{T_c}$ 符合理论预期。详见 *数据手册* 第 3 章。
 ← *...* → md_italic 蓝色

### 引用中嵌套格式

> **注意**：`time_constant` 参数的单位为毫秒（ms），
> ~~旧版使用秒（s）~~ 新版已统一。
 ← > → md_quote 绿色，** → md_bold 蓝色，` → md_code 橙色，~~ → md_strikethrough 灰色

### 列表中嵌套格式

- 任务一：完成 `calibration.py` 脚本 ← - → md_list 亮蓝，` → md_code 橙色
- 任务二：绘制 **C-V 曲线图**            ← - → md_list 亮蓝，** → md_bold 蓝色
- 任务三：撰写 *results.tex*             ← - → md_list 亮蓝，* → md_italic 蓝色

### 行内代码中的特殊字符

下面这行测试行内代码中的 Markdown 语法不应被解析：
`**这不是粗体** *这也不是斜体* [不是链接](url) ~~不是删除线~~`
 ← 反引号内全部 → md_code 橙色/蓝色，无其他颜色
