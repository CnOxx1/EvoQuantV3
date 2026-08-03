# 论文包：真实多带 PIT + JF/RFS 取向

## 目录

| 路径 | 内容 |
| --- | --- |
| `pdf/sci/` | 英文 SCI/JF 正式稿与实证脚本 |
| `pdf/cn/` | **中文论文包**（说明稿 / 中文 PDF） |
| `pdf/original/` | 原论文可复用源材料 |
| `pdf/data/` | PIT 面板与收益数据 |
| `pdf/figures/` · `pdf/tables/` | 图表 |

## 本轮关键

1. **灌库**：OKX exchange / macro / alternative / news / onchain / options / tokenomics  
2. **PIT 面板**：`pdf/data/pit_multiband_panel.csv`（400 天 × 10 资产）  
3. **识别**：真实 thin vs thick + durable-band LOBO  
4. **论文**：按真实 PIT 结果重写

## 复现

```bash
# 1) 灌库（耗时；OKX-only runtime patch，不改仓库配置提交）
PYTHONPATH=. python3 pdf/sci/bootstrap_multiband_archive.py

# 2) 从历史表构建 PIT
PYTHONPATH=. python3 pdf/sci/build_pit_archive.py

# 3) 真实 PIT 实证
PYTHONPATH=. python3 pdf/sci/run_pit_jf_experiments.py

# 4) 英文 PDF
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py

# 5) 中文 PDF
PYTHONPATH=. python3 pdf/cn/generate_cn_pdf.py
```

## 关键 OOS 结果（真实 PIT）

| 结果 | 数值 |
| --- | ---: |
| Thick CE | 0.474 |
| Thin CE | −0.011 |
| LOBO ΔCE macro / alt / exchange | −0.534 / −0.526 / −0.339 |
| ACWMI Sharpe / CE | 0.901 / 0.199 |
| WMI&lt;0.2 | 100% abstain（阈值不匹配稀疏档案） |
