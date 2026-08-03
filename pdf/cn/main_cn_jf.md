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

实证上，我们灌入真实多带档案（OKX 行情、宏观 vintage、alternative，以及较薄的 news/onchain/options/tokenomics），构建 400 天 × 10 资产（4000 资产—日）的 PIT 面板，并对齐 Yahoo 收益。机制引擎仅使用 $t$ 前信息；弃权阈值样本内冻结。样本外，厚真实 PIT 世界显著优于仅交易所薄世界（CE $0.474$ vs $-0.011$）。对耐久证据带的 leave-one-band-out 显示：去掉 macro/alternative/exchange，CE 分别下降 $0.534/0.526/0.339$。IS 冻结的 ACWMI 门控可实施（Sharpe $0.901$，CE $0.199$，弃权 $29.7\%$），但在 CE 上未主导未门控厚信号。生产阈值 WMI$<0.2$ 在稀疏档案上 100% 弃权，说明质量阈值必须按信息集支撑冻结。

贡献是：带完整公式的编译理论 + 可复现的真实 PIT 识别协议。局限（若干带右删失、自然硬中断稀少、十个流动性标的）明确列为终稿议程。

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

## 3. 理论

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

**命题（编译不是特征扩展）**：扩大 $\mathcal{F}^{\mathrm{raw}}$ 而无良好 $\Pi_t$，不必扩大决策相关的 $\mathcal{F}^{\mathrm{AI}}$；未门控、过期或角色不一致的证据可损害 $H_t,U_t$。

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
- 识别：薄 vs 厚；耐久带 LOBO；稀缺世界（$B^{\mathrm{hier}}$ 底五分位）事件研究

---

## 7. 主要结果

### 7.1 厚世界 ≫ 薄世界（OOS）

| 世界 | Mean $B$ | Mean $H$ | Sharpe | CE |
| --- | ---: | ---: | ---: | ---: |
| 薄（仅 exchange） | 0.201 | 0.562 | −0.004 | −0.011 |
| 厚真实 PIT | 0.356 | 0.688 | 1.399 | 0.474 |
| 厚 + AC 门控 | 0.356 | 0.688 | 0.901 | 0.199 |

### 7.2 Leave-one-band-out（耐久带）

| 去掉的带 | Sharpe | CE | ΔCE |
| --- | ---: | ---: | ---: |
| （无） | 0.901 | 0.199 | 0 |
| exchange | −0.232 | −0.141 | −0.339 |
| macro | −0.485 | −0.336 | −0.534 |
| alternative | −0.422 | −0.327 | −0.526 |

### 7.3 OOS 策略赛马

| 策略 | 年化收益 | Sharpe | CE | 最大回撤 | 弃权率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Always long | −0.816 | −1.399 | −1.157 | −0.466 | 0 |
| Momentum | 0.051 | 0.101 | −0.202 | −0.500 | 0 |
| Thick ungated | 0.816 | 1.399 | 0.474 | −0.279 | 0 |
| WMI$<0.2$ | 0 | 0 | 0 | 0 | 1.000 |
| ACWMI (IS-frozen) | 0.454 | 0.901 | 0.199 | −0.340 | 0.297 |

**解释：**（i）编译质量具有一阶经济内容；（ii）MIG 在耐久带间异质；（iii）选择性预测仅在阈值按档案支撑冻结时才可实施。

---

## 8. 稳健性、威胁与顶刊议程

1. 持续多年采集，消除 news/onchain/options/tokenomics 右删失。  
2. 以 `collection_runs` / 制度中断日志强化 $O_t$。  
3. 每日落 readiness / AI-context 快照，实现纯 `time_slice` 回放。  
4. 扩展截面与日历；补充交易成本调整 CE 与多重检验披露。

---

## 9. 结论

信息集编译是加密市场的一阶对象。本文给出完整 RCA-WM/ACWMI 理论，并在真实多带 PIT 档案上识别：厚世界优于薄世界，耐久带具有大额 leave-one-out 经济价值，IS 冻结 ACWMI 门控可实施。EvoQuant 是实验室。通往 JF/RFS 终稿的路径是制度性的：加深 vintage 历史、记录中断、每日快照、扩展截面——同时**不得再压缩掉形式化理论**。

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
