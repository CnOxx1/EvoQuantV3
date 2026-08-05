# ICAIF ’26 论文中英对照（完整正文）

> 源稿：当前 `main.tex`（约 7 页，ACM ICAIF ’26 sigconf+anonymous）  
> 用途：内部精读；**正式投稿仍以英文 PDF 为准**。  
> 体例：每条为 **EN → 中文**；公式、字段名（`should_ai_abstain`、WMI 等）、四臂专名（Compiled / Ungated / Raw / Blind）与引用键在两侧保持原样。

---

## 0. 关键术语表（全文统一译法）

| English | 中文（本稿采用） | 说明 |
|---|---|---|
| observation contract / interface | 观测契约 / 观测接口 | 论文主 claim；现标题前半 |
| typed refusal / hard refuse flag | 类型化拒绝 / 硬拒绝标志 | 布尔门控，非软置信度 |
| world-model runtime | 世界模型运行时 | 状态编译器 + 弃权运行时，非生成 WM |
| point-in-time (PIT) | 时点安全 / PIT | 防前视 |
| thin world / scarce support | 稀薄世界 / 稀薄支撑 | WMI 低于生产阈值 |
| band-thick / open slice | 波段齐全 / 开放切片 | 3/3 ready ≡ WMI≥0.05（反事实开放） |
| Compiled / Ungated / Raw / Blind | Compiled / Ungated / Raw / Blind | 四臂专名，两侧保留英文 |
| grounding workflow | 接地工作流 | 非交易认知核验（RQ2） |
| certainty equivalent (CE) | 确定性等价（CE） | 弃权下避免损失；非 alpha 主张 |
| vintage / available_at | vintage / `available_at` | 宏观发布滞后 |
| should_ai_abstain / thin_world | （保留英文字段） | 机器可读弃权 |
| evidence IDs / EAR | 证据 ID / EAR | 可审计 |
| BandPIT | BandPIT | 前收盘时钟编译器专名 |
| OOS | 样本外（OOS） | out-of-sample |
| Title (current) | 面向公开大语言模型的观测契约：加密市场决策之前的类型化拒绝 | 对应现标题全文 |

---

## 1. 标题

### 1.1
**EN:** An Observation Contract for Public LLMs: Typed Refusal before Crypto Market Decisions

**中文:** 面向公开大语言模型的观测契约：加密市场决策之前的类型化拒绝

### 1.2（短标题 / running head）
**EN:** An Observation Contract for Public LLMs

**中文:** 面向公开大语言模型的观测契约

---

## 2. 摘要（Abstract）

### 2.1 Claim
**EN:** Claim. Public LLMs fail on crypto markets for want of a reliable *observation interface*, not for want of another trading strategy.

**中文:** **主张。** 公开大语言模型在加密市场上失败，是因为缺少可靠的*观测接口*，而不是缺少又一条交易策略。

### 2.2 Contribution object
**EN:** We contribute a typed observation contract---an anonymized *world-model runtime* (state compiler + hard refuse flag, not a generative simulator)---that turns asynchronous multi-band evidence into a point-in-time (PIT) world bundle.

**中文:** 我们贡献一个类型化观测契约——一个匿名化的*世界模型运行时*（状态编译器 + 硬拒绝标志，而非生成式模拟器）——将异步多波段证据变为时点安全（PIT）世界状态包（world bundle）。

### 2.3 Semantics sentence
**EN:** Epistemic observations \(O_{j,t}=(x,\tau,q,g,r)\) and compilation \(\Pi_t\) yield \(\mathcal{F}^{\mathrm{AI}}_t\); completeness, honesty \((B,U,H)\), and WMI/ACWMI expose machine-readable refusal; evidence IDs bind actions to disclosed fields.

**中文:** 认识论观测 \(O_{j,t}=(x,\tau,q,g,r)\) 与编译 \(\Pi_t\) 生成 \(\mathcal{F}^{\mathrm{AI}}_t\)；完整性、诚实性 \((B,U,H)\) 与 WMI/ACWMI 暴露机器可读的拒绝；证据 ID 将行动绑定到已披露字段。

### 2.4 Evidence — four-arm ranking
**EN:** Evidence. On identical OOS asset-days, four live public LLMs (temperature \(0\)) form a four-arm ranking: Blind refuses; Raw over-trades and loses; Ungated abstains only partially (\({\approx}0.68\)); Compiled with a hard flag abstains on every thin day (\(1.0\)).

**中文:** **证据。** 在相同的样本外资产日上，四个现场公开 LLM（温度 \(0\)）形成四臂排序：Blind 拒绝；Raw 过度交易并亏损；Ungated 仅部分弃权（约 \(0.68\)）；带硬标志的 Compiled 在每个稀薄日弃权（\(1.0\)）。

### 2.5 Replication
**EN:** Full-OOS and band-thick splits reproduce the ranking.

**中文:** 全样本外与波段齐全切分复现该排序。

### 2.6 Scarce-support stress
**EN:** This panel never exceeds the production refuse threshold (\(\max\mathrm{WMI}\approx 0.093{<}0.2\)), so Compiled's full refusal is a scarce-support stress test.

**中文:** 该面板从未超过生产拒绝阈值（\(\max\mathrm{WMI}\approx 0.093{<}0.2\)），故 Compiled 的全拒绝是稀薄支撑压力测试。

### 2.7 Open-slice counterfactual
**EN:** On the counterfactual open slice (\(\mathrm{WMI}\ge 0.05\); \(n{=}1224\)), live Ungated (same content, no hard flag) acts with mean CE \({\approx}{+}0.29\) across vendors, while a no-LLM content rule also beats momentum (\(\Delta\mathrm{CE}{=}0.315\)).

**中文:** 在反事实开放切片（\(\mathrm{WMI}\ge 0.05\)；\(n{=}1224\)）上，现场 Ungated（同内容、无硬标志）跨厂商行动的平均 CE 约 \(+0.29\)，同时一条无 LLM 内容规则也击败动量（\(\Delta\mathrm{CE}{=}0.315\)）。

### 2.8 Grounding
**EN:** A grounding workflow recovers ready/missing/tilt answers at mean F1/acc.\ \({\approx}0.97\) (Compiled) vs.\ \({\lesssim}0.23\) (Raw).

**中文:** 接地工作流恢复就绪/缺失/倾斜答案，均值 F1/准确率约 \(0.97\)（Compiled）对 \(\lesssim 0.23\)（Raw）。

### 2.9 Systems contribution
**EN:** We detail the runtime (collectors, vintage store, BandPIT, bundle schema, LLM adapter) as an ICAIF systems contribution.

**中文:** 我们将运行时（采集器、vintage 存储、BandPIT、bundle schema、LLM 适配器）作为 ICAIF 系统贡献加以详述。

---

## 3. CCS / 关键词

### 3.1 CCS
**EN:** Computing methodologies~Artificial intelligence (500); Computing methodologies~Machine learning (300); Applied computing~Economics (300)

**中文:** 计算方法～人工智能（500）；计算方法～机器学习（300）；应用计算～经济学（300）

### 3.2 Keywords
**EN:** world models, public LLMs, AI agents, cryptocurrency, point-in-time, abstention, trustworthy AI, observation contract, systems

**中文:** 世界模型、公开 LLM、AI 智能体、加密货币、时点安全、弃权、可信 AI、观测契约、系统

---

## 4. 第 1 节 Introduction

### 4.1 Core claim (read this first)
**EN:** Core claim (read this first). Public LLMs fail on crypto *before* strategy: they lack a complete, honest, auditable *market observation interface*.

**中文:** **核心主张（请先读）。** 公开大语言模型在加密市场上失败于策略*之前*：它们缺少一个完整、诚实、可审计的*市场观测接口*。

### 4.2 Clocks and assumed streams
**EN:** Venue fragmentation, derivatives, on-chain flows, news, and macro vintages arrive on incompatible clocks~\cite{makarov2020,liu2022}, while generative world models~\cite{ha2018world,hafner2020dreamer,lecun2022path} and tool-using finance agents~\cite{yao2023react,yu2023finmem,zhang2024finagent} typically *assume* a usable observation stream.

**中文:** 场所碎片化、衍生品、链上资金流、新闻与宏观 vintage 以不兼容的时钟到达~\cite{makarov2020,liu2022}，而生成式世界模型~\cite{ha2018world,hafner2020dreamer,lecun2022path}与工具型金融智能体~\cite{yao2023react,yu2023finmem,zhang2024finagent}通常*假定*存在可用观测流。

### 4.3 What this paper builds
**EN:** This paper builds the missing interface---a typed observation contract with a hard refuse flag---not a new trading agent and not a generative simulator.

**中文:** 本文构建缺失的接口——带硬拒绝标志的类型化观测契约——既不是新的交易智能体，也不是生成式模拟器。

### 4.4 One-line thesis
**EN:** In one line: *compile asynchronous evidence into a PIT world bundle; refuse when the world is thin; show that live LLMs obey the hard contract and fail without it.*

**中文:** 一句话：*将异步证据编译为 PIT 世界状态包；世界稀薄时拒绝；表明现场 LLM 服从硬契约，且没有硬契约时失败。*

### 4.5 What we build
**EN:** What we build. We implement the contract as an anonymized market *world-model runtime*: a state compiler from raw multi-band evidence to a PIT-safe bundle for GPT~/DeepSeek~/GLM~/Gemini-class models under a typed refuse boolean.

