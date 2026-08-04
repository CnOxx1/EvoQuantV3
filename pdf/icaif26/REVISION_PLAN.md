# ICAIF '26 详细修改建议（世界模型理论）

> 目标会议：ACM ICAIF '26（Milan）  
> 硬约束：**双盲、ACM sigconf、全文 ≤8 页（含图+参考文献）、禁止附录/补充材料**  
> 截稿：**2026-08-09 23:59 AOE**（延后自 8/2）  
> 本目录与 `pdf/sci/`（JF/RFS）、`main_ai_wm.*` **隔离**；提交只用本文件夹产物。

---

## 0. 一句话理论锁定（投稿唯一主轴）

**金融世界模型运行时（Financial World-Model Runtime）**：把异步、多源、质量不一的原始市场证据，编译成可供 LLM / AI agent **分析、弃权、交易** 的世界状态；交易数字只用于证明「这个世界有内容」，不宣称策略圣杯。

对标 ICAIF 热点话术时，建议对齐：

| 通用 AI「世界模型」 | 本文金融版本 |
| --- | --- |
| 潜在状态 / 可预测世界 | 编译后信息集 \(\mathcal{F}^{\mathrm{AI}}_t\) |
| 观测编码器 | 认知观测 \(O_{j,t}=(x,\tau,q,g,r)\) + \(\Pi_t\) |
| 不确定性 / 拒绝预测 | WMI/ACWMI + world-conditional abstention |
| Agent 读状态做决策 | Compiled bundle → LLM / rule consumer |
| 仿真 rollout（可选后续） | 本稿先不做 Dreamer 式 dynamics；诚实写为 *state compiler*，不是完整 generative WM |

**重要：不要假装你们已经做了 Dreamer/JEPA 式视频世界模型。** ICAIF 审稿人懂这些词——用错会被打成「蹭热点」。正确姿势是：

> *We study the missing systems layer for financial AI agents: a point-in-time world-state compiler with explicit quality and abstention, complementary to generative world models that assume a clean observation stream.*

---

## 1. 与旧稿的切割（必须做）

| 旧稿（JF / 长稿） | ICAIF 新稿 |
| --- | --- |
| SDF / compilation wedge 主键 | **删或压成 2–3 句** related/discussion |
| 13-band / JF agenda | 一句 limitation |
| LOBO 长证明、附录、中文镜像 | **全部删除**（会议禁止 appendix） |
| Menu reality-check 长讨论 | 可一句带过 |
| 「asset pricing identification」话术 | 改为 **world-model content validation** |
| 作者信息、EvoQuant、GitHub | **匿名化** |
| 17+ 页 | **≤8 页** |

保留并升格：

1. \(O_{j,t}\)、\(\Pi_t\)、重构界（delay/noise/missing）  
2. WMI/ACWMI + 弃权  
3. 系统运行时（PIT、bundle、\(O_t\)、Compiled vs Raw）  
4. PIT content 验证（mechanism−momentum、LOBO content、长样本无隐藏 return alpha）

---

## 2. 建议题目（选一）

**推荐 A（系统+世界模型）**  
*Financial World-Model Runtime: Compiling Asynchronous Market Evidence for LLM Agents*

**推荐 B（更偏 agent）**  
*World Models for Market Agents: Point-in-Time Compilation, Quality, and Abstention*

**推荐 C（更偏 trustworthy AI）**  
*When Should a Market Agent Abstain? A World-Model Runtime with Quality-Gated Actions*

避免：带 “SDF”“JF”“certainty equivalent Holy Grail”“cryptocurrency alpha” 的标题。

---

## 3. 推荐 8 页结构（页预算）

| § | 节 | 预算 | 写什么 |
| --- | ---: | --- | --- |
| 1 | Introduction | 0.7 | 问题：LLM/agent 缺的是可审计 world state，不是又一个因子；贡献三点；thesis 一句 |
| 2 | Related Work | 0.8 | **World models (AI)** · LLM agents in finance · selective prediction · PIT/vintages · crypto microstructure（各 4–6 行） |
| 3 | Method: RCA-WM | 1.8 | 定义 + 2–3 个命题（无长证明）；一张「raw→compiled→consumer」架构图 |
| 4 | System | 1.0 | Pipeline、PIT clock、bundle schema、弃权接口；**匿名化**系统名 |
| 5 | Experiments | 2.5 | Setup → Content validation → Consumer protocol → Ablations（LOBO/costs） |
| 6 | Limitations | 0.4 | 稀疏 band、mock LLM、非完整 generative WM、成本脆弱 |
| 7 | Conclusion | 0.3 | 回收 thesis |
| — | References | ≤1.0 | **精选 25–35 篇**，否则超页 |

