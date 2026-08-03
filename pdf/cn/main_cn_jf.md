# 编译市场信息集：世界模型质量、选择性预测与经济价值

**李国聪**  
独立研究者 · lmu151638@gmail.com  

> 面向 *Journal of Finance* / *Review of Financial Studies* 的完整工作论文中文稿。  
> 英文正式 TeX：`pdf/sci/main_jf_rfs.tex`。  
> 理论公式吸收自原论文：`pdf/original/main_cn_pm.txt`。  
> EvoQuant 是实证实验室，**不是**理论来源。

---

## 摘要

条件资产定价把投资者信息集当作给定。在加密市场，这一前提失效：证据跨交易所、宏观 vintage、链上、期权、解锁与新闻异步到达，且间歇不可用。本文提出金融原生的**信息集编译**理论：定义认识论观测对象、异步重建误差界、从原始滤子到 AI 可见滤子的编译算子、生产基线 WMI，以及体制条件化的 ACWMI；并形式化 ECP、MIG、可用性冲击识别 DAG、贝叶斯弃权与解释质量指标 EAR/UCR/EV。

实证上，我们在 400 天 × 10 资产（4000 资产—日）的真实 PIT 面板上，把**带内容**（vintage 安全的 VIX/DXY 宏观风险状态、stablecoin 7 日净供给流动性）直接放进完全透明的行动规则。删除 macro / alternative 带摧毁 OOS 确定性等价收益（$\Delta$CE $-0.42$ / $-0.40$；块 bootstrap $p=0.010$ / $0.008$），且**分解显示损失主要经内容通道**而非仅弃权门控。透明规则 OOS 显著胜过动量（$\Delta$CE $0.334$，$p=0.034$，CI 排除 0）；而 2017–2026 长回测显示同一规则对动量**无**无条件优势——证明收益来自编译后的带内容，而非隐藏的收益率预测器。结果经受 10bps 成本与永续 funding 调整；推断附块长敏感性与 reality check 多重检验校正。

贡献是：带证明链与 SDF 接口的编译理论 + 内容/门控可分解的 LOBO 识别协议 + 长回测外部有效性锚。局限（带内容 vintage 单窗口、右删失带、十个标的）明确列为终稿议程。

**关键词：** 信息集；选择性预测；加密货币；point-in-time；测量误差；世界模型  
**JEL：** G12, G14, C58, C55

---

## 1. 引言

现代资产定价以信息集 $I_t$ 为条件（Fama–French；Cochrane；Gu–Kelly–Xiu；Kelly–Pruitt–Su；Nagel）。文献纪律集中在“如何使用 $I_t$”，而非“如何从异步、质量异质证据**编译** $I_t$”。加密市场使编译成为一阶问题：市场分割、杠杆、期权墙、解锁、链上与宏观流动性，可使同一价格路径对应不相容状态（Makarov–Schoar；Liu–Tsyvinski–Wu）。

本文三项贡献：

1. **理论**：RCA-WM / ACWMI 与 World-Model-First 全套形式对象（观测、时滞界、编译算子、ECP/MIG/DAG、弃权、EAR/UCR/EV）。  
2. **测量实验室**：EvoQuant 作为可复现仪器（采集、readiness、BandPIT、可用性冲击查询、可配置阈值）。  
3. **真实 PIT 识别**：厚 vs 薄、耐久带 LOBO、IS 冻结阈值下的 OOS 经济价值。

---

## 2. 相关文献

- **资产定价中的信息集**：经典与 ML 定价扩展特征跨度，但通常假定同步干净面板。  
- **加密市场结构**：分割与特异风险因子，支持多带世界而非纯价格预测。  
- **选择性预测**：世界薄或不诚实时应弃权；本文将弃权成本与世界质量挂钩。  
- **测量误差与 vintage**：宏观与加密带的时效/缺失是一阶对象。

---

## 3. 理论（含 Proposition 证明链）