**中文:** **我们构建什么。** 我们将契约实现为匿名化的市场*世界模型运行时*：在类型化拒绝布尔量下，从原始多波段证据到 PIT 安全包的状态编译器，面向 GPT~/DeepSeek~/GLM~/Gemini 一类模型。

### 4.6 World model meaning
**EN:** ``World model'' here means *observation compiler + abstention runtime* (Section~\ref{sec:method}), not a next-state dynamics model.

**中文:** 此处的「世界模型」指*观测编译器 + 弃权运行时*（第~\ref{sec:method} 节），而非下一状态动力学模型。

### 4.7 Three properties
**EN:** The compiled world must be **complete** (missingness disclosed), **honest** (stale or role-incoherent evidence gated), and **auditable** (actions bound to evidence).

**中文:** 编译后的世界必须**完整**（缺失被披露）、**诚实**（过期或角色不一致的证据被门控）、**可审计**（行动绑定到证据）。

### 4.8 How we evaluate — RQ1
**EN:** How we evaluate. **RQ1 (primary):** Can the hard contract *enforce* thin-world abstention across live public LLMs? Four arms on identical days---Compiled (hard flag), Ungated (same content, no flag), Raw (momentum fragment), Blind (no feed).

**中文:** **如何评估。** **RQ1（主）：** 硬契约能否跨现场公开 LLM *强制*稀薄世界弃权？相同日期上的四臂——Compiled（硬标志）、Ungated（同内容、无标志）、Raw（动量碎片）、Blind（无喂入）。

### 4.9 RQ2
**EN:** **RQ2:** Does the compiled bundle make analyst answers (ready~/missing~/tilt) verifiable?

**中文:** **RQ2：** 编译包是否使分析师答案（就绪~/缺失~/倾斜）可核验？

### 4.10 RQ3
**EN:** **RQ3 (secondary):** Are the vintaged tilts economically nonempty under a transparent no-LLM rule vs.\ momentum~/buy-and-hold?

**中文:** **RQ3（次）：** 在透明无 LLM 规则相对动量~/买入持有下，vintage 倾斜是否经济上非空？

### 4.11 Contributions
**EN:** Contributions. (1)~**Interface semantics:** epistemic observations, \(\Pi_t\), lag reconstruction, completeness/honesty, WMI/ACWMI abstention, evidence-bound actions---enough to define the contract, not a pricing theorem. (2)~**Runtime:** vintage collectors, BandPIT previous-close clock, quality-tagged bundles, shocks \(O_t\), multi-vendor adapter, frozen Compiled~/Ungated~/Raw~/Blind protocol. (3)~**Live validation:** Blind refuses; Raw over-trades and loses; Ungated \(\approx 0.68\); Compiled thin-abstain \(1.0\) (full OOS too). Grounding \(0.97\) vs.\ Raw \(0.04\)--\(0.23\); secondary content rule shows tilts nonempty.

**中文:** **贡献。** (1)~**接口语义：** 认识论观测、\(\Pi_t\)、滞后重构、完整性/诚实性、WMI/ACWMI 弃权、证据绑定行动——足以定义契约，而非定价定理。(2)~**运行时：** vintage 采集器、BandPIT 前收盘时钟、质量标注包、冲击 \(O_t\)、多厂商适配器、冻结的 Compiled~/Ungated~/Raw~/Blind 协议。(3)~**现场验证：** Blind 拒绝；Raw 过度交易并亏损；Ungated \(\approx 0.68\)；Compiled 稀薄弃权 \(1.0\)（全样本外亦然）。接地 \(0.97\) 对 Raw \(0.04\)--\(0.23\)；次要内容规则表明倾斜非空。

---

## 5. 第 2 节 Related Work

### 5.1 World models in AI
**EN:** World models in AI. World models learn compact states and often dynamics~\cite{ha2018world,hafner2020dreamer,lecun2022path}. We address the complementary *observation-side* problem: a PIT-safe, quality-tagged crypto world *before* dynamics or LLM policy. We claim the missing systems layer generative WMs usually assume---not a Dreamer/JEPA simulator.

**中文:** **AI 中的世界模型。** 世界模型学习紧凑状态并常学习动力学~\cite{ha2018world,hafner2020dreamer,lecun2022path}。我们处理互补的*观测侧*问题：在动力学或 LLM 策略*之前*的 PIT 安全、质量标注加密世界。我们主张的是生成式 WM 通常假定却缺失的系统层——不是 Dreamer/JEPA 模拟器。

### 5.2 LLM agents in finance
**EN:** LLM agents in finance. ChatGPT return prediction~\cite{lopez2023chatgpt}, open financial LLMs~\cite{yang2023fingpt}, memory-augmented trading agents~\cite{yu2023finmem,li2023tradinggpt}, and tool-augmented agents~\cite{zhang2024finagent,yao2023react} improve agent skill and orchestration. Recent ICAIF work targets adjacent layers: FinAgentBench evaluates agentic retrieval for financial QA~\cite{choi2025finagentbench}; FinSearch builds temporal-aware search agents over market and news feeds~\cite{shen2025finsearch}; FinResearchBench judges long-horizon research agents with logic-tree protocols~\cite{sun2025finresearchbench}; FactorMAD uses multi-agent debate for interpretable alpha mining~\cite{duan2025factormad}. Those systems improve how agents fetch, debate, and are scored, but still assume a usable observation stream. We study the missing prior step---a PIT-safe, quality-tagged *observation contract* with typed abstention---and evaluate within-model Compiled / Ungated / Raw / Blind under a frozen schema rather than proposing another memory router, retrieval planner, or debate society.

**中文:** **金融中的 LLM 智能体。** ChatGPT 收益预测~\cite{lopez2023chatgpt}、开放金融 LLM~\cite{yang2023fingpt}、记忆增强交易智能体~\cite{yu2023finmem,li2023tradinggpt}与工具增强智能体~\cite{zhang2024finagent,yao2023react}提升了智能体技能与编排。近期 ICAIF 工作瞄准相邻层：FinAgentBench 评估金融问答的智能体检索~\cite{choi2025finagentbench}；FinSearch 在市场与新闻喂入上构建时间感知搜索智能体~\cite{shen2025finsearch}；FinResearchBench 用逻辑树协议评判长视野研究智能体~\cite{sun2025finresearchbench}；FactorMAD 用多智能体辩论做可解释 alpha 挖掘~\cite{duan2025factormad}。这些系统改进了智能体如何获取、辩论与被评分，但仍假定存在可用观测流。我们研究缺失的先验步骤——带类型化弃权的 PIT 安全、质量标注*观测契约*——并在冻结 schema 下做同模型 Compiled / Ungated / Raw / Blind 评估，而非再提出记忆路由器、检索规划器或辩论社群。

### 5.3 Selective prediction and trustworthy AI
**EN:** Selective prediction and trustworthy AI. Abstention can be optimal under noise~\cite{elyaniv2010,geifman2017}. We tie refusal to world quality via an explicit runtime contract, not classifier confidence alone.

**中文:** **选择性预测与可信 AI。** 噪声下弃权可以是最优的~\cite{elyaniv2010,geifman2017}。我们通过显式运行时契约将拒绝绑定到世界质量，而非仅靠分类器置信度。

### 5.4 PIT measurement and crypto microstructure
**EN:** PIT measurement and crypto microstructure. Macro vintages~\cite{croushore2001} and crypto microstructure~\cite{makarov2020,liu2022} motivate multi-band compilation. Bootstrap discipline for the economic probes follows~\cite{white2000,politis1994,harvey2016}. Asset-pricing ML~\cite{gu2020,kelly2019,nagel2021} is adjacent: we validate the economic content of a compiled world for agents, not priced factors.

**中文:** **PIT 度量与加密微观结构。** 宏观 vintage~\cite{croushore2001}与加密微观结构~\cite{makarov2020,liu2022}动机多波段编译。经济探针的 bootstrap 纪律遵循~\cite{white2000,politis1994,harvey2016}。资产定价机器学习~\cite{gu2020,kelly2019,nagel2021}相邻：我们为智能体验证编译世界的经济内容，而非定价因子。

---

## 6. 第 3 节 Market World-Model Semantics

### 6.0 Section lead-in
**EN:** This section defines the observation contract formally. Readers who want the systems object first may skim to Section~\ref{sec:system}; the empirical estimand is the four-arm protocol in Section~\ref{sec:exp}.

**中文:** 本节形式化定义观测契约。希望先看系统对象的读者可略读至第~\ref{sec:system} 节；经验估计量是第~\ref{sec:exp} 节的四臂协议。

### 6.1 Definition — Epistemic observation
**EN:** Definition [Epistemic observation]. An epistemic observation is
\[
O_{j,t}=(x_{j,t},\ \tau_{j,t},\ q_{j,t},\ g_{j,t},\ r_{j,t}):
\]
value, latest-available time, quality, main-view gate, semantic role. A bare feature dump that omits \((\tau,q,g,r)\) is not a world observation.

**中文:** **定义［认识论观测］。** 认识论观测为
\[
O_{j,t}=(x_{j,t},\ \tau_{j,t},\ q_{j,t},\ g_{j,t},\ r_{j,t}):
\]
取值、最新可用时间、质量、主视图门控、语义角色。省略 \((\tau,q,g,r)\) 的裸特征倾倒不是世界观测。

