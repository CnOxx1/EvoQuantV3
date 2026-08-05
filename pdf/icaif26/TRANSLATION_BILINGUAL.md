# ICAIF ’26 论文逐句中英对照与分析

> 源稿：`main.tex` / `main.pdf`（当前投稿稿，约 7 页）  
> 用途：内部精读；**正式投稿仍以英文 PDF 为准**。  
> 体例：每条为 **EN → 中文 → 分析**（术语、论证功能、易误读点）。

---

## 0. 关键术语表（全文统一译法）

| English | 中文（本稿采用） | 说明 |
|---|---|---|
| world-model runtime | 世界模型运行时 | 不是 Dreamer 式生成 WM，而是状态编译器 |
| observation interface / contract | 观测接口 / 观测契约 | 论文主 claim |
| typed abstention / refuse contract | 类型化弃权 / 拒绝契约 | 布尔门控，非软置信度 |
| point-in-time (PIT) | 时点安全 / PIT | 防前视 |
| thin world / scarce support | 稀薄世界 / 稀薄支撑 | WMI 低于阈值 |
| band-thick | 波段齐全（档案厚） | 3/3 ready，≠ WMI 可行动 |
| Compiled / Ungated / Raw / Blind | 编译契约 / 无门控 / 原始碎片 / 盲问 | 四臂专名，正文可保留英文 |
| grounding workflow | 接地工作流 | 非交易认知核验 |
| certainty equivalent (CE) | 确定性等价 | 风险调整收益代理 |
| vintage / available_at | vintage / 可用时戳 | 宏观发布滞后 |
| should_ai_abstain | （保留英文字段）应弃权标志 | 机器可读 |
| evidence IDs / EAR | 证据 ID / 证据锚定要求 | 可审计 |
| OOS | 样本外 | out-of-sample |

---

## 1. 标题

**EN:** A Market World Model for Public LLMs: A Typed Observation Contract before Decision  

**中文:** 面向公开大语言模型的市场世界模型：决策之前的类型化观测契约  

**分析:**  
- “before Decision” 强调**观测先于决策**，不是交易策略论文。  
- “Typed” = 有类型/字段约束的契约（布尔弃权），不宜译成“打字的”。  
- 短标题 running head 只用前半句，符合 ACM 页眉单行要求。

---

## 2. 摘要（逐句）

### 2.1
**EN:** Public LLMs asked to analyze or trade crypto markets often fail before strategy: they lack a complete, honest, auditable *market observation interface*.  

**中文:** 被要求分析或交易加密市场的公开大语言模型，往往在策略之前就失败：它们缺少一个完整、诚实、可审计的*市场观测接口*。  

**分析:** 开篇定调失败点在**接口**不在 alpha；三形容词 complete/honest/auditable 是全文母题。

### 2.2
**EN:** We present an anonymized *world-model runtime* that compiles asynchronous multi-band evidence into a point-in-time (PIT) world bundle with a typed abstention contract.  

**中文:** 我们提出一个匿名化的*世界模型运行时*，将异步多波段证据编译为带类型化弃权契约的时点安全（PIT）世界状态包（world bundle）。  

**分析:** “compiles”≠训练生成模型；“anonymized”服务双盲，非算法匿名。

### 2.3
**EN:** Epistemic observations \(O_{j,t}=(x,\tau,q,g,r)\) and compilation \(\Pi_t\) yield \(\mathcal{F}^{\mathrm{AI}}_t\); completeness, honesty \((B,U,H)\), and WMI/ACWMI expose machine-readable refusal; evidence IDs bind actions to disclosed fields.  

**中文:** 认识论观测 \(O_{j,t}=(x,\tau,q,g,r)\) 与编译算子 \(\Pi_t\) 生成 \(\mathcal{F}^{\mathrm{AI}}_t\)；完整性、诚实性 \((B,U,H)\) 与 WMI/ACWMI 暴露机器可读的拒绝；证据 ID 将行动绑定到已披露字段。  

**分析:** 一句塞进形式语义；审稿人扫摘要时看到“有理论对象”。`g`=main-view gate，`r`=semantic role。

### 2.4
**EN:** The main claim is interface reliability under thin support, not a new trading agent.  

**中文:** 主主张是稀薄支撑下的接口可靠性，而不是一个新的交易智能体。  

**分析:** 主动降级交易叙事，降低“没赚钱”攻击面。