本稿英文 TeX 已补全证明链（非定义堆叠），单交叉与非冗余条件已形式化为 Assumption：
- **命题 1. Compilation ≠ feature expansion**（未门控滞后源可抬高 raw span 却压低 $U\!H$）
- **命题 2. SDF 接口**：可实施定价陈述只能条件于编译后滤子 $\mathbb{E}[m_{t+1}R_{t+1}\mid\mathcal{F}^{\mathrm{AI}}_t]=1$；对 raw 滤子度量的 alpha 含**编译楔** $w_t$，当且仅当 $\Pi$ 不损失定价相关信息时 $w_t\equiv0$（迭代期望 + MIG>0 构造反例；完整证明入附录）
- **命题 3. Lag reconstruction bound**（Lipschitz + 三角不等式）
- **命题 4. World-conditional abstention**（贝叶斯最优弃权；单交叉假设下弃权区为 WMI 下集）
- **命题 5. ACWMI factor monotonicity**（对数线性 + 凹性 → 单因子恶化不可被等权抵消）
- **命题 6. LOBO = 经济 MIG，含通道分解**：$\widehat{\mathrm{MIG}}_k$ 恒等分解为**内容通道**（带内容改变行动方向/激活）与**门控通道**（带可用性改变弃权）；PIT 上"tilt 置零"实现内容删除、"状态置 missing"实现门控删除，两者并施即 $I\setminus E_k$

### 3.1 宽度、稳定性、诚实性与 WMI

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

层级宽度与连续诚实性：
\[
B^{\mathrm{hier}}_t=0.25\,B^{\mathrm{dom}}_t+0.35\,B^{\mathrm{band}}_t+0.40\,B^{\mathrm{asset}}_t,
\]
\[
H^{\mathrm{cont}}_t=\exp(-2c_t)\max\bigl(0,\,1-0.5(1-e_t)\bigr).
\]

### 3.2 认识论观测对象

\[
O_{j,t}=(x_{j,t},\,\tau_{j,t},\,q_{j,t},\,g_{j,t},\,r_{j,t}).
\]

AI 消费的是带时间、质量、门控与角色的对象集合，而非平面特征矩阵。

### 3.3 异步状态与时滞误差界

潜在状态 $S_{t+1}=F(S_t,\eta_{t+1})$。来源观测：
\[
X^{\mathrm{obs}}_{j,t}=h_j(S_{t-\ell_{j,t}})+\nu_{j,t}.
\]
若 $h_j$ Lipschitz，则重建误差可分解为时滞、噪声与缺失三项：
\[
\|\widetilde S_t-S_t|
\le C_1\sum_j\omega_j\ell_{j,t}
+C_2\sum_j\omega_j\|\nu_{j,t}\|
+C_3\sum_j\omega_j(1-z_{j,t}).
\]

### 3.4 信息滤子与编译算子

\[
\mathcal{F}^{\mathrm{raw}}_t=\sigma\bigl(\{X^{\mathrm{obs}}_{j,\tau}\}\bigr),\qquad
\mathcal{F}^{\mathrm{AI}}_t=\sigma(W^{\mathrm{AI}}_t,D_t),
\]
\[
\Pi_t=\mathcal{B}_t\circ M_t\circ A_t,\qquad
W^{\mathrm{AI}}_t=\Pi_t(\mathcal{F}^{\mathrm{raw}}_t).
\]

**命题 1（编译不是特征扩展）**：扩大 $\mathcal{F}^{\mathrm{raw}}$ 而无良好 $\Pi_t$，不必扩大决策相关的 $\mathcal{F}^{\mathrm{AI}}$；未门控、过期或角色不一致的证据可损害 $H_t,U_t$。

*证明概要.* 加入滞后大或缺失的源 $j^\star$；若 $M_t$ 未剔除，则 $H$ 下降且 $U$ 弱降。宽度至多增 $1/K$，但乘积 $\mathrm{WMI}=BUH$ 可因 $UH$ 损失主导而下降。$W^{\mathrm{AI}}=\Pi(\mathcal{F}^{\mathrm{raw}})$ 继承门控对象，故原始 $\sigma$-域扩张不必扩大支付相关的 AI 可见信息。□