### 6.2 Definition — Financial world state
**EN:** Definition [Financial world state]. \(W_t=\Pi_t(\mathcal{F}^{\mathrm{raw}}_t)\) with scalar quality \(q(W_t)\) (e.g.\ WMI/ACWMI) gating abstention; \(\mathcal{F}^{\mathrm{AI}}_t=\sigma(W_t)\).

**中文:** **定义［金融世界状态］。** \(W_t=\Pi_t(\mathcal{F}^{\mathrm{raw}}_t)\)，标量质量 \(q(W_t)\)（如 WMI/ACWMI）门控弃权；\(\mathcal{F}^{\mathrm{AI}}_t=\sigma(W_t)\)。

### 6.3 Definition — Compilation
**EN:** Definition [Compilation]. \(\Pi_t=B_t\circ M_t\circ A_t\): align clocks, apply honesty/missingness gates, assemble band views.

**中文:** **定义［编译］。** \(\Pi_t=B_t\circ M_t\circ A_t\)：对齐时钟、施加诚实/缺失门控、组装波段视图。

### 6.4 Completeness, honesty, quality
**EN:** Completeness, honesty, quality. Ready/limited/missing counts disclose coverage. \(\mathrm{WMI}_t=B_t U_t H_t\); ACWMI supports regime-conditional gating. The Compiled contract exposes the abstain flag (`should_ai_abstain`) and `thin_world` as first-class fields.

**中文:** **完整性、诚实性、质量。** Ready/limited/missing 计数披露覆盖。\(\mathrm{WMI}_t=B_t U_t H_t\)；ACWMI 支持状态条件门控。Compiled 契约将弃权标志（`should_ai_abstain`）与 `thin_world` 作为一等字段暴露。

### 6.5 Assumption — Bounded lag and increments
**EN:** Assumption [Bounded lag and increments]. Band \(j\) has max observation lag \(\Delta_j\); latent state increments satisfy \(\|S_u-S_{u-1}\|\le\bar\delta\).

**中文:** **假设［有界滞后与增量］。** 波段 \(j\) 有最大观测滞后 \(\Delta_j\)；潜在状态增量满足 \(\|S_u-S_{u-1}\|\le\bar\delta\)。

### 6.6 Proposition — Lag reconstruction bound
**EN:** Proposition [Lag reconstruction bound]. Under Assumption~1,
\[
\|\widetilde S_t-S_t\|
\;\le\;
C_{\mathrm{del}}\bar\delta
+C_{\mathrm{noi}}\varepsilon_t
+C_{\mathrm{miss}}m_t.
\]
Compilation cannot erase delay; it can refuse to pretend the bound is zero.

**中文:** **命题［滞后重构界］。** 在假设 1 下，
\[
\|\widetilde S_t-S_t\|
\;\le\;
C_{\mathrm{del}}\bar\delta
+C_{\mathrm{noi}}\varepsilon_t
+C_{\mathrm{miss}}m_t.
\]
编译不能消除延迟；它可以拒绝假装该界为零。

### 6.7 Intuition
**EN:** Intuition. Crypto agents that concatenate tool dumps silently absorb delay and missingness into the feature vector. Prop.~\ref{prop:recon} makes those terms explicit: a thicker raw payload can worsen the reconstruction if honesty collapses.

**中文:** **直觉。** 拼接工具倾倒的加密智能体会把延迟与缺失静默吸进特征向量。命题~\ref{prop:recon} 使这些项显式化：若诚实性坍塌，更厚的原始载荷可使重构更差。

### 6.8 Proposition — Compilation ≠ feature dump
**EN:** Proposition [Compilation \(\neq\) feature dump]. Enlarging raw span without \(\Pi_t\) need not enlarge usable \(\mathcal{F}^{\mathrm{AI}}\): ungated stale evidence can raise volume while lowering honesty/stability.

**中文:** **命题［编译 \(\neq\) 特征倾倒］。** 在没有 \(\Pi_t\) 的情况下扩大原始跨度，未必扩大可用的 \(\mathcal{F}^{\mathrm{AI}}\)：未门控的过期证据可抬高体量却降低诚实性/稳定性。

### 6.9 Proposition — World-conditional abstention
**EN:** Proposition [World-conditional abstention]. If non-abstain actions exceed a world-dependent cost \(c_{\mathrm{abs}}(W_t)\), the Bayes action is abstain; with costs decreasing in WMI, abstention forms a lower set in world quality~\cite{elyaniv2010}.

**中文:** **命题［世界条件弃权］。** 若非弃权行动超过世界依赖成本 \(c_{\mathrm{abs}}(W_t)\)，贝叶斯行动是弃权；当成本随 WMI 递减时，弃权在世界质量上形成下集~\cite{elyaniv2010}。

### 6.10 Proposition — LOBO content vs. gating
**EN:** Proposition [LOBO content vs.\ gating]. Deleting band \(j\) changes value through a content channel and a gating channel. Empirically we report content share under an ungated rule so the probe speaks to nonempty fields.

**中文:** **命题［LOBO：内容 vs. 门控］。** 删除波段 \(j\) 通过内容通道与门控通道改变价值。经验上我们在未门控规则下报告内容份额，使探针指向字段非空。

### 6.11 Implication for the runtime
**EN:** Implication for the runtime. Props.~\ref{prop:compile}--\ref{prop:abstain} motivate exporting gates and abstain flags rather than tilts alone. Prop.~\ref{prop:lobo} motivates the economic check: if deleting a durable band does not change actions, the bundle is empty of content; the probe shows that is not the case here.

**中文:** **对运行时的含义。** 命题~\ref{prop:compile}--\ref{prop:abstain} 动机导出门控与弃权标志而非仅倾斜。命题~\ref{prop:lobo} 动机经济检验：若删除耐久波段不改变行动，则 bundle 内容为空；探针表明此处并非如此。

### 6.12 Remark — Not a generative WM
**EN:** Remark [Not a generative WM]. We do not learn \(p(s_{t+1}\mid s_t,a_t)\). We deliver a *state compiler + abstention runtime*.

**中文:** **注记［不是生成式 WM］。** 我们不学习 \(p(s_{t+1}\mid s_t,a_t)\)。我们交付的是*状态编译器 + 弃权运行时*。

---

## 7. 第 4 节 Runtime Architecture

### 7.0 Section lead-in
**EN:** We describe the anonymized prototype as a layered system (Figure~\ref{fig:pipeline}; module map in Table~\ref{tab:modules}). Source paths and product names are omitted for double-blind review; an anonymized artifact will be released upon acceptance.

**中文:** 我们将匿名原型描述为分层系统（图~\ref{fig:pipeline}；模块图见表~\ref{tab:modules}）。源路径与产品名因双盲评审省略；接受后将发布匿名化制品。

### 7.1 Layered design — Data layer
**EN:** Layered design. (1) **Data layer (collectors).** Exchange, macro, and alternative collectors write vintage-aware history: observation timestamps plus macro `available_at` vintages.

**中文:** **分层设计。** (1) **数据层（采集器）。** 交易所、宏观与另类采集器写入感知 vintage 的历史：观测时间戳，以及宏观 `available_at` vintage。

### 7.2 Store layer
**EN:** (2) **Store layer.** Embedded analytical stores hold raw series, merged market panels, and pipeline outputs (readiness, WMI / ACWMI, paper world snapshots).

**中文:** (2) **存储层。** 嵌入式分析存储保存原始序列、合并市场面板与流水线输出（就绪度、WMI / ACWMI、论文世界快照）。

### 7.3 Logic layer
**EN:** (3) **Logic layer (compilation).** BandPIT reconstructs band readiness on a previous-close clock; honesty and missingness gates plus band assembly implement \(\Pi_t\); world-quality indices and availability shocks \(O_t\) are first-class.

**中文:** (3) **逻辑层（编译）。** BandPIT 在前收盘时钟上重建波段就绪度；诚实与缺失门控及波段组装实现 \(\Pi_t\)；世界质量指数与可用性冲击 \(O_t\) 为一等公民。

### 7.4 Service layer
**EN:** (4) **Service layer.** A read API serves quality-tagged AI bundles and health/readiness objects to consumers without requiring collector restarts for newly arrived rows.

**中文:** (4) **服务层。** 只读 API 向消费者提供质量标注的 AI bundle 与健康/就绪对象；新到达行无需重启采集器即可可见。

### 7.5 Consumer layer
**EN:** (5) **Consumer layer.** Frozen-prompt LLM / rule agents call an OpenAI-compatible adapter (temperature \(0\)) under Compiled, Ungated, or Raw treatments.

**中文:** (5) **消费层。** 冻结提示的 LLM / 规则智能体通过 OpenAI 兼容适配器（温度 \(0\)）在 Compiled、Ungated 或 Raw 处理下调用。

### 7.6 Table — Anonymized module map (caption + headers)
**EN:** Table caption: Anonymized module map (systems view). Columns: Module | Responsibility. Rows: Collectors — Ingest multi-band series with timestamps / vintages; Vintage stores — Persist raw, market, and analytics objects; BandPIT compiler — Previous-close readiness, \(\Pi_t\), WMI/ACWMI; Bundle builder — Assemble complete/honest/auditable JSON world state; Shock index \(O_t\) — Query availability outages for quasi-exogenous levers; LLM adapter — OpenAI-compatible chat; frozen prompts; temp.\ \(0\); Eval harness — Compiled/Ungated/Raw/Blind sampling, transcripts, tables.