超页时优先砍：γ 网格表、jackknife 表、分年长样本细表、SDF、文献中的资产定价经典堆砌。

---

## 4. 理论修改清单（世界模型化）

### 4.1 必须新增/改写的「对齐段落」

在 Intro + Related 明确三角关系：

1. **Generative world models**（Ha & Schmidhuber; Hafner Dreamer; LeCun JEPA 等）——学习 dynamics / 可想象未来。  
2. **Financial ML / LLM agents**——通常假设输入已对齐。  
3. **本工作**——*observation-side world model / world-state compiler*：在 agent 读世界之前，先解决异步、缺失、vintage、诚实性。

建议定义（投稿可用）：

> **Definition (Financial world state).**  
> A financial world state at \(t\) is a quality-tagged, PIT-safe compilation \(W_t=\Pi_t(\mathcal{F}^{\mathrm{raw}}_t)\) together with a scalar world quality \(q(W_t)\) (e.g. WMI/ACWMI) that gates abstention.

### 4.2 命题保留优先级

| 优先级 | 对象 | ICAIF 处理 |
| --- | --- | --- |
| P0 | Compilation ≠ feature expansion | 保留短命题 |
| P0 | World-conditional abstention | 保留；连到 trustworthy AI |
| P0 | LOBO = content + gating | 保留定义 + 1 个实证表 |
| P1 | Reconstruction bound | 公式 1 行 + 直觉 |
| P2 | SDF / wedge | **移出主贡献**；最多 related 一句 |
| P2 | ACWMI 凹性/单调长证明 | 删证明，留公式 |

### 4.3 与「世界模型很火」的正确挂钩（防审稿攻击）

审稿人可能说：*这不是 world model，只是 ETL。*  
预埋回应：

- 世界模型的最小要件是：**面向决策的状态表示 + 质量/不确定性 + 可被 agent 消费**。  
- 我们显式提供 \(W_t\)、\(q(W_t)\)、弃权、以及 Compiled vs Raw 对照——这是 agent 世界接口，不是 silent feature store。  
- 我们 **不** 声称已学习 \(p(s_{t+1}\mid s_t,a_t)\)；那是下一步 *dynamics world model*。本稿贡献是 **state compiler + abstention runtime**。

---

## 5. 系统节修改清单

1. **匿名**：用 “our runtime / the prototype” ，不要写 EvoQuant、具体域名、可识别 API 路径。可用通用名：`BandPIT`, `WMI`（若首次提出需定义）。  
2. **一张架构图（必上）**：Collectors → Vintage store → \(\Pi_t\) / readiness → World bundle → LLM/Rule consumer → action/abstain。  
3. **Bundle schema 小表**（半栏）：字段 = bands, ages, WMI/ACWMI, tilts, \(O_t\), evidence ids。  
4. **PIT previous-close clock** 用 3–4 行写清（防 look-ahead）。  
5. 删：迁移 fallback 长故事、交易所可达性、生产 vs paper ACWMI 长 disclosure（缩成一句）。

---

## 6. 实验修改清单（适配 8 页 + ICAIF 口味）

### 6.1 主实验顺序（审稿人友好）

1. **Setup**：PIT 399 天、10 assets、durable bands、prev-close、IS/OOS。  
2. **RQ1 Content：** mechanism − momentum \(\Delta\)CE（预指定）+ bootstrap \(p\)。  
3. **RQ2 Ablation：** LOBO content vs gating（说明 ungated 下 content share=1 的含义，防同义反复攻击）。  
4. **RQ3 Interface：** Compiled vs Raw consumer（哪怕 mock）——**ICAIF 比 CE 小数更吃这一套**。  
5. **RQ4 Trust：** abstention / ECP / EAR（短）。  
6. **RQ5 Stress：** costs 10/25 bps 相对 gap；长样本「无 content ⇒ 无隐藏 alpha」一句。

### 6.2 表/图配额（建议 ≤5 可视元素）

| ID | 内容 | 去留 |
| --- | --- | --- |
| Fig.1 | 架构图 | **必留** |
| Tab.1 | OOS policies（mech / mom / ACWMI） | 必留 |
| Tab.2 | Bootstrap headline + LOBO | 合并为一表更佳 |
| Fig.2 | 成本敏感性 或 LOBO 条形 | 二选一 |
| Tab.3 | Compiled−Raw consumer | **必留（哪怕 mock）** |