**命题 2（SDF 接口：编译约束定价）**：可实施的条件定价陈述只能取 $\mathbb{E}[m_{t+1}R_{t+1}\mid\mathcal{F}^{\mathrm{AI}}_t]=1$ 形式；对更细的 $\mathcal{F}^{\mathrm{raw}}_t$ 评价同一代理人产生**编译楔** $w_t=\mathbb{E}[mR\mid\mathcal{F}^{\mathrm{raw}}]-\mathbb{E}[mR\mid\mathcal{F}^{\mathrm{AI}}]$，对所有 payoff 为零当且仅当 $\Pi$ 不损失定价相关信息。对 raw 滤子度量的 alpha 混合了真实错定价与编译损失。

*证明概要.* 迭代期望给 $\mathbb{E}[w_t\mid\mathcal{F}^{\mathrm{AI}}]=0$；若某带 $\mathrm{MIG}>0$ 被弃，存在 payoff 其 raw 条件期望随该带变动而编译后不变，故 $w_t\neq0$ 于正概率集。□

**命题 3（滞后重构界）**：在 Lipschitz 观测与有界增量下，重构误差满足延迟/噪声/缺失三项界，常数与 AI 模型类无关。

*证明概要.* Lipschitz 给出滞后映射偏差 $\le L_j\bar\delta\,\ell_{j,t}$；将 $\widetilde S-S$ 分解为滞后偏差、$\nu$ 与缺失项，三角不等式加权得界。TTL/readiness 恰压缩这三项。□

### 3.5 ECP、MIG 与识别 DAG

\[
\mathrm{ECP}_t=\mathbf{1}\{\mathrm{conf}_t>\bar c\}\,\mathbf{1}\{\mathrm{WMI}_t<w\},
\]
\[
\mathrm{MIG}^{(m)}_{k,t}=I(R^{(m)}_t;E_{k,t}\mid I^{(-k)}_t),
\]
\[
O_t\to W_t\to A_t,\quad M_t\to W_t,\quad M_t\to A_t,\quad C_t\to(W_t,A_t).
\]

识别优先依赖可观测可用性冲击 $O_t$。

### 3.6 贝叶斯弃权

动作集 $\mathcal{A}=\{\mathrm{bullish},\mathrm{bearish},\mathrm{neutral},\mathrm{abstain}\}$：
\[
a^\star_t=\arg\min_{a}\mathbb{E}[\ell(a,R_t)\mid W_t],
\]
当所有非弃权动作期望损失高于 $c_{\mathrm{abs}}(W_t)$ 时弃权。

**命题 4（世界条件弃权）**：若 $\ell(\mathrm{abstain})\equiv c_{\mathrm{abs}}(W)$ 且所有非弃权动作 $\mathbb{E}[\ell\mid W]>c_{\mathrm{abs}}$，则最优为弃权；在单交叉假设（已形式化为 Assumption）下，非弃权损失与 $c_{\mathrm{abs}}$ 对 WMI 弱递减时弃权域是 WMI 的下集（由 IS 冻结 ACWMI 阈值实现）。

*证明概要.* 第一称由 Bayes argmin 直接得；第二称由单交叉假设给出下等值集结构。□

### 3.7 ACWMI 与解释质量

\[
\mathrm{ACWMI}_t
=\exp\!\left(
\frac{\sum_{i=1}^{5}\gamma_i(r_t)\log x_{i,t}}{\sum_{i=1}^{5}\gamma_i(r_t)}
\right),
\quad
x_t=(B^{\mathrm{hier}}_t,U_t,H^{\mathrm{cont}}_t,S_t,C_t).
\]

