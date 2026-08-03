# 论文包：理论先行，项目验证

叙事顺序：

1. **提出理论** RCA-WM / ACWMI  
2. **用 EvoQuant 证明**（43 域 / 13 带 / 39 逻辑模块 / 生产 WMI）  
3. 不是“项目提出理论”

## 主文件

| 文件 | 说明 |
| --- | --- |
| `sci/main_acwmi_sci.tex` / `.pdf` | 英文 SCI 正稿 |
| `main_cn_acwmi.md` | 中文说明 |

```bash
PYTHONPATH=. python3 pdf/sci/run_paper_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
```