砍掉：γ×cost 全表、asset jackknife 全表、分年明细、条件 IC 长表、cascade 校准。

### 6.3 Claim 语言（投稿安全）

**要写：**
- compiled world has economically nonempty content  
- content channel dominates gating under our rule  
- relative CE gap vs same-input momentum  

**不要写：**
- beats market / unconditional alpha  
- LLM trading alpha  
- full generative world model  
- JF-level identification of SDF wedge  

---

## 7. Related Work 必引方向（世界模型向）

至少覆盖（具体条目见 `refs.bib`，投稿前核对年份页码）：

1. **AI world models / model-based RL**：Ha & Schmidhuber；Dreamer (Hafner et al.)；可选 LeCun JEPA position。  
2. **LLM agents / tool use in finance**：选 2–3 篇 ICAIF/ACL/NeurIPS workshop 近期工作。  
3. **Selective prediction**：El-Yaniv & Wiener；Geifman & El-Yaniv。  
4. **PIT / real-time macro**：Croushore & Stark。  
5. **Crypto microstructure / factors**：Makarov & Schoar；Liu–Tsyvinski–Wu。  
6. **Trustworthy / abstention in decisions**：与 finance risk 连接的 1 篇即可。

资产定价经典（Cochrane, Fama–French）**各留 0–1 篇**，勿再占半页。

---

## 8. 匿名与合规（易 desk-reject）

- [x] `anonymous` 选项（CFP：仅 `sigconf,anonymous`，无 `review` 行号）；页眉无姓名；短标题单行 running head  
- [ ] 删邮箱、Independent Researcher、仓库链接  
- [ ] 代码/数据：写 “anonymized repository / will be released”  
- [ ] 自引第三人称  
- [ ] **不要**在正文引用本工作 arXiv（CFP：为保匿名勿引此类）  
- [ ] 作者列表在 CMT 一次填对（提交后不可改）  
- [ ] 每人 ≤6 篇投稿  
- [ ] 审稿期间勿投其他 archival venue  
- [ ] 录用需 **现场报告**（in-person）

---

## 9. 截稿前执行顺序（按优先级）

因距 **8/9 AOE** 很紧，建议只做可完稿路径：

### P0（必须，否则不要投）
1. 在本目录完成 **匿名 8 页** PDF（`main.tex` → Overleaf ACM 或 `generate_icaif26_pdf.py`）。  
2. 架构图 + 3 张主表塞进正文且不超页。  
3. Abstract/Intro/Conclusion 全部使用世界模型运行时 thesis。  
4. 删除 SDF 主键叙事与全部附录。  
5. CMT 双盲上传。

### P1（强烈建议，若还有 1–2 天）
1. 跑通/整理 **Compiled vs Raw** 表到正文（mock 可，但要写清）。  
2. Related 补齐 world-model 文献。  
3. Limitations 诚实写：非 generative dynamics WM；稀疏 band；绝对 CE 成本脆弱。

### P2（来不及就放弃）
1. Live LLM API 实验。  
2. 多年 vintaged alt PIT。  
3. Gated-policy LOBO 重跑。  
4. 新图美化。

---

## 10. 审稿人预答辩（投稿版）

| 攻击 | 短答 |
| --- | --- |
| Not a world model | We propose an observation-side WM runtime (state compiler + quality + abstention), complementary to generative dynamics WMs. |
| Just feature engineering | PIT clock, \(O_{j,t}\), quality indices, abstention policy, and Compiled−Raw interface are first-class; silent ETL lacks these. |
| Mock LLM useless | Protocol is the contribution; mocks keep estimand fixed for live vendors. |
| Results are trading alpha paper | Relative content validation only; absolute CE cost-fragile; no Holy Grail claim. |
| Only 3 bands / short panel | Stated limitation; durable-band identification by design. |
| LOBO tautology | Under ungated rule, content deletion collapses to momentum by construction; that *is* the content channel; gating deferred to denser archives. |

---

## 11. 本目录已提供的草稿

| 文件 | 用途 |
| --- | --- |
| `main.tex` | 8 页向匿名草稿（可用 Overleaf + acmart） |
| `refs.bib` | 精简参考文献 |
| `generate_icaif26_pdf.py` / `main_icaif26.pdf` | 无 TeX 时的可读提交形 PDF |
| `REVISION_PLAN.md` | 本文件 |

长篇理论与完整实证仍在 `pdf/sci/`；**不要**把 JF 长稿直接改后缀投稿 ICAIF。
