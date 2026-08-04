# 从“模型优先”到“世界模型优先”：面向 AI 市场分析的加密货币数据世界模型基础设施

**李国聪**  
独立研究者 · lmu151638@gmail.com  

> 本稿主题对齐原论文 `pdf/original/main_cn_core.pdf`（World-Model-First）。  
> 理论对象经 RCA-WM / ACWMI 形式化；EvoQuant 是可复现的实证仪器，不是理论来源。  
> 英文配套：`pdf/sci/main_jf_rfs.tex`。复现：`make paper-lab`（需 `DB_SPLIT_ENABLED=1`）。

---

## 摘要

对于需要持续理解市场状态、形成条件判断并输出可审计结论的智能系统而言，能力上限往往并不首先受模型复杂度约束，而首先受制于其所面对的市场世界是否足够宽、足够稳、足够诚实。围绕“多数 AI 交易系统失败，并非因为模型不够聪明，而是因为喂给模型的市场世界观过于单薄”这一命题，本文将项目界定为面向 AI 市场分析的**数据世界模型基础设施**，而非收益预测器或自动交易引擎。

本文构建从潜在市场状态到 AI 可见世界对象的形式框架：以宽度 $B_t$、稳定性 $U_t$、诚实性 $H_t$ 定义世界模型质量，给出生产基线 $\mathrm{WMI}_t$ 与体制条件指数 $\mathrm{ACWMI}_t$，并引入编译算子、ECP、MIG、可用性冲击识别 DAG、贝叶斯弃权与解释质量指标 EAR/UCR/EV。

在 400 天 × 10 资产的真实多带 PIT 面板上，我们将 vintage 安全的宏观风险状态与 stablecoin 流动性**内容**直接写入完全透明的行动规则。结果显示：带内容机制相对动量的 OOS 确定性等价收益 $\Delta\mathrm{CE}=0.334$（块 bootstrap $p=0.034$）；删除 macro / alternative 带显著摧毁价值（$p=0.010/0.008$），且**内容通道主导**；2017–2026 长回测显示同一规则对动量无无条件优势——证明显著收益负载在编译后的带内容上。项目核心价值在于通过 `latest_*`、质量门控、主/诊断视图分离、八证据带 bundle 与时间治理，降低世界模型误差并提高 AI 结论的可审计性。

**关键词：** AI 市场世界模型；加密货币；数据基础设施；市场微观结构；信息集；质量治理  
**JEL：** G10, G17, C55, C82, O33

---

## 1. 引言

### 1.1 研究背景

公开叙事常把 AI 交易失败归因于模型不够先进或提示词不够精细。对承担市场分析任务的智能系统而言，真正决定分析边界的，不只是函数逼近能力，更是市场世界是否完整、及时、可信。

加密市场使这一问题一阶化：相同价格路径在不同交易所结构、杠杆拥挤、资金费率、期权墙、解锁周期与宏观背景下，可对应不相容状态。仅观察 K 线得到的是价格轨迹而非市场结构；仅读新闻得到的是叙事噪声而非执行约束；仅面对历史大表也未必得到“此刻市场是什么样”的在线世界对象。

本文因此提出更底层的问题：**如何为 AI 构建足够宽、稳、诚实的市场世界模型，使其输入空间更接近真实市场的多层结构？**

### 1.2 研究对象与定位

当前项目不是单纯抓取脚本，也不是已闭环的自动交易系统。基于文档与代码，我们将其定位为面向 AI 的加密市场**数据基础设施**：

1. 持续采集交易、宏观、链上、新闻、期权、供给与替代数据；  
2. 对异构数据标准化、落库、快照同步与质量治理；  
3. 在逻辑层将分散观测重组为 AI 可直接消费的结构化市场上下文。

