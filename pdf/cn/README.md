# 中文论文包（`pdf/cn/`）

完整顶刊工作论文中文稿与英文镜像。

| 文件 | 说明 |
| --- | --- |
| **`main_cn_jf.md`** | **完整中文顶刊稿**（理论公式 + 真实 PIT 实证） |
| `main_cn_jf.pdf` | 中文 PDF（有 CJK 字体时由生成脚本写出） |
| `main_jf_rfs.pdf` | 英文完整稿镜像 |
| `main_cn_theory.md` | 理论公式摘录（较短） |

英文正式 TeX：`pdf/sci/main_jf_rfs.tex`  
原论文源材料：`pdf/original/main_cn_pm.txt`

## 生成

```bash
PYTHONPATH=. python3 pdf/sci/generate_full_manuscript_pdf.py
# 或
make paper-full
```