**中文:** 表题：匿名化模块图（系统视角）。列头：模块 | 职责。行：Collectors — 以时间戳/vintage 摄取多波段序列；Vintage stores — 持久化原始、市场与分析对象；BandPIT compiler — 前收盘就绪度、\(\Pi_t\)、WMI/ACWMI；Bundle builder — 组装完整/诚实/可审计的 JSON 世界状态；Shock index \(O_t\) — 查询可用性中断作为准外生杠杆；LLM adapter — OpenAI 兼容聊天；冻结提示；温度 \(0\)；Eval harness — Compiled/Ungated/Raw/Blind 抽样、转录与表格。

### 7.7 Figure — Runtime architecture (caption)
**EN:** Figure caption: Anonymized runtime architecture. Five numbered layers map raw multi-band evidence to a typed world-bundle contract; the consumer layer defines the frozen four-arm protocol (Compiled / Ungated / Raw / Blind). Live abstention outcomes are in Sec.~\ref{sec:exp}; Blind has no feed from the service layer.

**中文:** 图题：匿名化运行时架构。五个编号层将原始多波段证据映射到类型化世界包契约；消费层定义冻结的四臂协议（Compiled / Ungated / Raw / Blind）。现场弃权结果见第~\ref{sec:exp} 节；Blind 无来自服务层的喂入。

### 7.8 Data flow lead-in
**EN:** Data flow: inputs, processing, outputs. Table~\ref{tab:dataflow} traces the runtime end-to-end. *Inputs*: the evaluation archive populates three public bands---exchange klines, funding, and open interest via REST; daily macro risk indices (equity volatility, dollar index) with `available_at` vintages; and aggregate stablecoin circulation---each row stored with its observation timestamp. *Processing*: for every asset-day, BandPIT selects the latest observation with timestamp \(\le(t{-}1)\,23{:}59\), grades it fresh/stale/missing against per-band age thresholds, aggregates breadth/stability/honesty into WMI and regime-conditional ACWMI, derives content tilts (5-day macro-index changes; 7-day stablecoin-flow slope; return momentum), and logs availability shocks \(O_t\). *Outputs*: a \(\sim\)3{,}990-row PIT panel (10 assets \(\times\) 399 days), per-day world bundles scoped to these three archive bands (Listing~\ref{lst:bundle}), and the consumer transcripts/tables behind Section~\ref{sec:exp}.

**中文:** **数据流：输入、处理、输出。** 表~\ref{tab:dataflow} 端到端追踪运行时。*输入*：评估档案填充三个公共波段——经 REST 的交易所 K 线、资金费率与未平仓；带 `available_at` vintage 的日度宏观风险指数（权益波动、美元指数）；以及聚合稳定币流通量——每行以其观测时间戳存储。*处理*：对每个资产日，BandPIT 选取时间戳 \(\le(t{-}1)\,23{:}59\) 的最新观测，按波段年龄阈值评为新鲜/过期/缺失，将广度/稳定性/诚实性聚合为 WMI 与状态条件 ACWMI，导出内容倾斜（5 日宏观指数变化；7 日稳定币流量斜率；收益动量），并记录可用性冲击 \(O_t\)。*输出*：约 3,990 行 PIT 面板（10 资产 \(\times\) 399 日）、限定于这三档档案波段的每日世界包（代码清单~\ref{lst:bundle}），以及第~\ref{sec:exp} 节背后的消费转录/表格。

### 7.9 Table — Data flow (caption + headers)
**EN:** Table caption: Data flow through the runtime (three-band evaluation archive). Columns: Band | Fetched (raw) | Emitted (bundle). Rows: exchange — OHLCV klines (1h/1d), funding, open interest, orderbook → \(\mathrm{mom5}\); band status/age; funding context; macro — equity-vol and dollar indices; vintaged macro series → \(\mathrm{macro\_tilt}\) (5d changes); status/age; alternative — aggregate stablecoin circulation → \(\mathrm{alt\_tilt}\) (7d flow slope); status/age; payoff — daily closes (external reference) → close-to-close \(r_t\) for scoring only; derived — --- → \(B,U,H\), WMI, ACWMI, `should_ai_abstain`, `thin_world`, \(O_t\), `evidence_ids`.

**中文:** 表题：运行时数据流（三波段评估档案）。列头：波段 | 获取（原始）| 发射（bundle）。行：exchange — OHLCV K 线（1h/1d）、资金费率、未平仓、订单簿 → \(\mathrm{mom5}\)；波段状态/年龄；资金费率上下文；macro — 权益波动与美元指数；vintage 宏观序列 → \(\mathrm{macro\_tilt}\)（5 日变化）；状态/年龄；alternative — 聚合稳定币流通 → \(\mathrm{alt\_tilt}\)（7 日流量斜率）；状态/年龄；payoff — 日收盘（外部参考）→ 仅用于评分的收盘对收盘 \(r_t\)；derived — --- → \(B,U,H\)、WMI、ACWMI、`should_ai_abstain`、`thin_world`、\(O_t\)、`evidence_ids`。

### 7.10 PIT previous-close clock
**EN:** PIT previous-close clock. For calendar day \(t\), the decision information set is reconstructed at \((t{-}1)\,23{:}59\). The payoff is the same-calendar-day close-to-close return \(r_t\). This removes same-day look-ahead in band statuses and vintaged macro/alternative content. The bundle records the clock in `decision_asof`, and every live run pins `timing_protocol` to the previous-close protocol.

**中文:** **PIT 前收盘时钟。** 对日历日 \(t\)，决策信息集在 \((t{-}1)\,23{:}59\) 重建。收益是同日历日收盘对收盘收益 \(r_t\)。这消除波段状态与 vintage 宏观/另类内容中的同日前视。bundle 在 `decision_asof` 中记录时钟，每次现场运行将 `timing_protocol` 固定为前收盘协议。

### 7.11 World bundle contract
**EN:** World bundle contract. Table~\ref{tab:schema} lists field groups. Listing~\ref{lst:bundle} shows a compact Compiled example from the OOS panel: exchange missing so \(2/3\) archive bands ready, WMI low, `should_ai_abstain=true`, and `evidence_ids` binding actions to disclosed bands/tilts. Ungated removes the hard boolean (and threshold) but keeps numeric WMI/ACWMI and completeness. Raw retains only `mom5` (plus a non-informative noise bit).

**中文:** **世界包契约。** 表~\ref{tab:schema} 列出字段组。代码清单~\ref{lst:bundle} 展示来自 OOS 面板的紧凑 Compiled 示例：交易所缺失故 \(2/3\) 档案波段就绪，WMI 低，`should_ai_abstain=true`，且 `evidence_ids` 将行动绑定到已披露波段/倾斜。Ungated 移除硬布尔量（及阈值）但保留数值 WMI/ACWMI 与完整性。Raw 仅保留 `mom5`（外加一个无信息噪声位）。

### 7.12 Table — World bundle field groups
**EN:** Table caption: World bundle field groups. Columns: Group | Fields. Rows: Timing — `decision_asof`, previous-close protocol; Completeness — \(n_{\mathrm{ready/limited/missing}}\), band statuses; Honesty — \(B,U,H\), main-view / stale gates; Quality — WMI, ACWMI, `should_ai_abstain`, `thin_world`; Content — \(\mathrm{macro\_tilt}\), \(\mathrm{alt\_tilt}\), regime, cascade; Audit — `evidence_ids`, EAR required.

**中文:** 表题：世界包字段组。列头：组 | 字段。行：Timing — `decision_asof`、前收盘协议；Completeness — \(n_{\mathrm{ready/limited/missing}}\)、波段状态；Honesty — \(B,U,H\)、主视图/过期门控；Quality — WMI、ACWMI、`should_ai_abstain`、`thin_world`；Content — \(\mathrm{macro\_tilt}\)、\(\mathrm{alt\_tilt}\)、regime、cascade；Audit — `evidence_ids`、要求 EAR。

### 7.13 Listing — Compact Compiled bundle (caption only; code stays EN)
**EN:** Listing caption: Compact Compiled bundle example (OOS exchange gap).

**中文:** 代码清单题：紧凑 Compiled bundle 示例（OOS 交易所缺口）。（代码正文保持英文原样。）

### 7.14 Four information arms — Compiled
**EN:** Four information arms and LLM adapter. **Compiled (hard contract):** full bundle; frozen prompt *requires* abstain when `should_ai_abstain` is true.

**中文:** **四信息臂与 LLM 适配器。** **Compiled（硬契约）：** 完整 bundle；冻结提示在 `should_ai_abstain` 为真时*要求*弃权。

### 7.15 Ungated
**EN:** **Ungated (disclosure control):** same content, completeness, and numeric WMI; *no* hard flag; soft prompt asks the model to judge thinness (disclosure without enforcement).

**中文:** **Ungated（披露对照）：** 同内容、完整性与数值 WMI；*无*硬标志；软提示要求模型判断稀薄性（有披露无强制）。

### 7.16 Raw
**EN:** **Raw (thin integration):** `mom5` only; no quality index or abstention guidance. This matches a common production wiring (price feature in, action out), not a deliberately crippled baseline: the missing piece is the quality/abstain contract, not richer raw features.

**中文:** **Raw（薄集成）：** 仅 `mom5`；无质量指数或弃权指导。这匹配常见生产接线（价格特征进、行动出），而非故意致残基线：缺失的是质量/弃权契约，而非更丰富的原始特征。

