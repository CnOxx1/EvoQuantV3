# 面向 AI 加密市场分析的条件化自适应世界模型

## ——理论框架及其在 EvoQuant 上的实证验证

**李国聪**  
（SCI 投稿对应中文说明稿，日期：2026 年 8 月 3 日）

**英文题名：** Regime-Conditional Adaptive World Models for AI Cryptocurrency Market Analysis: Theory and Empirical Validation on EvoQuant

> 正式投稿以英文 SCI 稿为准：`pdf/sci/main_acwmi_sci.tex` / `pdf/sci/main_acwmi_sci.pdf`。  
> 原论文可复用源材料：`pdf/original/`。

---

## 叙事顺序（必须遵守）

1. **先提出理论**：RCA-WM / ACWMI（吸收原 World-Model-First 论文）
2. **再用项目证明**：EvoQuant 仅作为实证系统
3. **不是**“项目提出理论，论文整理项目”

---

## 从原论文吸收并强化的内容

| 原论文对象 | 在 SCI 稿中的位置 |
| --- | --- |
| 认识论观测对象 \(O_{j,t}=(x,\tau,q,g,r)\) | §3.1 |
| 异步时滞 / Lipschitz 重建误差界 | §3.2 |
| 信息滤子 \(\mathcal{F}^{raw}\to\mathcal{F}^{AI}\) | §3.4 |
| ECP 置信校准惩罚 | §3.4 / Table 7 |
| MIG 证据带边际信息增益 | §3.4 |
| 因果 DAG + 可用性冲击 \(O_t\) | §3.5 |
| 贝叶斯拒绝判断 \(\ell(a,R_t)\) | §3.4 |
| 解释空间 \(\Phi_t\) | §3.4 |
| EAR / UCR / EV 评价套件 | §3.5 / Table 7 |
| 模块→失真校正表 | Table 3 |
| 多目标 Pareto 评价 | Fig. 7 |

---

## 摘要

AI 市场分析失败，往往不是因为预测器不够强，而是因为喂给模型的市场世界不完整、不新鲜或不诚实。本文**首先提出**条件化自适应世界模型（RCA-WM）理论：在 World-Model-First 认识论之上，定义从异步多源观测到 AI 可见世界对象的编译算子，并提出由层级宽度、稳定性、连续诚实性、信号完整性与跨证据一致性构成的加权几何质量指数 ACWMI；同时把贝叶斯拒绝判断、ECP、MIG 与 EAR/UCR/EV 多目标评价写入世界模型契约。随后，本文以开源系统 **EvoQuant** 作为**实证验证平台**（非理论来源），在 1800 个资产—日、含植入结构事件的面板上检验理论。结果显示：清算级联检测 F1=0.895，危机检测 F1=0.793，粗粒度体制匹配 71.6%；相对生产基线 WMI 阈值，AC 拒绝策略把危机期不安全行动率从 81% 降到 0；危机期 ECP 率从 0.181 降到 0.002。理论贡献是 RCA-WM/ACWMI；EvoQuant 只提供项目级证明。

**关键词：** AI 市场世界模型；条件化编译；质量治理；拒绝判断；解释可审计性；加密货币；data-centric AI

---

## 1. 理论贡献（先行）

| 理论对象 | 含义 |
| --- | --- |
| 观测对象 \(O_{j,t}\) | 值 + 时间 + 质量 + 门控 + 角色 |
| 时滞重建界 | 控制“看到过去世界”的误差 |
| 编译算子 \(\Pi_t^{(r,m)}\) | 把原始信息滤子编译为 AI 主视图 |
| 层级宽度 \(B^{hier}\) | 域 / 带 / 资产就绪 |
| 连续诚实性 \(H^{cont}\) | 奖励剔除、惩罚污染 |
| 信号完整性 \(S\) / 一致性 \(C\) | 半衰期·拥挤·惊奇 / 多证据方向一致 |
| ACWMI | \(\{B,U,H,S,C\}\) 的体制条件加权几何平均 |
| ECP / MIG / \(\Phi_t\) | 置信惩罚、边际信息、解释空间 |
| EAR/UCR/EV | 证据归因、无支撑断言、解释波动 |
| 拒绝规则 | 随 ACWMI、冲突与降级层级自适应 |

## 2. 实证系统（后置证明）

EvoQuant 用于证明理论可实例化、可计算、可检验：

| 证明材料 | 数值 |
| --- | ---: |
| 数据域 | 43 |
| 逻辑模块 | 39 |
| 审计证据带 | 13 |
| 生产基线 | \(\mathrm{WMI}=B\times U\times H\) |

复现（项目侧 paper lab，与生产 API 对齐）：

```bash
make paper-smoke
make paper-lab            # PIT → JF 实证 → PDF
make paper-lab WITH_BOOTSTRAP=1
```

生产接口：`BandPITService`（多带 PIT）、`load_availability_shocks`（\(O_t\)）、
`WORLD_MODEL_INDEX_MODE` / `ACWMI_ABSTAIN_THRESHOLD`（WMI/ACWMI）。详见 `pdf/sci/README.md`。

## 3. 主要验证结果

| 指标 | 结果 |
| --- | ---: |
| Cascade F1 | 0.895 |
| Crisis F1 | 0.793 |
| Regime match | 71.6% |
| Crisis unsafe (WMI → AC) | 81% → 0 |
| Crisis ECP (baseline → AC) | 0.181 → 0.002 |
| Crisis EAR (AC-gated) | 1.000 |