研究问题不是“代码库能否直接产生超额收益”，而是：项目如何把真实市场映射为适合 AI 消费的数据世界模型？相较于薄信息输入，厚世界模型带来哪些信息论与决策论优势？分层架构、`latest_*`、质量门控与主/诊断分离分别解决什么？该角色应如何被学术化度量？

### 1.3 贡献

1. **问题前移**：把 AI 失败原因从模型层前移到观测层与数据治理层，强调世界模型构造错误是一等错误。  
2. **形式化对象**：将“足够宽、稳、诚实的数据世界模型”提升为可识别、可评估的学术对象（WMI/ACWMI、编译算子、ECP/MIG、弃权）。  
3. **工程—理论映射**：把模块化采集、快照、门控、bundle 与调度矩阵映射为世界模型生成器。  
4. **可执行实证**：在真实多带 PIT 上完成薄/厚对比、可分解 LOBO 与长回测外部有效性锚，并补充图表包（图 1–15）。

### 1.4 结构

第二节文献定位；第三节理论框架；第四节项目作为世界模型生成系统；第五节对 AI 分析的作用；第六节识别与评估设计；第七节主要结果与图表；第八节对话与局限；第九节结论。

---

## 2. 文献综述与理论定位

### 2.1 资产定价中的条件信息集

Fama–French 与 Cochrane 的框架依赖相对稳定、结构清晰的信息世界。加密市场中交易所分裂、执行摩擦、funding、basis、爆仓、期权拥挤、链上迁移与供给冲击，使单一价格序列难以代表真实状态。用过薄信息集逼近高维动态世界，是系统性设定错误。

### 2.2 机器学习金融中的高维扩张

更丰富特征可提高样本外统计预测能力，但也加剧数据挖掘与多重检验风险。本文不首先把“更多特征”理解为模型优势，而把**特征如何被治理、时间对齐与质量门控**本身当作研究对象。

### 2.3 微观结构、测量误差与鲁棒决策

Makarov–Schoar 强调跨所摩擦；Liu–Tsyvinski–Wu 识别加密共同风险因子。测量误差与鲁棒控制文献指出：延迟、噪声与不可靠信息世界会偏移估计与决策。本项目在数据层显式管理观测延迟、质量降级与语义错位，为 AI 构造更可靠的信息表面。

### 2.4 data-centric AI

data-centric AI 强调通过数据质量与覆盖度提升表现。本文将该思想延伸到**持续更新、跨来源、跨频率的市场观测世界**，而非静态标签集。

---

## 3. 理论框架：从潜在市场状态到 AI 可见世界

### 3.1 潜在状态与观测层

设真实但不可完全观测的市场状态为 $S_t$。AI 可用的是观测算子作用后的结果：
\[
X_{j,t}=h_j(S_t)+\nu_{j,t},\qquad j=1,\ldots,J.
\]
模型优先思路直接讨论 $\hat y_{t+1}=f(X_{1,t},\ldots,X_{J,t})$，却略去观测是否完整、可比较、过期或适入主视图。世界模型优先在 $f$ 之前加入生成函数：
\[
W_t=G\bigl(\{X_{j,\tau}\}_{j\le J,\tau\le t},\,Q_t,\,R_t,\,A_t\bigr),
\]
其中 $Q_t$ 为质量标记，$R_t$ 为 AI-ready 门控，$A_t$ 为时间对齐与聚合。AI 实际处理的是 $W_t$。

### 3.2 宽度、稳定性、诚实性与 WMI

**定义（宽度）**
\[
B_t=\frac{1}{K}\sum_{k=1}^{K}a_{k,t}.
\]
**定义（稳定性）**
\[
U_t=\exp\!\Big(-\sum_{j=1}^{J}\omega_j d_{j,t}\Big).
\]
**定义（诚实性）**
\[
H_t=1-\frac{1}{J}\sum_{j=1}^{J}m_{j,t}.
\]
生产基线：
\[
\mathrm{WMI}_t=B_t\times U_t\times H_t.
\]
层级宽度与连续诚实性用于 ACWMI：
\[
B^{\mathrm{hier}}_t=0.25\,B^{\mathrm{dom}}_t+0.35\,B^{\mathrm{band}}_t+0.40\,B^{\mathrm{asset}}_t,
\]
\[
H^{\mathrm{cont}}_t=\exp(-2c_t)\max\bigl(0,\,1-0.5(1-e_t)\bigr).
\]

