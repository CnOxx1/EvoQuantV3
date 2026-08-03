# 中文论文包（`pdf/cn/`）

本目录存放 ACWMI / RCA-WM 论文的**中文版本**与中文说明稿。  
英文 SCI/JF 正式稿在 `pdf/sci/`；原论文源材料在 `pdf/original/`。

## 文件

| 文件 | 说明 |
| --- | --- |
| `main_cn_acwmi.md` | 中文说明稿（Markdown 源） |
| `main_cn_acwmi.pdf` | 由中文 Markdown 生成的 PDF |
| `main_cn_acwmi.txt` | 纯文本导出 |
| `main_cn_acwmi_sci.pdf` | 英文 SCI 稿镜像（便于中文包内对照） |
| `generate_cn_pdf.py` | 中文 PDF 生成脚本 |

## 生成中文 PDF

```bash
PYTHONPATH=. python3 pdf/cn/generate_cn_pdf.py
```

## 与英文稿的关系

- 正式投稿以英文为准：`pdf/sci/main_acwmi_sci.tex` / `pdf/sci/main_acwmi_sci.pdf`
- 中文稿用于国内交流、说明与叙事对齐，不替代英文投稿正文