\[
\mathrm{EAR}_t=\frac{\#\{\text{绑定证据的判断}\}}{\#\{\text{总判断}\}},\quad
\mathrm{UCR}_t=1-\mathrm{EAR}_t,\quad
\mathrm{EV}_t=\frac{d(\Phi_t,\Phi_{t-1})}{1+d(W_t,W_{t-1})}.
\]

薄/厚世界还改变解释空间：
\[
\Phi^{\mathrm{thin}}_t\neq\Phi^{\mathrm{thick}}_t,\qquad
\Pr(\phi^\star_t\in\Phi^{\mathrm{thick}}_t)>\Pr(\phi^\star_t\in\Phi^{\mathrm{thin}}_t).
\]

**命题 5（ACWMI 因子单调性）**：$\gamma\gg 0$、$x\in(0,1]$ 时，$\partial\mathrm{ACWMI}/\partial x_k>0$，且 $\log\mathrm{ACWMI}$ 对 $\log x$ 凹；诚实性比例恶化不能由等权宽度一对一抵消。

*证明概要.* $\log\mathrm{ACWMI}=\sum w_i\log x_i$；污染冲击使 $|\Delta\log H|$ 大而 $\Delta\log B=O(1/K)$，净加权变化为负。□

**命题 6（LOBO 即经济 MIG，含通道分解）**：固定规则下 $V(I)$ 为 OOS CE，$\widehat{\mathrm{MIG}}_k=V(I)-V(I\setminus E_k)$。带 $k$ 经两条通道进入决策——**内容通道**（带信号改变行动方向/激活）与**门控通道**（带可用性改变 $B,U,H$ 与弃权）；$\widehat{\mathrm{MIG}}_k$ 按套叠恒等式精确分解为两通道效应。Blackwell 单调 + 非冗余 ⇒ $\widehat{\mathrm{MIG}}_k>0$。PIT 上"tilt 置零"实现内容删除、"状态置 missing"实现门控删除，两者并施即 $I\setminus E_k$。

*证明概要.* Blackwell ⇒ $V(I)\ge V(I\setminus E_k)$；分解是三个实验臂（仅内容、仅门控、全删）上的套叠恒等式。□

**证明链小结**：命题 1 区分原始跨度与可用世界质量；命题 2 把任意定价核约束到编译后滤子（alpha vs 编译楔）；命题 3 锚定 freshness/TTL；命题 4 正当化世界条件弃权；命题 5 使 ACWMI 成为严格质量指数；命题 6 将 LOBO CE 跌幅映射为经济 MIG 并分离内容与门控。后文实证是该链的实例化，而非替代。

---

## 4. EvoQuant 作为测量仪器

数据层采集 → SQLite 历史 → 逻辑层 readiness / AI context → API。本研究所用生产接口包括：`BandPITService`、`load_availability_shocks`、可配置 `WORLD_MODEL_INDEX_MODE` / 弃权阈值。叙事顺序：**先理论，后项目**。

---

## 5. 数据与真实多带 PIT

| 带 | 档案状态 |
| --- | --- |
| exchange (OKX) | 耐久：~9.4k 日线，2025-06-30→2026-08-03 |
| macro | 耐久：~81k，含 `available_at` |
| alternative | 耐久：~89k |
| news/onchain/options/tokenomics | 当前多为采集日右删失 |

PIT 面板：400 天 × 10 资产 = 4000 行；耐久带 ready 率 ≈ exchange 0.998 / macro 1.0 / alternative 1.0。

---

## 6. 实证设计

- IS/OOS 切点：2026-01-16（200/200 天）  
- AC 阈值 IS 冻结：ACWMI$<0.35$ 或 $C<0.35$；生产 WMI$=0.2$ 不调参  
- 经济价值：年化收益/波动、Sharpe、CRRA CE（$\gamma=2$）、最大回撤  
- **推断**：OOS 日度组合收益的循环块 bootstrap（$n=999$，块长 5 日）给出 $\Delta$Sharpe/$\Delta$CE 的双边 $p$ 值  
- 识别：薄 vs 厚；耐久带 LOBO；稀缺世界（$B^{\mathrm{hier}}$ 底五分位）事件研究  

### 6.1 Mechanism signals：透明规则 + 带内容进入行动

方向仓位是**确定性规则**（无隐层模型）。关键改动：带**内容**直接进入行动映射，PIT 不 ready 时强制为 0，故 LOBO 删的是内容而不仅是门控：

- $\mathrm{macro\_tilt}$：vintage 安全（`available_at`）的 VIX/DXY 5 日变化——双降 = risk-on(+1)，双升 = risk-off(−1)  
- $\mathrm{alt\_tilt}$：stablecoin 7 日净供给符号（$t$ 前最新观测）  
- $S$：AlphaDecay 半衰期 × 拥挤 × 惊奇  
- $C$：{mom5, flow, cascade, systemic, macro_tilt, alt_tilt} 符号两两一致率  
- **R1** crisis **且** $\mathrm{cascade\_p}\ge0.60$ → 做空（**证据合取**：单源触发不可行动，与 $C$ 同逻辑）  
- **R2** trend 且 mom5$>0$ 且 cascade$<0.45$ 且 macro_tilt$\ge0$ → 做多（宏观否决）  
- **R2b** range 且 macro_tilt$>0$ 且 alt_tilt$>0$ 且 mom5$\ge0$ → 做多（带驱动）  
- **R3** $\mathrm{sign}(\mathrm{mom5})$；双带 risk-off 时多头否决为 0（空仓）；平局由 $\mathrm{sign}(\mathrm{tilt和})$ 决定  

**校准审计与引擎修复（如实披露）**：长回测审计曾暴露两处 harness 缺陷——全历史回撤使 crisis 成吸收态、cascade 输入映射饱和于 0.86（规则退化为恒定做空，靠熊市 OOS"获胜"）。修复为 60 日窗口、波动率标准化尾部强度、真实 RSI/ADX 代理后，cascade_p 对次日左尾实现单调校准（$P(r<-5\%)$ 从 0.039 升至 0.110）。该修复由审计驱动，非 OOS 表现搜索。详见 `table_mechanism_definition.csv` / `table_cascade_calibration.csv`。

---

## 7. 主要结果

### 7.1 带内容 OOS 显著胜过动量（头条对比）

| 策略 | 年化收益 | Sharpe | CE | 最大回撤 | 弃权率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Always long | −0.816 | −1.399 | −1.157 | −0.466 | 0 |
| Momentum | 0.051 | 0.101 | −0.202 | −0.500 | 0 |
| Mechanism（带内容） | 0.385 | 0.767 | **0.132** | −0.438 | 0.075 |
| WMI$<0.2$ | 0 | 0 | 0 | 0 | 1.000 |
| ACWMI (IS-frozen) | 0.385 | 0.767 | 0.132 | −0.438 | 0.075 |

**Mechanism − Momentum：$\Delta$CE $=0.334$，$p=0.034$，95% CI $[0.03,0.68]$ 排除 0。** 两策略共享全部收益率输入、仅差 vintage 宏观/替代内容——该对比按构造隔离了编译带内容的价值。

### 7.2 厚 vs 薄世界（薄 = 内容与门控同删）

| 世界 | Mean $B$ | Mean $H$ | Sharpe | CE | 弃权率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 薄（仅 exchange） | 0.201 | 0.562 | −0.850 | −0.388 | 0.454 |
| 厚真实 PIT | 0.356 | 0.688 | 0.767 | 0.132 | 0.075 |

$\Delta$Sharpe $=1.62$（$p=0.044$，CI 排除 0）；$\Delta$CE $=0.52$（$p=0.22$，200 天尚不显著）。

### 7.3 LOBO：显著，且由内容通道驱动

| 带 | ΔCE 总 | $p$ | ΔCE 内容 | $p$ | ΔCE 门控 | $p$ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| exchange | −0.056 | 0.394 | — | — | −0.056 | 0.394 |
| macro | −0.418 | **0.010** | −0.334 | **0.034** | −0.066 | **0.026** |
| alternative | −0.402 | **0.008** | −0.334 | **0.034** | −0.040 | **0.044** |

带信息改变的是**交易什么**，而不仅是**何时弃权**——直接回应"LOBO 只测门控敏感性"的批评。两带内容删除损失相同是因为 R2b 与双带否决都要求两个 tilt 同号。

### 7.4 长回测外部有效性锚（BTC/ETH 2017–2026）

同一规则（tilt=0，2025 前无带档案）在 3471 天上：年化 0.456、Sharpe 0.664、CE −0.009，10 个日历年 8 年为正（2018 熊市 +2.13）；但**对动量无显著优势**（$\Delta$CE 0.017，$p=0.55$）。收益率核心无隐藏 alpha ⇒ 7.1–7.3 的显著收益负载在编译带内容上。

### 7.5 成本、funding 与推断稳健性

10bps 单边成本下 Mechanism 保持 Sharpe 0.467（CE −0.019 vs 动量 −0.352）；25bps 下双双为负但排序不变；永续 funding 调整改变 CE 不足 0.005。块长 {5,10,21} 结论稳定。White (2000) reality check（全策略菜单 vs always-long）$p=0.144$——多重检验诚实披露：菜单级弱于单一预设的内容对比。$B^{\mathrm{hier}}$ 权重扰动 CE 三位小数不变。

### 7.6 稀疏档案上的选择性预测

IS 校准选择最小附加门控（ACWMI$<0.25$ 仅额外约束 1% 天数）；生产 WMI$<0.2$ 100% 弃权。两者同证：**质量阈值不可跨信息集支撑移植**（命题 4）。实测 ECP $=0.688$（conf$>0.7$ 且 WMI$<0.2$）——分类器频繁在薄世界高置信，恰是 ECP 设计要捕捉的状态。所有行动绑定命名计算器证据（EAR $=1$，UCR $=0$）。

---

## 8. 稳健性、威胁与顶刊议程

1. 持续多年采集，消除 news/onchain/options/tokenomics 右删失，扩展带内容 vintage 到多窗口。  
2. 以 `collection_runs` / 制度中断日志强化 $O_t$。  
3. 每日落 readiness / AI-context 快照，实现纯 `time_slice` 回放。  
4. 扩展截面与日历；stationary bootstrap 复核；损失函数变体。

---

## 9. 结论

信息集编译是加密市场的一阶对象。本文给出带证明链与 SDF 接口的 RCA-WM/ACWMI 理论（命题 1–6），并在真实多带 PIT 档案上完成可分解识别：**带内容显著优于动量（$p=0.034$）、LOBO macro/alternative 显著（$p=0.010/0.008$）且内容通道主导、长回测证明规则本身无隐藏 alpha**——恰是编译理论预测的模式。通往 JF/RFS 终稿的路径是制度性的：加深 vintage、记录中断、每日快照、扩展截面与日历——同时**不得再压缩掉形式化证明链**。

---

## 附录 A. 符号

| 符号 | 含义 |
| --- | --- |
| $O_{j,t}$ | 认识论观测 |
| $B_t,U_t,H_t$ | 宽度、稳定性、诚实性 |
| $\mathrm{WMI}_t$ / $\mathrm{ACWMI}_t$ | 生产 / 体制条件指数 |
| $\Pi_t$ | 编译算子 |
| $\mathrm{ECP},\mathrm{MIG}$ | 校准惩罚 / 边际信息增益 |
| $\Phi_t$；EAR/UCR/EV | 解释空间与解释质量 |
| $O_t$ | 可用性冲击（DAG） |

## 附录 B. 复现

```bash
make paper-lab
PYTHONPATH=. python3 pdf/sci/generate_full_manuscript_pdf.py
```

英文 TeX：`pdf/sci/main_jf_rfs.tex`  
面板：`pdf/data/pit_multiband_panel.csv`

## 参考文献（精选）

Cochrane (2005); Fama–French (1993); Gu–Kelly–Xiu (2020); Harvey–Liu–Zhu (2016); Kelly–Pruitt–Su (2019); Liu–Tsyvinski–Wu (2022); Makarov–Schoar (2020); Nagel (2021).
