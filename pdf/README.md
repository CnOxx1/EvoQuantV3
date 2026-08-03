# EvoQuant 论文包（独立 SCI 稿）

本目录存放**独立成文**的 SCI 投稿材料。论文背景与实证均来自本仓库 EvoQuant 系统，不依赖任何未使用旧论文。

## 主投稿文件

| 文件 | 说明 |
| --- | --- |
| `sci/main_acwmi_sci.tex` | Elsevier `elsarticle` 英文源稿 |
| `sci/main_acwmi_sci.pdf` | 英文 SCI PDF（含图/表） |
| `main_cn_acwmi_sci.pdf` | 同上副本 |
| `main_cn_acwmi.md` | 中文说明稿 |

## 项目绑定实验

```bash
PYTHONPATH=. python3 pdf/sci/run_paper_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
```

实验脚本直接调用生产代码：

- `AIMarketContextService._compute_world_model_index`
- `RegimeClassifier` / `LiquidationCascadeCalculator` / `ContagionRiskCalculator`
- `AlphaDecayCalculator` / `FlowDecompositionCalculator` / `VolatilityCalculator`
- `DegradationManager` / `AssetReadinessService.BAND_WEIGHTS`

## 图与表

- `figures/fig1`–`fig8`
- `tables/`（含 `panel_simulation.csv`）
