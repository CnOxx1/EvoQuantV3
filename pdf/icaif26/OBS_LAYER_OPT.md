# Observation-layer narrative optimization (ICAIF ’26)

## Core thesis (locked)

> 给公共 LLM 一套加密市场观测层：把异步证据编成可消费的世界包；质量不够时强制弃权，避免半吊子上下文害决策。

English product sentence used in the paper:

> Give public LLMs a crypto market observation layer: compile asynchronous evidence into a consumable world bundle; force abstention when quality is insufficient so half-baked context cannot harm decisions.

## Diagnosis (pre-edit)

| Thesis clause | Was present? | Problem |
| --- | --- | --- |
| Observation layer for public LLMs | Yes (interface/contract) | Title/hero sold **typed refusal**, not the layer |
| Compile async evidence → world bundle | Yes (system §) | Buried under abstain ladder in abstract Evidence |
| Force abstain when quality thin | Yes (RQ1 primary) | Correct as **safety valve**, wrong as **brand** |
| Avoid half-baked context harming decisions | Yes (Raw/Ungated CE) | Framed as refusal paper, not observation quality |

Empirics stay: scarce panel, Compiled thin-abs 1.0, Ungated lower bound (not Compiled-open), RQ2 grounding, RQ3 no-LLM.

## Edit policy

1. **Hero = observation layer + world bundle**; refusal = quality gate of that layer.
2. **Do not invent Compiled-open trading** or claim bootstrap significance where CIs include 0.
3. **RQ numbering unchanged** (RQ1 refuse / RQ2 grounding / RQ3 content) to avoid cross-ref churn; **intro framing** presents seeing (RQ2) and gating (RQ1) as two faces of one layer.
4. Keep ≤8 pages; prefer sentence swaps over new figures.

## Title chosen

*A Crypto Observation Layer for Public LLMs: Compiling World Bundles with Quality-Gated Refusal*