### 7.17 Blind
**EN:** **Blind (direct ask):** ``Today is \(d\). How should I trade \(a\)?'' with *no* data feed.

**中文:** **Blind（直接问）：** 「今天是 \(d\)。我该如何交易 \(a\)？」且*无*数据喂入。

### 7.18 Actions and metrics
**EN:** Actions \(\in\{\mathrm{bullish},\mathrm{bearish},\mathrm{neutral},\mathrm{abstain}\}\). Primary metrics are thin-world abstain rate and EAR proxy; CE is reported as avoided loss under refusal, not as an alpha claim. The evaluation archive is the three-band set \(\{\mathrm{exchange},\mathrm{macro},\mathrm{alternative}\}\) (Figure~\ref{fig:ready}): macro and alternative stay ready throughout; exchange readiness drops in the later OOS window and defines the within-archive *band-thick* contrast below. The refuse rule sets `should_ai_abstain` when \(\mathrm{WMI}<0.2\). On this scarce OOS panel \(\max\mathrm{WMI}\approx 0.093\), so every day is thin and Compiled never opens---a refuse-under-sparse stress test, not a claim the contract never allows action. The adapter uses OpenAI-compatible chat completions; credentials stay in environment variables (never in artifacts).

**中文:** 行动 \(\in\{\mathrm{bullish},\mathrm{bearish},\mathrm{neutral},\mathrm{abstain}\}\)。主指标是稀薄世界弃权率与 EAR 代理；CE 报告为拒绝下的避免损失，而非 alpha 主张。评估档案是三波段集合 \(\{\mathrm{exchange},\mathrm{macro},\mathrm{alternative}\}\)（图~\ref{fig:ready}）：宏观与另类全程就绪；交易所就绪度在后期 OOS 窗口下降，并定义下文档案内*波段齐全*对照。拒绝规则在 \(\mathrm{WMI}<0.2\) 时置 `should_ai_abstain`。在此稀薄 OOS 面板上 \(\max\mathrm{WMI}\approx 0.093\)，故每日皆稀薄且 Compiled 从不开放——这是稀疏下拒绝压力测试，而非主张契约永不允许行动。适配器使用 OpenAI 兼容 chat completions；凭证留在环境变量（从不进入制品）。

### 7.19 Figure — Band readiness (caption)
**EN:** Figure caption: PIT readiness for the three-band evaluation archive (solid / dashed / dotted for grayscale).

**中文:** 图题：三波段评估档案的 PIT 就绪度（实线/虚线/点线以便灰度印刷）。

### 7.20 Frozen prompt contracts (intro)
**EN:** Frozen prompt contracts. Listings~\ref{lst:prompt-c}--\ref{lst:prompt-u} excerpt the frozen Compiled and Ungated contracts (temperature \(0\); action schema identical). The only intentional difference is hard vs.\ soft abstention. Raw prompts omit world-quality language entirely.

**中文:** **冻结提示契约。** 代码清单~\ref{lst:prompt-c}--\ref{lst:prompt-u} 摘录冻结的 Compiled 与 Ungated 契约（温度 \(0\)；行动 schema 相同）。唯一有意差异是硬 vs. 软弃权。Raw 提示完全省略世界质量语言。

### 7.21 Listing — Compiled contract (caption)
**EN:** Listing caption: Compiled contract (excerpt).

**中文:** 代码清单题：Compiled 契约（摘录）。（代码正文保持英文原样。）

### 7.22 Listing — Ungated soft contract (caption)
**EN:** Listing caption: Ungated soft contract (excerpt).

**中文:** 代码清单题：Ungated 软契约（摘录）。（代码正文保持英文原样。）

### 7.23 Why hard refusal is not a confound
**EN:** Why hard refusal is not a confound. Compiled abstention is partly prompt obedience, and that is intentional: when \(q(W_t)\) is low, production agents need an enforceable refuse interface (Prop.~\ref{prop:abstain}). Ungated measures soft judgment from disclosure alone; Raw measures the common price-signal-only integration. The headline result is that the hard contract is reliable across vendors; soft refusal is not.

**中文:** **为何硬拒绝不是混杂。** Compiled 弃权部分是提示服从，且这是有意的：当 \(q(W_t)\) 低时，生产智能体需要可强制的拒绝接口（命题~\ref{prop:abstain}）。Ungated 度量仅来自披露的软判断；Raw 度量常见的仅价格信号集成。头条结果是硬契约跨厂商可靠；软拒绝则否。

### 7.24 Service surface and reproducibility
**EN:** Service surface and reproducibility. The service layer exposes read-only objects used by the consumer harness: (i)~quality-tagged world bundles; (ii)~band readiness / WMI--ACWMI snapshots; (iii)~availability-shock queries \(O_t\); (iv)~health metadata disclosing whether paper engines or production proxies hydrate ACWMI inputs. Collectors and the logic pipeline can run as supervised jobs; the API reads stores live, so newly compiled rows appear without process bounce. For review we freeze prompts, temperature, action schema, IS/OOS cut, and sampling seed; model IDs and an OpenAI-compatible base URL are configuration, not estimands. Credentials never enter committed artifacts. Upon acceptance we will release an anonymized repository with the consumer harness, frozen prompts, and table-reproduction scripts.

**中文:** **服务面与可复现性。** 服务层暴露消费 harness 使用的只读对象：(i)~质量标注世界包；(ii)~波段就绪度 / WMI--ACWMI 快照；(iii)~可用性冲击查询 \(O_t\)；(iv)~健康元数据，披露论文引擎或生产代理是否灌入 ACWMI 输入。采集器与逻辑流水线可作为受监督作业运行；API 实时读存储，新编译行无需进程重启即可出现。评审中我们冻结提示、温度、行动 schema、IS/OOS 切分与抽样种子；模型 ID 与 OpenAI 兼容 base URL 是配置而非估计量。凭证从不进入已提交制品。接受后将发布含消费 harness、冻结提示与表格复现脚本的匿名化仓库。

---

## 8. 第 5 节 Experiments

### 8.1 Setup
**EN:** Setup. PIT panel \(\sim\)399 days, 10 liquid names, previous-close clock, chronological IS/OOS \(200/200\) days (\(\approx\)2{,}000 OOS asset-days). Live RQ1 uses the *same* stratified \(100\) OOS asset-days across arms (seed fixed), temperature \(0\), frozen prompts, and an OpenAI-compatible gateway; a checkpointed full-OOS sweep tests population scale. Vendor models are GPT-, DeepSeek-, GLM-, and Gemini-class flash/mini IDs listed in Table~\ref{tab:llm}. Scarce/thin labels bind on OOS by design; Sec.~\ref{sec:econ} covers fully populated days.

**中文:** **设置。** PIT 面板约 399 日、10 个流动性品种、前收盘时钟、按时间 IS/OOS \(200/200\) 日（约 2{,}000 个 OOS 资产日）。现场 RQ1 在各臂使用*相同*的分层 \(100\) 个 OOS 资产日（种子固定）、温度 \(0\)、冻结提示与 OpenAI 兼容网关；检查点化的全 OOS 扫描检验总体规模。厂商模型为表~\ref{tab:llm} 所列 GPT-、DeepSeek-、GLM- 与 Gemini 类 flash/mini ID。稀薄/稀缺标签按设计在 OOS 上绑定；第~\ref{sec:econ} 节覆盖充分填充的日期。

### 8.2 RQ1 lead — headline result
**EN:** RQ1 (primary): Live interface behavior across information arms. Table~\ref{tab:llm} and Figure~\ref{fig:und} report the headline result; all arms share the same \(100\) OOS asset-days. Under Compiled, all four models abstain on every thin-world day (thin-abs.\ \(1.0\)); rationales cite world fields on \(93\)--\(99\%\) of days. This is prompt-contract obedience by design, not spontaneous thinness discovery. Under Ungated, mean thin-abs.\ falls to \(0.68\) (range \(0.43\)--\(0.86\)): DeepSeek and GLM stay above \(0.80\), GPT drops to \(0.63\), and `gemini-3.5-flash-lite` falls to \(0.43\) and trades. Unconditional Ungated CE (abstain days as cash) spans \(-1.04\) to \(+0.02\); restricting to days the model actually acts, three of four vendors post large negative act-conditional CE (mean \({\approx}{-}1.9\)), so soft judgment does not safely convert disclosure into profitable action. Under Raw, abstain rates are \(0.04\)--\(0.75\) with substantial directional mass (Table~\ref{tab:mix}). Mean \(\Delta\)CE (Compiled$-$Raw) is \(+1.07\) and positive for every vendor, because Compiled sits out losses that Raw incurs on sparse support.

**中文:** **RQ1（主）：跨信息臂的现场接口行为。** 表~\ref{tab:llm} 与图~\ref{fig:und} 报告头条结果；各臂共享相同的 \(100\) 个 OOS 资产日。在 Compiled 下，四个模型在每个稀薄世界日弃权（稀薄弃权 \(1.0\)）；理由在 \(93\)--\(99\%\) 的日子引用世界字段。这是按设计的提示契约服从，而非自发稀薄性发现。在 Ungated 下，均值稀薄弃权降至 \(0.68\)（范围 \(0.43\)--\(0.86\)）：DeepSeek 与 GLM 保持在 \(0.80\) 以上，GPT 降至 \(0.63\)，而 `gemini-3.5-flash-lite` 降至 \(0.43\) 并交易。无条件 Ungated CE（弃权日视为现金）跨度 \(-1.04\) 到 \(+0.02\)；限定到模型实际行动的日子，四厂商中三家给出大幅负的行动条件 CE（均值约 \(-1.9\)），故软判断不能安全地把披露转化为盈利行动。在 Raw 下，弃权率为 \(0.04\)--\(0.75\)，并有大量方向性行动（表~\ref{tab:mix}）。均值 \(\Delta\)CE（Compiled$-$Raw）为 \(+1.07\) 且对每个厂商为正，因为 Compiled 避开了 Raw 在稀疏支撑上招致的损失。