### 3.3 认识论观测对象

\[
O_{j,t}=(x_{j,t},\,\tau_{j,t},\,q_{j,t},\,g_{j,t},\,r_{j,t}).
\]
AI 消费的是带时间、质量、门控与角色的对象集合，而非平面特征矩阵。

### 3.4 异步状态与时滞误差界

$S_{t+1}=F(S_t,\eta_{t+1})$。来源观测 $X^{\mathrm{obs}}_{j,t}=h_j(S_{t-\ell_{j,t}})+\nu_{j,t}$。若 $h_j$ Lipschitz，则重建误差可分解为时滞、噪声与缺失三项：
\[
\|\widetilde S_t-S_t|
\le C_1\sum_j\omega_j\ell_{j,t}
+C_2\sum_j\omega_j\|\nu_{j,t}\|
+C_3\sum_j\omega_j(1-z_{j,t}).
\]
`latest_*`、freshness/TTL 与 `is_ready_for_ai` 正是压缩这三项的工程对应物。

### 3.5 信息滤子与编译算子

\[
\mathcal{F}^{\mathrm{raw}}_t=\sigma\bigl(\{X^{\mathrm{obs}}_{j,\tau}\}\bigr),\qquad
\mathcal{F}^{\mathrm{AI}}_t=\sigma(W^{\mathrm{AI}}_t,D_t),
\]
\[
\Pi_t=\mathcal{B}_t\circ M_t\circ A_t,\qquad
W^{\mathrm{AI}}_t=\Pi_t(\mathcal{F}^{\mathrm{raw}}_t).
\]
**命题 1（编译 ≠ 特征扩展）**：扩大 raw 跨度而无良好 $\Pi_t$，不必扩大决策相关的 $\mathcal{F}^{\mathrm{AI}}$；未门控滞后源可抬高 span 却压低 $UH$。  
**命题 2（SDF 接口）**：可实施定价陈述只能条件于 $\mathcal{F}^{\mathrm{AI}}_t$；对 raw 滤子度量的 alpha 含编译楔。

### 3.6 ECP、MIG 与识别 DAG

\[
\mathrm{ECP}_t=\mathbf{1}\{\mathrm{conf}_t>\bar c\}\,\mathbf{1}\{\mathrm{WMI}_t<w\},
\]
\[
\mathrm{MIG}^{(m)}_{k,t}=I(R^{(m)}_t;E_{k,t}\mid I^{(-k)}_t).
\]
可用性冲击 $O_t$ 优先识别：$O_t\to W_t\to A_t$，模型 $M_t$ 与混淆 $C_t$ 进入 $W_t,A_t$。

### 3.7 贝叶斯弃权与 ACWMI

