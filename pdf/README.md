# 论文包：完整 JF/RFS 工作论文 + 真实多带 PIT

## 完整顶刊稿（主入口）

| 语言 | 源文件 | PDF |
| --- | --- | --- |
| **英文** | `pdf/sci/main_jf_rfs.tex` | `pdf/sci/main_jf_rfs.pdf` |
| **中文** | `pdf/cn/main_cn_jf.md` | `pdf/cn/main_cn_jf.pdf` |

```bash
make paper-full
```

理论公式来自 `pdf/original/`；实证来自真实 PIT 面板 `pdf/data/pit_multiband_panel.csv`。  
EvoQuant 是实验室，不是理论来源。

## 目录

| 路径 | 内容 |
| --- | --- |
| `pdf/sci/` | 英文正式稿、实证脚本、PDF 生成 |
| `pdf/cn/` | 中文完整稿 |
| `pdf/original/` | 原论文可复用源材料 |
| `pdf/data/` | PIT 面板与收益数据 |
| `pdf/figures/` · `pdf/tables/` | 图表 |

## 复现实证

```bash
make paper-lab
# 或
PYTHONPATH=. python3 pdf/sci/bootstrap_multiband_archive.py
PYTHONPATH=. python3 pdf/sci/build_pit_archive.py
PYTHONPATH=. python3 pdf/sci/run_pit_jf_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_full_manuscript_pdf.py
```

## 关键 OOS 结果（真实 PIT）

| 结果 | 数值 |
| --- | ---: |
| Thick CE | 0.474 |
| Thin CE | −0.011 |
| LOBO ΔCE macro / alt / exchange | −0.534 / −0.526 / −0.339 |
| ACWMI Sharpe / CE | 0.901 / 0.199 |
| WMI&lt;0.2 | 100% abstain（阈值不匹配稀疏档案） |