### 8.3 Table — Live abstention rates
**EN:** Table caption: Live abstention rates on identical \(100\) OOS asset-days (Wilson 95\% CIs); Blind abstains \(1.0\) for every model. \(\Delta\)CE is avoided loss, not an alpha claim. Columns: Model | Thin C | Thin U [CI] | Abs.\ R [CI] | \(\Delta\)CE. Mean row: Thin C \(1.00\); Thin U \(0.68\); \(\Delta\)CE \(+1.07\).

**中文:** 表题：相同 \(100\) 个 OOS 资产日上的现场弃权率（Wilson 95\% CI）；Blind 对每个模型弃权 \(1.0\)。\(\Delta\)CE 是避免损失，非 alpha 主张。列头：模型 | 稀薄 C | 稀薄 U［CI］| 弃权 R［CI］| \(\Delta\)CE。均值行：稀薄 C \(1.00\)；稀薄 U \(0.68\)；\(\Delta\)CE \(+1.07\)。（数字保持原样。）

### 8.4 Figure — Four-arm ladder (caption)
**EN:** Figure caption: Live four-arm abstention rates (same \(100\) days; Wilson 95\% CIs). Blind refuses; Raw over-trades; Ungated is vendor-dependent; Compiled enforces the typed refuse contract.

**中文:** 图题：现场四臂弃权率（相同 \(100\) 日；Wilson 95\% CI）。Blind 拒绝；Raw 过度交易；Ungated 依赖厂商；Compiled 强制类型化拒绝契约。

### 8.5 Table — Raw-arm action mix
**EN:** Table caption: Raw-arm action mix (\(100\) days). Compiled abstains on all thin days; Blind (direct ask, no feed) abstains \(100\%\) for every model. Columns: Model | Abs. | Bull. | Bear. | Neut.

**中文:** 表题：Raw 臂行动混合（\(100\) 日）。Compiled 在所有稀薄日弃权；Blind（直接问、无喂入）对每个模型弃权 \(100\%\)。列头：模型 | 弃权 | 看涨 | 看跌 | 中性。（数字保持原样。）

### 8.6 Full-OOS replication
**EN:** Full-OOS replication. To check that the \(100\)-day ranking is not a subsample artifact, we checkpointed the three data arms on the *full* OOS panel (\(n{=}2000\) asset-days; every OOS day is thin-world under the scarce-support design). Compiled thin-abstain is \(1.000\) {\scriptsize[.998,\,1.000]} for all four vendors. Ungated rates tighten the Wilson intervals, with mean thin-abs.\ \(0.56\) (GPT \(0.666\) {\scriptsize[.645,\,.686]}; GLM \(0.679\) {\scriptsize[.654,\,.703]} on \(n{=}1402\) completed calls; DeepSeek \(0.540\) {\scriptsize[.518,\,.561]}; Gemini \(0.359\) {\scriptsize[.338,\,.380]}). Vendor ranking within Ungated shifts relative to the \(100\)-day sample (DeepSeek is less cautious at scale), but no vendor matches Compiled. Where Raw is trusted, over-trading remains sharp: GPT and Gemini abstain at \(0.000\) {\scriptsize[.000,\,.002]}; DeepSeek stays cautious at \(0.748\) {\scriptsize[.728,\,.767]} (\(n{=}1925\)). Because the full OOS window is entirely thin, Compiled CE is identically zero by construction; thick-day economics are deferred to Sec.~\ref{sec:econ}.

**中文:** **全样本外复现。** 为检查 \(100\) 日排序不是子样本伪影，我们在*完整* OOS 面板上对三个数据臂做检查点（\(n{=}2000\) 资产日；在稀薄支撑设计下每个 OOS 日皆为稀薄世界）。Compiled 稀薄弃权对全部四厂商为 \(1.000\)［.998,\,1.000］。Ungated 率收紧 Wilson 区间，均值稀薄弃权 \(0.56\)（GPT \(0.666\)［.645,\,.686］；GLM \(0.679\)［.654,\,.703］，\(n{=}1402\) 完成调用；DeepSeek \(0.540\)［.518,\,.561］；Gemini \(0.359\)［.338,\,.380］）。Ungated 内厂商排序相对 \(100\) 日样本有偏移（DeepSeek 在规模上更不谨慎），但无一厂商匹配 Compiled。在信任 Raw 处，过度交易仍尖锐：GPT 与 Gemini 弃权为 \(0.000\)［.000,\,.002］；DeepSeek 保持谨慎 \(0.748\)［.728,\,.767］（\(n{=}1925\)）。因完整 OOS 窗口全为稀薄，Compiled CE 按构造恒为零；厚日经济推迟至第~\ref{sec:econ} 节。

### 8.7 Blind arm
**EN:** Blind arm. On the same \(100\) asset-days, the no-feed prompt *``Today is \(d\). How should I trade BTC?''* yields abstention on \(100\%\) of days for all four models (CE \(=0\); zero directional actions). Without a feed, the models refuse. The costly failure mode is the middle case: the same model given a Raw fragment starts trading (abstain as low as \(0.04\)) and loses. Compiled matches Blind's refusal on thin days by contract, while still exposing the structured world that RQ2 and RQ3 show is usable.

**中文:** **Blind 臂。** 在相同 \(100\) 资产日上，无喂入提示*「今天是 \(d\)。我该如何交易 BTC？」* 对全部四个模型在 \(100\%\) 日子弃权（CE \(=0\)；零方向行动）。没有喂入时，模型拒绝。代价高昂的失败模式是中间情形：同一模型给定 Raw 碎片后开始交易（弃权低至 \(0.04\)）并亏损。Compiled 按契约在稀薄日匹配 Blind 的拒绝，同时仍暴露 RQ2 与 RQ3 表明可用的结构化世界。

### 8.8 Band-thick / open-slice days
**EN:** Band-thick / open-slice days. Archive readiness alone is not a refuse policy. On full-OOS *band-thick* days (all three archive bands ready; \(61\%\) of OOS, \(n{\approx}1224\); identical to \(\mathrm{WMI}\ge 0.05\)), production Compiled still abstains at \(1.0\) because WMI remains below \(0.2\). Ungated soft judgment only partially recovers (mean abs.\ \({\approx}0.48\)), but its CE on this open slice is *positive* for every vendor (mean \({\approx}{+}0.29\); Table~\ref{tab:thick})---the closest live probe of open-world behavior. Raw remains risky in the middle: GPT and Gemini abstain at \(0.0\) with CE \(-0.28\) and \(-0.25\). A readiness dashboard would miss this failure mode; the typed contract continues to refuse at the production gate.

**中文:** **波段齐全 / 开放切片日。** 仅档案就绪度不是拒绝策略。在全 OOS *波段齐全*日（三档档案波段皆就绪；占 OOS 的 \(61\%\)，\(n{\approx}1224\)；等同于 \(\mathrm{WMI}\ge 0.05\)），生产 Compiled 仍以 \(1.0\) 弃权，因为 WMI 仍低于 \(0.2\)。Ungated 软判断仅部分恢复（均值弃权约 \(0.48\)），但其在该开放切片上的 CE 对每个厂商皆为*正*（均值约 \(+0.29\)；表~\ref{tab:thick}）——这是最接近的开放世界行为现场探针。Raw 在中间仍危险：GPT 与 Gemini 弃权为 \(0.0\)，CE 为 \(-0.28\) 与 \(-0.25\)。就绪度仪表盘会错过这一失败模式；类型化契约在生产门继续拒绝。

### 8.9 Table — Band-thick / open slice
**EN:** Table caption: Full-OOS band-thick / open slice (\(3/3\) ready \(\equiv\) \(\mathrm{WMI}\ge 0.05\)). Production Compiled abstains \(1.0\); live Ungated CE is positive; Raw over-acts. Columns: Model | Abs.\ U | CE U | Act-CE U | Abs.\ R | CE R. Footnote: \(^*\)Raw GLM \(n{=}398\); Ungated GLM \(n{=}932\); others \(n{=}1224\).

**中文:** 表题：全 OOS 波段齐全 / 开放切片（\(3/3\) 就绪 \(\equiv\) \(\mathrm{WMI}\ge 0.05\)）。生产 Compiled 弃权 \(1.0\)；现场 Ungated CE 为正；Raw 过度行动。列头：模型 | 弃权 U | CE U | 行动条件 CE U | 弃权 R | CE R。脚注：\(^*\)Raw GLM \(n{=}398\)；Ungated GLM \(n{=}932\)；其余 \(n{=}1224\)。（数字保持原样。）

### 8.10 Inside the Ungated arm
**EN:** Inside the Ungated arm. Ungated rationales cite disclosed world fields on \(53\)--\(93\%\) of days, so models *read* the world; they differ in acting on it. Vendor-specific caution---not missing disclosure---drives the gap the typed contract closes.