动作集 $\mathcal{A}=\{\mathrm{bullish},\mathrm{bearish},\mathrm{neutral},\mathrm{abstain}\}$：
\[
a^\star_t=\arg\min_{a}\mathbb{E}[\ell(a,R_t)\mid W_t],
\]
当所有非弃权动作期望损失高于 $c_{\mathrm{abs}}(W_t)$ 时弃权。体制条件指数：
\[
\mathrm{ACWMI}_t
=\exp\!\left(
\frac{\sum_{i=1}^{5}\gamma_i(r_t)\log x_{i,t}}{\sum_{i=1}^{5}\gamma_i(r_t)}
\right),
\quad
x_t=(B^{\mathrm{hier}}_t,U_t,H^{\mathrm{cont}}_t,S_t,C_t).
\]
解释质量：
\[
\mathrm{EAR}_t=\frac{\#\{\text{绑定证据的判断}\}}{\#\{\text{总判断}\}},\quad
\mathrm{UCR}_t=1-\mathrm{EAR}_t,\quad
\mathrm{EV}_t=\frac{d(\Phi_t,\Phi_{t-1})}{1+d(W_t,W_{t-1})}.
\]

### 3.8 LOBO 即经济 MIG（含通道分解）

固定规则下 $V(I)$ 为 OOS CE，$\widehat{\mathrm{MIG}}_k=V(I)-V(I\setminus E_k)$。带 $k$ 经**内容通道**（改变行动方向/激活）与**门控通道**（改变 $B,U,H$ 与弃权）进入决策；PIT 上 tilt 置零实现内容删除、状态置 missing 实现门控删除。

---

## 4. 项目作为世界模型生成系统

### 4.1 分层架构

数据层采集 → SQLite 历史 / `latest_*` 快照 → 逻辑层 readiness 与 `ai_market_context` bundle → API。图 14 给出 World-Model-First 流水线：原始证据带经治理编译为 $W_t$，再进入 AI 判断与弃权。

### 4.2 八证据带

| 证据带 | 角色 |
| --- | --- |
| exchange | 行情、订单簿、funding、爆仓、持仓、basis |
| macro | DXY、VIX 等宏观风险偏好 |
| news / event_calendar | 叙事与日程 |
| onchain | TVL 与链上资本流 |
| tokenomics | 解锁与供给压力 |
| options | 隐含波动与 Gamma 墙 |
| alternative | 稳定币净供给等替代流动性 |

### 4.3 latest_*、门控与 bundle

`latest_*` 提供“此刻世界对象”；`health_status` / `quality_flag` / `is_ready_for_ai` 决定主视图准入；bundle 聚合八带并附 `coverage_score`、`risk_flags` 与 `evidence`。主视图与诊断视图分离，防止未治理 raw 污染 AI 主路径。

### 4.4 生产接口（仪器化）

本研究调用：`BandPITService`、`load_availability_shocks`、可配置 `WORLD_MODEL_INDEX_MODE` / 弃权阈值。叙事顺序：**先理论，后项目**。

---

## 5. 对 AI 市场分析的作用

厚世界模型并不直接“给出答案”，而是：（i）降低世界模型误差；（ii）压缩伪解释自由度；（iii）使结论可审计（evidence 绑定）；（iv）在世界薄或不诚实时正当化弃权。薄世界高置信正是 ECP 设计要捕捉的状态。

---

## 6. 识别与评估设计

### 6.1 数据

真实多带 PIT：2025-06-30 → 2026-08-03，400 天 × 10 资产 = 4000 行。耐久带 ready 率：exchange ≈ 1.0，macro = 1.0，alternative = 1.0；news/onchain/options/tokenomics 多为采集日右删失（图 11）。

### 6.2 设计

- IS/OOS 切点：2026-01-16（200/200 天）  
- 阈值仅在 IS 冻结；生产 WMI$=0.2$ 不调参  
- 经济价值：年化收益/波动、Sharpe、CRRA CE（$\gamma=2$）、最大回撤  
- 推断：循环块 bootstrap（$n=999$，块长 5；敏感性 {5,10,21}）  
- 识别：薄 vs 厚；耐久带 LOBO（内容+门控）；稀缺世界事件研究；长回测锚  

### 6.3 透明机制（带内容进入行动）

方向仓位是确定性规则（无隐层）。带内容直接进入映射，PIT 不 ready 时强制为 0：

- $\mathrm{macro\_tilt}$：vintage 安全的 VIX/DXY 5 日变化  
- $\mathrm{alt\_tilt}$：stablecoin 7 日净供给符号  
- R1：crisis **且** cascade$≥0.60$ → 做空（证据合取）  
- R2/R2b/R3：宏观否决、带驱动做多、动量回退与双带 risk-off 否决  

长回测审计曾暴露 harness 缺陷（危机吸收态、cascade 饱和）；修复为 60 日窗口与波动率标准化尾部强度后披露，非 OOS 搜索。

---

## 7. 主要结果

### 7.1 流水线与世界质量路径

图 14 展示编译流水线；图 12 给出 WMI/ACWMI 在 PIT 面板上的路径及 IS/OOS 切点；图 3（实验包）给出 cascade 与一致性 $C$ 的伴随路径；图 11 显示耐久带持续 ready、稀缺带右删失。

### 7.2 OOS 经济价值：带内容显著优于动量

| 策略 | 年化收益 | Sharpe | CE | 最大回撤 | 弃权率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Always long | −0.816 | −1.399 | −1.157 | −0.466 | 0 |
| Momentum | 0.051 | 0.101 | −0.202 | −0.500 | 0 |
| Mechanism / Thick（带内容） | 0.385 | 0.767 | 0.132 | −0.438 | 0.075 |
| WMI$<0.2$ | 0 | 0 | 0 | 0 | 1.000 |
| ACWMI (IS-frozen) | 0.385 | 0.767 | 0.132 | −0.438 | 0.075 |

**Mechanism − Momentum：$\Delta\mathrm{CE}=0.334$，$p=0.034$，95% CI 排除 0。**  
图 1：OOS 累计财富；图 2：Sharpe/CE 条形对比。两策略共享收益率输入、仅差 vintage 宏观/替代内容——按构造隔离编译带内容的价值。

### 7.3 厚 vs 薄世界

| 世界 | Mean $B$ | Mean $H$ | Sharpe | CE | 弃权率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 薄（仅 exchange） | 0.201 | 0.562 | −0.850 | −0.388 | 0.454 |
| 厚真实 PIT | 0.356 | 0.688 | 0.767 | 0.132 | 0.075 |

$\Delta$Sharpe $=1.62$（$p=0.044$）；$\Delta$CE $=0.52$（$p=0.22$，200 天尚不显著）。见图 6 / 图 15。

### 7.4 LOBO：显著且由内容通道驱动

| 带 | ΔCE 总 | $p$ | ΔCE 内容 | $p$ | ΔCE 门控 | $p$ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| exchange | −0.056 | 0.394 | — | — | −0.056 | 0.394 |
| macro | −0.418 | 0.010 | −0.334 | 0.034 | −0.066 | 0.026 |
| alternative | −0.402 | 0.008 | −0.334 | 0.034 | −0.040 | 0.044 |

图 4 / 图 9：带信息改变的是**交易什么**，而不仅是**何时弃权**。

### 7.5 长回测外部有效性锚

同一规则（2025 前 tilt=0）在 BTC/ETH 2017–2026（3471 天）上：年化 0.456、Sharpe 0.664，但对动量无显著优势（$\Delta\mathrm{CE}=0.017$，$p=0.55$）。图 10：日历年回报。收益率核心无隐藏 alpha ⇒ 7.2–7.4 的显著收益负载在编译带内容上。

### 7.6 成本、funding 与推断稳健性

图 13：10bps 下 Mechanism Sharpe 0.467（CE −0.019 vs 动量 −0.352）；25bps 下排序不变；funding 调整 CE 变动 $<0.005$。块长敏感性稳定；White (2000) reality check $p=0.144$（菜单级诚实披露）。$B^{\mathrm{hier}}$ 权重扰动 CE 三位小数不变。实测 ECP $=0.688$，EAR $=1$。

### 7.7 图表索引

| 图 | 内容 |
| --- | --- |
| 1 | OOS 累计财富 |
| 2 | 策略 Sharpe / CE |
| 3 | WMI/ACWMI 与 cascade/$C$ 路径 |
| 4 | LOBO 边际 CE |
| 5 | 稀缺世界事件研究 |
| 6 / 15 | 薄 vs 厚 |
| 7 | 弃权—价值前沿 |
| 8 | IS/OOS 稳定性 |
| 9 | LOBO 内容/门控分解（新） |
| 10 | 长回测分年（新） |
| 11 | 带 readiness 时间路径（新） |
| 12 | WMI/ACWMI PIT 路径（新） |
| 13 | 交易成本敏感性（新） |
| 14 | World-Model-First 流水线（新） |

---

## 8. 对话、局限与议程

### 8.1 与资产定价 / ML / data-centric AI

本文将 Fama–French / Cochrane 的信息集前提前移为可工程化的编译问题；与 ML 文献共享样本外纪律，但对象是世界质量而非预测器复杂度；与 data-centric AI 共享“数据优先”，对象是动态市场观测世界。

### 8.2 局限

1. 带内容 vintage 主要覆盖当前 PIT 窗口；news/onchain/options/tokenomics 右删失。  
2. 自然硬中断稀少；稀缺世界用 $B^{\mathrm{hier}}$ 底五分位代理。  
3. 十个标的、约 400 交易日——截面与日历需扩展。  
4. 分析库历史快照仍稀疏；纯 `time_slice` 回放需每日落盘 readiness / AI-context。

### 8.3 终稿议程

多年持续采集；强化 `collection_runs` / 中断日志；每日快照；扩展截面；stationary bootstrap 与损失函数变体——同时不得压缩形式化证明链。

---

## 9. 结论

世界模型优先把 AI 市场分析的瓶颈从“模型是否够聪明”改写为“市场世界是否够宽、稳、诚实”。本文将市场世界模型提升为可形式化、可识别、可评估的学术对象，并在真实多带 PIT 上完成可分解识别：**带内容显著优于动量（$p=0.034$）；LOBO macro/alternative 显著（$p=0.010/0.008$）且内容通道主导；长回测证明规则本身无隐藏 alpha**——恰是编译理论预测的模式。EvoQuant 的价值不在直接给出交易答案，而在于为 AI 提供可审计的厚世界。

---

## 附录 A. 符号

| 符号 | 含义 |
| --- | --- |
| $S_t$；$X_{j,t}$；$O_{j,t}$ | 潜在状态；观测；认识论对象 |
| $B_t,U_t,H_t$；$\mathrm{WMI}_t$/$\mathrm{ACWMI}_t$ | 宽度/稳定性/诚实性；质量指数 |
| $\Pi_t$；$W^{\mathrm{AI}}_t$ | 编译算子；AI 可见世界 |
| $\mathrm{ECP},\mathrm{MIG}$ | 校准惩罚；边际信息增益 |
| EAR/UCR/EV | 解释质量 |
| $O_t$ | 可用性冲击（DAG） |

## 附录 B. 复现

```bash
export DB_SPLIT_ENABLED=1   # 使用 exchange/market/analytics 域库
make paper-lab
PYTHONPATH=. python3 pdf/sci/generate_core_figures.py
PYTHONPATH=. python3 pdf/sci/generate_core_manuscript_pdf.py
```

面板：`pdf/data/pit_multiband_panel.csv`  
结果：`pdf/sci/EXPERIMENT_RESULTS.md`  
图表：`pdf/figures/fig1_*.png` … `fig15_*.png`

## 参考文献（精选）

Asness–Moskowitz–Pedersen (2013); Cochrane (2005); Fama–French (1992, 1993, 2015); Fuller (1987); Gu–Kelly–Xiu (2020); Hansen–Sargent (2008); Harvey–Liu–Zhu (2016); Jegadeesh–Titman (1993); Kelly–Pruitt–Su (2019); Liu–Tsyvinski–Wu (2022); Makarov–Schoar (2020); Nagel (2021); Shmueli (2010); Carroll et al. (2006).
