# 论文包：面向 JF/RFS 的信息集编译研究

目标期刊路径：**Journal of Finance / Review of Financial Studies**（当前为 submission-oriented draft）。

## 叙事

1. 信息集编译是资产定价一等对象（非又一个 alpha）
2. RCA-WM / ACWMI + 可用性冲击识别
3. **真实收益** + IS 冻结阈值 + OOS 经济价值 + 强基线 + 消融
4. EvoQuant 仅作测量实验室，不是理论来源
5. 如实报告：本样本 ACWMI **不**在 CE 上优于 thick ungated

## 复现

```bash
# 若需重下行情（已缓存 pdf/data/crypto_daily_yahoo.csv）
PYTHONPATH=. python3 pdf/sci/run_jf_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
```

## 主文件

| 文件 | 说明 |
| --- | --- |
| `sci/main_acwmi_sci.tex` / `.pdf` | JF/RFS 取向英文稿 |
| `sci/run_jf_experiments.py` | 真实收益 OOS 实证 |
| `data/crypto_daily_yahoo.csv` | Yahoo 日收益缓存 |
| `original/` | 原 World-Model-First 论文源材料 |