**中文:** **Ungated 臂内部。** Ungated 理由在 \(53\)--\(93\%\) 的日子引用已披露世界字段，故模型*读到*了世界；差异在于是否据此行动。厂商特异的谨慎——而非缺失披露——驱动类型化契约所弥合的差距。

### 8.11 Offline diagnostics
**EN:** Offline diagnostics. World-honoring offline followers abstain at \(1.0\) on full OOS; momentum-only mocks ignore thin-world flags (thin-abs.\ \(0\)). Offline results are protocol checks; live vendors are the main claim.

**中文:** **离线诊断。** 遵从世界的离线跟随者在全 OOS 上弃权 \(1.0\)；仅动量的 mock 忽略稀薄世界标志（稀薄弃权 \(0\)）。离线结果是协议检查；现场厂商是主主张。

### 8.12 When would the contract open?
**EN:** When would the contract open? Compiled never trades under the production threshold because \(\max\mathrm{WMI}\approx 0.093{<}0.2\)---the scarce-support stress test. The contract is not permanently closed: \(\mathrm{WMI}\ge 0.05\) marks \(n{=}1224\) open days, and on that slice ACWMI already clears \(0.25\), so a WMI gate of \(0.05\) would set `should_ai_abstain=false` everywhere. Table~\ref{tab:thick} already reports live Ungated on those days (positive CE); the secondary no-LLM content rule also beats momentum there (\(\Delta\mathrm{CE}{=}0.315\); Table~\ref{tab:dense}). Production Compiled remains refuse-first at \(0.2\); a Compiled-with-open-boolean sweep is harness-supported for denser vintages.

**中文:** **契约何时开放？** 在生产阈值下 Compiled 从不交易，因为 \(\max\mathrm{WMI}\approx 0.093{<}0.2\)——稀薄支撑压力测试。契约并非永久关闭：\(\mathrm{WMI}\ge 0.05\) 标记 \(n{=}1224\) 个开放日，且该切片上 ACWMI 已超过 \(0.25\)，故 WMI 门 \(0.05\) 会处处置 `should_ai_abstain=false`。表~\ref{tab:thick} 已报告那些日子上的现场 Ungated（正 CE）；次要无 LLM 内容规则也在彼处击败动量（\(\Delta\mathrm{CE}{=}0.315\)；表~\ref{tab:dense}）。生产 Compiled 在 \(0.2\) 保持拒绝优先；对更密 vintage，harness 支持 Compiled-with-open-boolean 扫描。

### 8.13 RQ2 — Grounding workflow
**EN:** RQ2: Non-trading cognition---grounding workflow. The compiled world should also support analysis, not only trade/abstain decisions. We run a live multi-step *grounding workflow* on \(50\) OOS asset-days per arm. Given Compiled or Raw inputs, the model must (i)~list which of \(\{\mathrm{exchange},\mathrm{macro},\mathrm{alternative}\}\) are ready, (ii)~list which are missing, (iii)~report \(\mathrm{sign}(\mathrm{macro\_tilt})\) and \(\mathrm{sign}(\mathrm{alt\_tilt})\), and (iv)~judge sufficiency. Steps (i)--(iii) are scored against PIT ground truth. Table~\ref{tab:grounding}: with the Compiled bundle, mean ready-band F1 \(0.97\), missing-band F1 \(0.97\), and tilt-sign accuracy \(0.97\); with Raw, the same scores collapse to \(0.04\), \(0.23\), and \(0.19\). Sufficiency judgments alone are weak once completeness is scoped to real archive bands---models may call a \(3/3\)-ready day ``sufficient'' while WMI still marks the world thin. The sharper claim is verifiability: only the compiled world lets the model state what is ready, missing, and signed, in a form that can be checked. This is the analyst-facing counterpart of Prop.~\ref{prop:recon}'s missingness term.

**中文:** **RQ2：非交易认知——接地工作流。** 编译世界也应支持分析，而非仅交易/弃权决策。我们在每臂 \(50\) 个 OOS 资产日上运行现场多步*接地工作流*。给定 Compiled 或 Raw 输入，模型必须 (i)~列出 \(\{\mathrm{exchange},\mathrm{macro},\mathrm{alternative}\}\) 中哪些就绪，(ii)~列出哪些缺失，(iii)~报告 \(\mathrm{sign}(\mathrm{macro\_tilt})\) 与 \(\mathrm{sign}(\mathrm{alt\_tilt})\)，以及 (iv)~判断充分性。步骤 (i)--(iii) 对照 PIT 真值评分。表~\ref{tab:grounding}：有 Compiled 包时，均值就绪波段 F1 \(0.97\)、缺失波段 F1 \(0.97\)、倾斜符号准确率 \(0.97\)；有 Raw 时，相同分数坍缩至 \(0.04\)、\(0.23\) 与 \(0.19\)。一旦完整性限定到真实档案波段，仅充分性判断很弱——模型可能称 \(3/3\) 就绪日「充分」，而 WMI 仍标记世界稀薄。更锋利的主张是可核验性：只有编译世界让模型以可检查形式陈述何为就绪、缺失与符号。这是命题~\ref{prop:recon} 缺失项的面向分析师对应物。

### 8.14 Table — Grounding workflow
**EN:** Table caption: Grounding workflow (\(50\) days): ready / missing / tilt signs. Columns: Model | Ready F1 (C, R) | Missing F1 (C, R) | Tilt-sign acc. (C, R). Mean: C \(0.97\) / R \(0.04\), \(0.97\) / \(0.23\), \(0.97\) / \(0.19\).

**中文:** 表题：接地工作流（\(50\) 日）：就绪 / 缺失 / 倾斜符号。列头：模型 | 就绪 F1（C, R）| 缺失 F1（C, R）| 倾斜符号准确率（C, R）。均值：C \(0.97\) / R \(0.04\)，\(0.97\) / \(0.23\)，\(0.97\) / \(0.19\)。（数字保持原样。）

### 8.15 RQ3 — Secondary content probe
**EN:** RQ3: Secondary content probe. RQ1--RQ2 concern the interface. RQ3 asks whether the compiled tilts are economically nonempty. A transparent rule shares return inputs with momentum and adds vintaged \(\mathrm{macro\_tilt}\) / \(\mathrm{alt\_tilt}\)---no LLM in the loop. Out-of-sample (\(199\) days \(\times\) \(10\) assets) this content rule beats the baselines (Table~\ref{tab:econ}, Figure~\ref{fig:econ}): Sharpe \(0.764\) / CE \(+0.130\) versus momentum (\(0.096\), \(-0.206\)) and buy-and-hold (\(-1.404\), \(-1.163\)). The pre-specified contrast mechanism $-$ momentum is significant under block bootstrap (\(\Delta\mathrm{CE}{=}0.334\), \(p{=}0.034\)). \(\Delta\mathrm{CE}\) is positive for all ten assets (Figure~\ref{fig:econ}, right). LOBO (Prop.~\ref{prop:lobo}) attributes the gain to band content (deleting macro/alternative collapses to momentum); gaps survive \(10\)--\(25\)bps costs. A \(2017\)--\(2026\) audit with non-vintaged proxy tilts shows no edge (\(\Delta\mathrm{CE}\approx 0\), \(p{=}0.81\)): value appears where the vintage-compiled world exists. The result supports nonempty tilts, not an LLM trading ranking.

**中文:** **RQ3：次要内容探针。** RQ1--RQ2 关乎接口。RQ3 询问编译倾斜是否经济上非空。一条透明规则与动量共享收益输入并加入 vintage \(\mathrm{macro\_tilt}\) / \(\mathrm{alt\_tilt}\)——环中无 LLM。样本外（\(199\) 日 \(\times\) \(10\) 资产）该内容规则击败基线（表~\ref{tab:econ}，图~\ref{fig:econ}）：Sharpe \(0.764\) / CE \(+0.130\)，对比动量（\(0.096\)，\(-0.206\)）与买入持有（\(-1.404\)，\(-1.163\)）。预指定对照 mechanism $-$ momentum 在块 bootstrap 下显著（\(\Delta\mathrm{CE}{=}0.334\)，\(p{=}0.034\)）。\(\Delta\mathrm{CE}\) 对全部十个资产为正（图~\ref{fig:econ}，右）。LOBO（命题~\ref{prop:lobo}）将增益归因于波段内容（删除宏观/另类坍缩为动量）；差距在 \(10\)--\(25\)bps 成本下仍存。用非 vintage 代理倾斜的 \(2017\)--\(2026\) 审计无优势（\(\Delta\mathrm{CE}\approx 0\)，\(p{=}0.81\)）：价值出现在 vintage 编译世界存在之处。结果支持倾斜非空，而非 LLM 交易排行榜。

### 8.16 Within-archive dense / open world
**EN:** Within-archive dense / open world. Among the three archive bands, \(61\%\) of OOS asset-days are band-thick (\(3/3\) ready) and \(39\%\) are band-thin (exchange gap; Figure~\ref{fig:ready}). On this panel, band-thick coincides with counterfactual open days (\(\mathrm{WMI}\ge 0.05\)). Table~\ref{tab:dense}: on that open/thick slice the content rule acts and beats momentum (\(\Delta\mathrm{CE}{=}0.315\); CE \(+0.061\) vs.\ \(-0.254\)), stronger than on exchange-gap days (\(0.129\))---complementary to RQ1's refuse-under-thin test.