### 2.5
**EN:** On identical OOS asset-days, four live public LLMs (temperature \(0\)) rank as Blind refuses, Raw over-trades and loses, Ungated abstains only partially (\({\approx}0.68\)), and Compiled with a hard flag abstains on every thin day (\(1.0\)); a full-OOS sweep and a band-thick split reproduce the same ranking.  

**中文:** 在相同的样本外资产日上，四个现场公开 LLM（温度 \(0\)）排序为：盲问拒绝；原始碎片过度交易并亏损；无门控仅部分弃权（约 \(0.68\)）；带硬标志的编译契约在每个稀薄日弃权（\(1.0\)）；全样本外扫描与波段齐全切分复现同一排序。  

**分析:** 摘要里的“硬结果梯子”；数字刻意压缩（相对旧版）。

### 2.6
**EN:** The panel never exceeds the production WMI refuse threshold (\(\max\mathrm{WMI}\approx 0.093{<}0.2\)), so Compiled's full refusal is the scarce-support stress test; a lower counterfactual threshold would open the band-thick slice where content remains nonempty.  

**中文:** 该面板从未超过生产环境 WMI 拒绝阈值（\(\max\mathrm{WMI}\approx 0.093{<}0.2\)），故编译臂的全拒绝是稀薄支撑压力测试；更低的反事实阈值将打开放段齐全切片，且该切片上内容非空。  

**分析:** 预判“契约从不打开”质疑；open 日硬数字在正文展开。

### 2.7
**EN:** A grounding workflow recovers ready/missing/tilt answers at mean F1/acc.\ \({\approx}0.97\) from Compiled vs.\ \({\lesssim}0.23\) from Raw.  

**中文:** 接地工作流从编译包恢复就绪/缺失/倾斜答案，均值 F1/准确率约 \(0.97\)，而原始臂 \(\lesssim 0.23\)。  

**分析:** RQ2 摘要句；非交易但很硬。

### 2.8
**EN:** As a secondary content check, a transparent no-LLM rule on the same vintaged tilts beats momentum and buy-and-hold out-of-sample (\(\Delta\mathrm{CE}{=}0.334\), \(p{=}0.034\)).  

**中文:** 作为次要内容检验，一条透明的无 LLM 规则在相同 vintage 倾斜上样本外击败动量与买入持有（\(\Delta\mathrm{CE}{=}0.334\)，\(p{=}0.034\)）。  

**分析:** RQ3 明确 secondary；只留一个显著性数字。

### 2.9
**EN:** We detail the runtime (collectors, vintage store, BandPIT, bundle schema, LLM adapter) as an ICAIF systems contribution.  

**中文:** 我们将运行时（采集器、vintage 存储、BandPIT、bundle schema、LLM 适配器）作为 ICAIF 系统贡献加以详述。  

**分析:** 对接 venue 的 systems 口味。

---

## 3. CCS / 关键词

**EN CCS:** Artificial intelligence (500); Machine learning (300); Economics (300)  

**中文:** 人工智能；机器学习；应用计算～经济学  

**EN keywords:** world models, public LLMs, AI agents, cryptocurrency, point-in-time, abstention, trustworthy AI, observation contract, systems  

**中文关键词:** 世界模型、公开 LLM、AI 智能体、加密货币、时点安全、弃权、可信 AI、观测契约、系统  

**分析:** `systems` 关键词帮助分到系统/应用轨。

---

## 4. 第 1 节 引言

### 4.1 开篇段
**EN:** Public LLMs are increasingly asked to analyze or trade crypto markets. The bottleneck is not another alpha signal. It is *understanding*: before decision, an agent needs a market world that is **complete** (missingness disclosed), **honest** (stale or role-incoherent evidence gated), and **auditable** (actions bound to evidence).  

**中文:** 公开大语言模型越来越多地被要求分析或交易加密市场。瓶颈不是又一个 alpha 信号，而是*理解*：决策之前，智能体需要一个**完整**（缺失被披露）、**诚实**（过期或角色不一致的证据被门控）、**可审计**（行动绑定到证据）的市场世界。  

**分析:** “understanding” 是口号词但已收敛为三性质定义，避免空泛。

**EN:** Venue fragmentation, derivatives, on-chain flows, news, and macro vintages arrive on incompatible clocks. Generative world models and tool-using finance agents typically assume a usable observation stream. Crypto agents often do not have one.  

**中文:** 场所碎片化、衍生品、链上资金流、新闻与宏观 vintage 以不兼容的时钟到达。生成式世界模型与工具型金融智能体通常假定存在可用观测流；加密智能体往往并没有。  

