# 面向 AI 加密市场分析的条件化自适应世界模型

## ——理论框架及其在 EvoQuant 上的实证验证

**李国聪**  
（SCI 投稿对应中文说明稿，日期：2026 年 8 月 3 日）

**英文题名：** Regime-Conditional Adaptive World Models for AI Cryptocurrency Market Analysis: Theory and Empirical Validation on EvoQuant

> 正式投稿以英文 SCI 稿为准：`pdf/sci/main_acwmi_sci.tex` / `pdf/sci/main_acwmi_sci.pdf`。

---

## 叙事顺序（必须遵守）

1. **先提出理论**：RCA-WM / ACWMI / 条件化编译 / 降级拒绝  
2. **再用项目证明**：EvoQuant（43 域 / 13 带 / 39 逻辑模块 / 生产 WMI）仅作为实证系统  
3. **不是**“项目提出理论，论文整理项目”

---

## 摘要

AI 市场分析失败，往往不是因为预测器不够强，而是因为喂给模型的市场世界不完整、不新鲜或不诚实。本文**首先提出**条件化自适应世界模型（RCA-WM）理论：定义从异步多源观测到 AI 可见世界对象的编译算子，并提出由层级宽度、稳定性、连续诚实性、信号完整性与跨证据一致性构成的加权几何质量指数 ACWMI；同时把降级感知的拒绝判断写入世界模型契约。随后，本文以开源系统 **EvoQuant** 作为**实证验证平台**（非理论来源），在 1800 个资产—日、含植入结构事件的面板上检验理论。结果显示：清算级联检测 F1=0.895，危机检测 F1=0.793，粗粒度体制匹配 71.6%；相对生产基线 WMI 阈值，AC 拒绝策略把危机期不安全行动率从 81% 降到 0。理论贡献是 RCA-WM/ACWMI；EvoQuant 只提供项目级证明。

**关键词：** AI 市场世界模型；条件化编译；质量治理；拒绝判断；加密货币；data-centric AI

---

## 1. 理论贡献（先行）

| 理论对象 | 含义 |
| --- | --- |
| 编译算子 \(\Pi_t^{(r,m)}\) | 把原始信息滤子编译为 AI 主视图 |
| 层级宽度 \(B^{hier}\) | 域 / 带 / 资产就绪 |
| 连续诚实性 \(H^{cont}\) | 奖励剔除、惩罚污染 |
| 信号完整性 \(S\) | 半衰期 / 拥挤 / 惊奇度 |
| 一致性 \(C\) | 多证据方向一致 |
| ACWMI | \(\{B,U,H,S,C\}\) 的体制条件加权几何平均 |
| 拒绝规则 | 随 ACWMI、冲突与降级层级自适应 |

## 2. 实证系统（后置证明）

EvoQuant 用于证明理论可实例化、可计算、可检验：

| 证明材料 | 数值 |
| --- | ---: |
| 数据域 | 43 |
| 逻辑模块 | 39 |
| 审计证据带 | 13 |
| 生产基线 | \(\mathrm{WMI}=B\times U\times H\) |

复现：

```bash
PYTHONPATH=. python3 pdf/sci/run_paper_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
```

## 3. 主要验证结果

| 指标 | 结果 |
| --- | --- |
| Cascade F1 | 0.895 |
| Crisis F1 | 0.793 |
| Regime match | 71.6% |
| 危机 unsafe（基线 WMI） | 81% |
| 危机 unsafe（AC 理论策略） | 0% |

## 4. 一句话结论

**理论在前，项目在后**：RCA-WM/ACWMI 是论文提出的科学对象；EvoQuant 是用来证明该理论的可运行证据。