**中文:** **档案内稠密 / 开放世界。** 在三档档案波段中，\(61\%\) 的 OOS 资产日为波段齐全（\(3/3\) 就绪），\(39\%\) 为波段稀薄（交易所缺口；图~\ref{fig:ready}）。在此面板上，波段齐全与反事实开放日（\(\mathrm{WMI}\ge 0.05\)）重合。表~\ref{tab:dense}：在该开放/齐全切片上内容规则行动并击败动量（\(\Delta\mathrm{CE}{=}0.315\)；CE \(+0.061\) vs.\ \(-0.254\)），强于交易所缺口日（\(0.129\)）——与 RQ1 的稀薄下拒绝检验互补。

### 8.17 Table — Secondary content probe
**EN:** Table caption: Secondary content probe: world-model rule vs.\ traditional baselines (no LLM). Columns: Policy / contrast | Sharpe | CE. Rows include Buy-and-hold, Momentum always, World-model content rule, Mechanism $-$ Momentum.

**中文:** 表题：次要内容探针：世界模型规则 vs. 传统基线（无 LLM）。列头：策略 / 对照 | Sharpe | CE。行含买入持有、始终动量、世界模型内容规则、Mechanism $-$ Momentum。（数字保持原样。）

### 8.18 Table — Open/dense split
**EN:** Table caption: Open/dense split of the content probe (OOS). Open \(=\) \(\mathrm{WMI}\ge 0.05\) \(\equiv\) \(3/3\) bands ready. Columns: Slice | Share | Mech CE | \(\Delta\)CE vs mom.

**中文:** 表题：内容探针的开放/稠密切分（OOS）。Open \(=\) \(\mathrm{WMI}\ge 0.05\) \(\equiv\) \(3/3\) 波段就绪。列头：切片 | 份额 | Mech CE | 相对动量的 \(\Delta\)CE。（数字保持原样。）

### 8.19 Figure — OOS economics (caption)
**EN:** Figure caption: Secondary content probe (no LLM). Left: equity curves; right: \(\Delta\)CE vs.\ momentum positive for every asset.

**中文:** 图题：次要内容探针（无 LLM）。左：权益曲线；右：相对动量的 \(\Delta\)CE 对每个资产为正。

### 8.20 Discussion — What the results mean
**EN:** Discussion and threats. What the results mean. Thin days must refuse; soft ``consider abstaining'' text does not. Compiled's hard gate delivers that under live LLMs (RQ1--RQ2). Ungated still acts on most days (\({\approx}0.68\) abstain; GLM \(0.86\) vs.\ Gemini \(0.43\)) and often destroys CE versus cash when it acts. Raw and Blind show unstructured or empty context cannot replace typed readiness. RQ3 is secondary; open-slice live Ungated (Table~\ref{tab:thick}) already shows nonempty CE when the counterfactual opens, while production Compiled stays refuse-first. We claim a typed observation interface---not LLM trading SOTA, not a generative simulator, not a full causal theory of crypto markets.

**中文:** **讨论与威胁。结果意味着什么。** 稀薄日必须拒绝；软性「考虑弃权」文本不行。Compiled 的硬门在现场 LLM 下交付这一点（RQ1--RQ2）。Ungated 仍在多数日子行动（弃权约 \(0.68\)；GLM \(0.86\) vs.\ Gemini \(0.43\)），且行动时相对现金常摧毁 CE。Raw 与 Blind 表明非结构化或空上下文不能替代类型化就绪度。RQ3 是次要的；开放切片现场 Ungated（表~\ref{tab:thick}）已在反事实开放时显示非空 CE，而生产 Compiled 保持拒绝优先。我们主张类型化观测接口——不是 LLM 交易 SOTA，不是生成式模拟器，不是加密市场的完整因果理论。

### 8.21 Positioning vs. related systems
**EN:** Relative to FinMem~/FinAgent~\cite{yu2023finmem,zhang2024finagent} and ICAIF retrieval/debate/judge lines~\cite{choi2025finagentbench,shen2025finsearch,sun2025finresearchbench,duan2025factormad}, we contribute an observation compiler and refuse interface, not a new memory/search/debate router. Relative to return-prediction LLM studies~\cite{lopez2023chatgpt}, we score refusal and auditability before PnL.

**中文:** 相对 FinMem~/FinAgent~\cite{yu2023finmem,zhang2024finagent} 与 ICAIF 检索/辩论/评判线~\cite{choi2025finagentbench,shen2025finsearch,sun2025finresearchbench,duan2025factormad}，我们贡献观测编译器与拒绝接口，而非新的记忆/搜索/辩论路由器。相对收益预测 LLM 研究~\cite{lopez2023chatgpt}，我们在 PnL 之前评分拒绝与可审计性。

### 8.22 Design rationale
**EN:** Design rationale. Three choices are deliberate. (i)~Export gates, not only features: completeness, honesty, and `should_ai_abstain` make refusal machine-readable rather than a free-text apology. (ii)~Previous-close PIT over wall-clock streaming: every live decision cites a recomputable `decision_asof`, avoiding same-day look-ahead. (iii)~Four arms instead of one Sharpe number: Compiled / Ungated / Raw / Blind separates typed enforcement, soft judgment, thin integrations, and no feed.

**中文:** **设计理据。** 三个选择是有意的。(i)~导出门控，而非仅特征：完整性、诚实性与 `should_ai_abstain` 使拒绝机器可读，而非自由文本道歉。(ii)~前收盘 PIT 优于挂钟流式：每个现场决策引用可重算的 `decision_asof`，避免同日前视。(iii)~四臂而非一个 Sharpe 数字：Compiled / Ungated / Raw / Blind 分离类型化强制、软判断、薄集成与无喂入。

### 8.23 Threats to validity
**EN:** Threats to validity. Compiled thin-world abstention is prompt-contract obedience by design---the product interface---not evidence that models spontaneously discover thinness; Ungated is the control that removes the boolean. The archive is scarce (\(\max\mathrm{WMI}\approx 0.093\)), so production Compiled never opens at \(0.2\). Open-slice live evidence uses Ungated on \(\mathrm{WMI}\ge 0.05\) days (Table~\ref{tab:thick}) plus a no-LLM content rule---not a Compiled-with-open-boolean run. Mixed-sample act-conditional Ungated CE is negative for three of four vendors, while the open slice alone is positive. Vendors are flash/mini-class IDs at temperature \(0\); GLM Raw full-OOS is incomplete; denser bands are absent.

**中文:** **效度威胁。** Compiled 稀薄世界弃权按设计是提示契约服从——即产品接口——而非模型自发发现稀薄性的证据；Ungated 是移除布尔量的对照。档案稀薄（\(\max\mathrm{WMI}\approx 0.093\)），故生产 Compiled 在 \(0.2\) 从不开放。开放切片现场证据使用 \(\mathrm{WMI}\ge 0.05\) 日上的 Ungated（表~\ref{tab:thick}）外加无 LLM 内容规则——不是 Compiled-with-open-boolean 运行。混合样本行动条件 Ungated CE 对四厂商中三家为负，而仅开放切片为正。厂商为温度 \(0\) 的 flash/mini 类 ID；GLM Raw 全 OOS 不完整；更密波段缺失。

### 8.24 Scope
**EN:** Scope. We do not claim LLM trading SOTA or generative dynamics. Natural extensions include richer bands and thick-regime live trading once WMI leaves the scarce floor. Camera-ready will restore author identity and release the anonymized harness deferred during review.

**中文:** **范围。** 我们不主张 LLM 交易 SOTA 或生成动力学。自然扩展包括更丰富波段，以及一旦 WMI 离开稀薄底时的厚机制现场交易。Camera-ready 将恢复作者身份并发布评审期间推迟的匿名化 harness。

---

## 9. 第 6 节 Conclusion

### 9.1
**EN:** Public LLMs need a market they can safely observe before they decide. We contribute a typed observation contract---an anonymized state-compiler runtime with a hard refuse flag---for asynchronous crypto feeds. Live arms make the point concrete: Blind refuses, Raw over-trades and loses, Ungated is vendor-dependent, and Compiled enforces thin-world abstain \(1.0\) at the production gate; on the counterfactual open slice, live Ungated posts positive CE while a secondary content rule confirms nonempty tilts. Grounding recovers ready/missing/tilt answers at \({\approx}0.97\) vs.\ Raw \({\lesssim}0.23\). The contribution is the interface, not a trading leaderboard.

**中文:** 公开大语言模型在决策之前需要一个可以安全观测的市场。我们为异步加密喂入贡献类型化观测契约——带硬拒绝标志的匿名状态编译器运行时。现场各臂使论点具体：Blind 拒绝，Raw 过度交易并亏损，Ungated 依赖厂商，Compiled 在生产门强制稀薄世界弃权 \(1.0\)；在反事实开放切片上，现场 Ungated 给出正 CE，同时次要内容规则确认倾斜非空。接地以约 \(0.97\) 对 Raw \(\lesssim 0.23\) 恢复就绪/缺失/倾斜答案。贡献是接口，而非交易排行榜。

---

## 10. 致谢 / 参考文献（稿内说明）

### 10.1 Acknowledgments
**EN:** Omitted for anonymous review.

**中文:** 匿名评审从略。

### 10.2 Bibliography
**EN:** Bibliography via `refs.bib` / ACM-Reference-Format (not translated here).

**中文:** 参考文献见 `refs.bib` / ACM-Reference-Format（此处不逐条翻译）。