**分析:** 把 gap 钉在“观测流缺失”，与后文 ICAIF agent 论文区分。

### 4.2 Thesis
**EN:** We build a market *world-model runtime* for public LLMs: compile raw multi-band evidence into a PIT-safe bundle that GPT / DeepSeek / GLM / Gemini-class models can call under a typed refuse contract. The goal is reliable observation under sparse and asynchronous feeds, not a new portfolio policy. Strategy metrics appear only as a secondary check that the compiled fields are nonempty.  

**中文:** 我们为公开 LLM 构建市场*世界模型运行时*：将原始多波段证据编译为 PIT 安全包，供 GPT / DeepSeek / GLM / Gemini 一类模型在类型化拒绝契约下调用。目标是在稀疏与异步喂入下可靠观测，而非新的组合策略。策略指标仅作次要检验，用于说明编译字段非空。  

**分析:** 旧版 slogan “quant from strategy…” 已删，语气更论文。

### 4.3 What we claim
**EN:** RQ1 tests whether a typed world interface can *enforce* world-conditional abstention across live public LLMs (a runtime contract, not spontaneous thinness discovery from raw ticks). RQ2 tests whether the compiled world makes analyst-facing epistemic answers verifiable. RQ3 asks whether a transparent rule on the same vintaged tilts beats momentum and buy-and-hold---a content check, not an LLM trading leaderboard.  

**中文:** RQ1 检验类型化世界接口能否在现场公开 LLM 上*强制*世界条件弃权（运行时契约，而非从原始 tick 自发发现稀薄性）。RQ2 检验编译世界是否使面向分析师的认识论答案可核验。RQ3 询问：同一 vintage 倾斜上的透明规则能否击败动量与买入持有——这是内容检验，不是 LLM 交易排行榜。  

**分析:** 三个 RQ 边界清晰；括号内主动排除误读。

### 4.4 Contributions（三条）
**EN 1:** Cognition semantics. Epistemic observations, compilation \(\Pi_t\), a lag reconstruction bound, completeness/honesty fields, WMI/ACWMI abstention, evidence-bound actions.  

**中文 1:** 认知语义。认识论观测、编译 \(\Pi_t\)、滞后重构界、完整性/诚实性字段、WMI/ACWMI 弃权、证据绑定行动。  

**EN 2:** Anonymized runtime architecture. Vintage-aware collectors, BandPIT previous-close clock, quality-tagged bundles, availability shocks \(O_t\), a multi-vendor OpenAI-compatible adapter, and a frozen Compiled / Ungated / Raw / Blind consumer protocol.  

**中文 2:** 匿名化运行时架构。感知 vintage 的采集器、BandPIT 前收盘时钟、质量标注包、可用性冲击 \(O_t\)、多厂商 OpenAI 兼容适配器，以及冻结的四臂消费协议。  

**EN 3:** Live interface validation. … Blind refuses, Raw over-trades… Compiled… 1.0 … grounding 0.97 … no-LLM content rule … nonempty.  

**中文 3:** 现场接口验证。…盲问拒绝、原始过度交易…编译强制 1.0…接地 0.97…无 LLM 内容规则确认倾斜经济非空。  

**分析:** C3 把实证摘要压进一条，便于扫读。

---

## 5. 第 2 节 相关工作

### 5.1 World models in AI
**EN:** World models learn compact states and often dynamics. We address the complementary *observation-side* problem: a PIT-safe, quality-tagged crypto world *before* dynamics or LLM policy. We claim the missing systems layer generative WMs usually assume---not a Dreamer/JEPA simulator.  

**中文:** 世界模型学习紧凑状态并常学习动力学。我们处理互补的*观测侧*问题：在动力学或 LLM 策略之前，先有一个 PIT 安全、质量标注的加密世界。我们主张的是生成式 WM 通常假定却缺失的系统层——不是 Dreamer/JEPA 模拟器。  

**分析:** 与 Ha/Dreamer/LeCun 划界；“observation-side” 是关键词。

### 5.2 LLM agents in finance
**EN:** … Recent ICAIF work targets adjacent layers: FinAgentBench… FinSearch… FinResearchBench… FactorMAD…. Those systems improve how agents fetch, debate, and are scored, but still assume a usable observation stream. We study the missing prior step---a PIT-safe, quality-tagged *observation contract* with typed abstention---and evaluate within-model Compiled / Ungated / Raw / Blind under a frozen schema rather than proposing another memory router, retrieval planner, or debate society.  

