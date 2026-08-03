# EvoQuant 论文参考与理论扩展

本目录存放项目相关的学术论文文本与 PDF。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `main_cn_core.pdf` | 前序论文 PDF（来自 EvoQuantWeb）：《从“模型优先”到“世界模型优先”》 |
| `main_cn_acwmi.md` | **新论文** Markdown 源稿 |
| `main_cn_acwmi.pdf` | **新论文** PDF |
| `main_cn_acwmi.txt` | **新论文** 纯文本版 |
| `generate_acwmi_pdf.py` | 由 Markdown 生成 PDF 的脚本 |

## 理论演进关系

1. **第一代（前序论文）**  
   提出世界模型优先命题，定义  
   \(\mathrm{WMI}_t = B_t \times U_t \times H_t\)，  
   并形式化 `latest_*`、质量门控、主/诊断视图分离与八证据带编译。

2. **第二代（本文）**  
   针对乘积坍塌、离散诚实性、任务无关编译、扁平证据带、缺少点时与降级理论等局限，提出  
   **条件化自适应世界模型（RCA-WM）** 与  
   \(\mathrm{ACWMI}_t^{(r,m)}\)。

## 重新生成 PDF

```bash
python3 pdf/generate_acwmi_pdf.py
```