**中文:** …近期 ICAIF 工作瞄准相邻层：FinAgentBench（检索评测）、FinSearch（时序搜索智能体）、FinResearchBench（长程研究评判）、FactorMAD（多智能体辩论挖因子）。这些系统改进智能体如何抓取、辩论与被打分，但仍假定存在可用观测流。我们研究缺失的前置步骤——带类型化弃权的 PIT 安全、质量标注*观测契约*——并在冻结 schema 下做同模型四臂评估，而非再提一个记忆路由/检索规划/辩论社团。  

**分析:** 与 ’25 录用线对齐又区分；“prior step” 定位。

### 5.3 Selective prediction
**EN:** Abstention can be optimal under noise. We tie refusal to world quality via an explicit runtime contract, not classifier confidence alone.  

**中文:** 噪声下弃权可以是最优的。我们通过显式运行时契约把拒绝绑定到世界质量，而非仅靠分类器置信度。  

### 5.4 PIT / microstructure
**EN:** Macro vintages and crypto microstructure motivate multi-band compilation. … Asset-pricing ML is adjacent: we validate the economic content of a compiled world for agents, not priced factors.  

**中文:** 宏观 vintage 与加密微观结构动机多波段编译。……资产定价 ML 相邻：我们验证面向智能体的编译世界之经济内容，而非定价因子。  

---

## 6. 第 3 节 语义（定义/命题）

### Definition 3.1 Epistemic observation
**EN:** \(O_{j,t}=(x,\tau,q,g,r)\): value, latest-available time, quality, main-view gate, semantic role. A bare feature dump that omits \((\tau,q,g,r)\) is not a world observation.  

**中文:** 认识论观测五元组：取值、最新可用时间、质量、主视图门控、语义角色。省略 \((\tau,q,g,r)\) 的裸特征倾倒不是世界观测。  

**分析:** 用否定句立边界——Raw/mom5 在定义上就不是完整观测。

### Definition 3.2 Financial world state
**EN:** \(W_t=\Pi_t(\mathcal{F}^{\mathrm{raw}}_t)\) with scalar quality \(q(W_t)\) gating abstention; \(\mathcal{F}^{\mathrm{AI}}_t=\sigma(W_t)\).  

**中文:** 金融世界状态由编译得到，标量质量门控弃权；AI 可用信息集是世界状态的可测映射。  

### Definition 3.3 Compilation
**EN:** \(\Pi_t=B_t\circ M_t\circ A_t\): align clocks, apply honesty/missingness gates, assemble band views.  

**中文:** 编译 = 对齐时钟 ∘ 诚实/缺失门控 ∘ 组装波段视图。  

### Completeness / honesty / quality 段
**EN:** Ready/limited/missing counts disclose coverage. \(\mathrm{WMI}_t=B_t U_t H_t\); ACWMI supports regime-conditional gating. The Compiled contract exposes `should_ai_abstain` and `thin_world` as first-class fields.  

**中文:** 就绪/受限/缺失计数披露覆盖。WMI 为广度×稳定×诚实之积；ACWMI 支持状态条件门控。编译契约把弃权标志与稀薄世界标志作为一等字段暴露。  

### Assumption / Prop. lag bound
**EN:** Compilation cannot erase delay; it can refuse to pretend the bound is zero.  

**中文:** 编译不能抹掉延迟；它可以拒绝假装界为零。  

**分析:** 一句点题——弃权的理论正当性。

### Prop. compilation ≠ feature dump
**EN:** Enlarging raw span without \(\Pi_t\) need not enlarge usable \(\mathcal{F}^{\mathrm{AI}}\): ungated stale evidence can raise volume while lowering honesty/stability.  

**中文:** 没有 \(\Pi_t\) 时扩大原始跨度未必扩大可用 AI 信息集：未门控的过期证据可能抬高体量却降低诚实/稳定。  

### Prop. world-conditional abstention
**EN:** If non-abstain actions exceed a world-dependent cost \(c_{\mathrm{abs}}(W_t)\), the Bayes action is abstain; with costs decreasing in WMI, abstention forms a lower set in world quality.  

**中文:** 若非弃权行动的代价超过世界依赖的弃权成本，贝叶斯行动为弃权；当成本随 WMI 下降时，弃权构成世界质量上的下集。  

### Prop. LOBO
**EN:** Deleting band \(j\) changes value through a content channel and a gating channel. Empirically we report content share under an ungated rule so the probe speaks to nonempty fields.  

**中文:** 删除波段 \(j\) 经内容通道与门控通道改变价值。经验上我们在无门控规则下报告内容份额，使探针指向字段非空。  

### Remark
**EN:** We do not learn \(p(s_{t+1}\mid s_t,a_t)\). We deliver a *state compiler + abstention runtime*.  

**中文:** 我们不学习动力学转移。我们交付的是*状态编译器 + 弃权运行时*。  

---

## 7. 第 4 节 运行时架构

### 开场
**EN:** We describe the anonymized prototype as a layered system …. Source paths and product names are omitted for double-blind review; an anonymized artifact will be released upon acceptance.  

**中文:** 我们将匿名原型描述为分层系统……源路径与产品名因双盲省略；录用后发布匿名化制品。  

### 五层（简译）
1. **Data:** 交易所/宏观/另类采集器写入带 vintage 的历史。  
2. **Store:** 嵌入式分析库保存原始、合并面板与流水线输出。  
3. **Logic:** BandPIT 前收盘时钟；门控实现 \(\Pi_t\)；\(O_t\) 一等。  
4. **Service:** 只读 API 提供质量标注包，无需为新行重启采集。  
5. **Consumer:** 冻结提示的 LLM/规则，经 OpenAI 兼容适配器，温度 0。  

### 数据流段（压缩译）
**输入**三波段公共档案；**处理** BandPIT 取 \(\le(t-1)23{:}59\) 最新观测并分级；**输出**约 3990 行 PIT 面板与每日 bundle。  

### PIT previous-close
**EN:** For calendar day \(t\), the decision information set is reconstructed at \((t{-}1)\,23{:}59\). The payoff is the same-calendar-day close-to-close return \(r_t\).  

**中文:** 日历日 \(t\) 的决策信息集在前一日 23:59 重构；收益用同日收盘到收盘收益 \(r_t\)。  

**分析:** 经典 PIT：信息截止与收益日对齐，去同日前视。

### World bundle / 四臂
| Arm | 中文要点 |
|---|---|
| Compiled | 全包 + 硬 `should_ai_abstain` 必须弃权 |
| Ungated | 同内容、无硬标志，软判断 |
| Raw | 仅 mom5；常见生产接线，非故意弱基线 |
| Blind | 无数据直接问如何交易 |

**EN:** … \(\max\mathrm{WMI}\approx 0.093\), so every day is thin and Compiled never opens---a refuse-under-sparse stress test, not a claim the contract never allows action.  

**中文:** …最大 WMI≈0.093，故每日皆稀薄、编译从不打开——这是稀薄下拒绝压力测试，并非声称契约永不放行。  

### Why hard refusal is not a confound
**EN:** Compiled abstention is partly prompt obedience, and that is intentional…. The headline result is that the hard contract is reliable across vendors; soft refusal is not.  

**中文:** 编译弃权部分是提示服从，且这是有意的……头条结果是：硬契约跨厂商可靠，软拒绝不然。  

**分析:** 主动承认“服从提示”，用 Ungated 对照把批评变成设计点。

---

## 8. 第 5 节 实验

### Setup
**中文要点:** PIT≈399 天×10 资产；IS/OOS 各 200 天；RQ1 同 100 日分层样本；温度 0；全 OOS 检查点扫描；稀薄标签按设计绑定。

### RQ1 主结果段
**EN:** Under Compiled… thin-abs. 1.0 … prompt-contract obedience by design, not spontaneous thinness discovery. Under Ungated… 0.68…. Unconditional Ungated CE … −1.04 to +0.02; … act-conditional CE (mean ≈−1.9)…. Mean ΔCE (Compiled−Raw)=+1.07….  

**中文:** 编译下稀薄弃权 1.0……属提示契约服从，非自发发现稀薄。无门控均值 0.68……无条件 CE 在 −1.04 到 +0.02；行动日条件 CE 均值约 −1.9……编译相对原始的 ΔCE 均值 +1.07。  

**分析:** 区分 unconditional / act-conditional CE，堵住数字打架。

### Full-OOS / Blind / Band-thick / Ungated inside / Offline
（要点译）  
- 全 OOS：Compiled 仍 1.000；Ungated 均值约 0.56。  
- 盲问：100% 弃权；危险的是中间态 Raw。  
- 波段齐全日：档案“看起来完整”仍需契约；Raw 仍乱交易。  
- Ungated：会读字段，但行动因厂商而异。  
- 离线：协议检查，主 claim 仍是 live。

### When would the contract open?（关键硬数字）
**EN:** … \(\mathrm{WMI}\ge 0.05\) marks \(n{=}1224\) (61%)…. content rule acts on 92% … CE +0.061 vs −0.254; ΔCE=0.315….  

**中文:** 反事实开放规则 WMI≥0.05 标记 n=1224（61%）天……内容规则在这些天上 92% 会交易……CE +0.061 vs −0.254，ΔCE=0.315。  

**分析:** 直接回答“契约何时放行”；经济数字来自无 LLM 规则，威胁段会再声明。

### RQ2 Grounding
**中文要点:** 50 日多步：列就绪/缺失、报倾斜符号、判充分性；编译均值 F1/acc≈0.97，原始坍塌到 0.04–0.23；充分性单独不可靠，主张是可核验认识论。

### RQ3 Content probe
**中文要点:** 无 LLM 透明规则；Sharpe 0.764 / CE +0.130 vs 动量与 B&H；ΔCE=0.334，p=0.034；十资产全正；LOBO 归内容；非 vintage 审计无边。Open/thick 切片 ΔCE=0.315。

### Discussion / Design / Threats / Scope
**Threats（重要）中文要点:**  
- 编译弃权=提示服从（产品接口），非自发发现；Ungated 去布尔对照。  
- 档案稀薄，live 编译在 0.2 阈值下从不打开；open 日经济用无 LLM 规则。  
- flash/mini、温度 0；GLM Raw 未完；缺 news/on-chain/options。  
- 三厂商行动日 CE 为负，说明只披露不强制不稳定。  

---

## 9. 结论

**EN:** We contribute a typed observation contract and anonymized runtime for public LLMs under asynchronous crypto feeds. Live arms show Blind refuses, Raw over-trades and loses, Ungated is vendor-dependent, and Compiled enforces thin-world abstain 1.0 even on band-thick days; grounding recovers … ≈0.97 vs Raw ≲0.23. A secondary no-LLM content rule shows the tilts are economically nonempty versus momentum and buy-and-hold.  

**中文:** 我们贡献异步加密喂入下面向公开 LLM 的类型化观测契约与匿名运行时。现场四臂显示：盲问拒绝、原始过度交易并亏损、无门控依赖厂商、编译即使在波段齐全日仍强制稀薄弃权 1.0；接地恢复约 0.97 对原始 ≲0.23。次要无 LLM 内容规则表明倾斜相对动量与买入持有经济非空。  

**分析:** 结论不再用口号收尾，只复述事实梯子——此前润色的重点。

---

## 10. 图表标题速译

| 标签 | 英文 caption（要义） | 中文 |
|---|---|---|
| Tab modules | Anonymized module map | 匿名模块图 |
| Fig pipeline | Anonymized runtime architecture… | 匿名运行时架构 |
| Tab dataflow | Data flow through the runtime | 运行时数据流 |
| Tab schema | World bundle field groups | 世界包字段组 |
| Fig ready | PIT readiness… grayscale styles | PIT 就绪度（灰打线型） |
| Tab llm | Live abstention rates… | 现场弃权率 |
| Fig und | Four-arm abstention rates | 四臂弃权率 |
| Tab mix | Raw-arm action mix | 原始臂行动混合 |
| Tab thick | Band-thick split… | 波段齐全切分 |
| Tab grounding | Grounding workflow… | 接地工作流 |
| Tab econ | Content probe vs baselines | 内容探针 vs 基线 |
| Tab dense | Open/dense split… | 开放/稠密切分 |
| Fig econ | Equity curves + per-asset ΔCE | 权益曲线与分资产 ΔCE |

---

## 11. 阅读建议（分析总览）

1. **主线一句话:** 先给公开 LLM 一个完整/诚实/可审计的市场观测契约，再谈决策。  
2. **不要误读为:** LLM 交易 SOTA、Dreamer 世界模型、或“Compiled 从不交易所以没用”——正文用阈值与 open 日 ΔCE=0.315 回应。  
3. **证据金字塔:** RQ1 接口梯子（主）→ RQ2 接地（硬）→ RQ3 内容非空（次）。  
4. **译稿注意:** 专名 Compiled/Ungated/Raw/Blind、字段名、WMI/ACWMI 建议保留英文；“typed”勿译“打字”。

---

*本文件随 `main.tex` 更新；若正文再改，请同步修订对应句子。*
