# LLM Consumer Validation Protocol (pre-registered)

**Status:** Pre-registered companion design for the JF/RFS working paper.  
**Role:** Secondary AI-consumer validation — **not** the primary identification strategy.  
**Primary identification remains:** transparent R1–R3 rule, Mechanism − Momentum, and LOBO content/gating decomposition on the real PIT archive.

## Scientific claim under test

Compilation quality improves decision quality for AI agents that condition on the market information set:

\[
\Delta_m = V_m(\text{Compiled}) - V_m(\text{Raw})
\]

for each model \(m\), where \(V\) is OOS CRRA certainty equivalent (\(\gamma=2\)) of a mapped action in \(\{+1,0,-1,\text{abstain}\}\).

We report within-model treatment effects and the cross-model mean \(\bar\Delta = K^{-1}\sum_m \Delta_m\). We do **not** claim that any LLM has unconditional trading alpha.

## Treatments (within model)

| Arm | Information set |
| --- | --- |
| **Compiled** | PIT-safe epistemic bundle: band statuses, WMI/ACWMI, honesty/stability, macro_tilt, alt_tilt, regime, cascade_p, quality flags, abstention guidance when index is low |
| **Raw** | Thin/ungated view: recent returns / momentum only; no world-model index; no band roles; no abstention guidance |

Same calendar dates, same assets, same action schema, same decoding settings.

## Frozen decoding

- `temperature = 0.0`
- Deterministic parsing of JSON action schema
- No web tools / no retrieval beyond the supplied bundle
- Prompts frozen under `prompts/frozen/` before OOS evaluation
- IS used only to validate parser robustness, never to rewrite prompts after seeing OOS PnL

## Action space

```json
{"action": "bullish|bearish|neutral|abstain", "confidence": 0.0-1.0, "rationale": "short"}
```

Mapping to positions: bullish→+1, bearish→−1, neutral→0, abstain→0 (cash).  
Abstention is economically distinct in reporting (abstain rate, ECP-style overconfidence when WMI low).

## Models

Configured in `pdf/sci/experiment_config.json` → `llm_consumer.models`.  
Default offline suite uses deterministic mock providers so CI/replication does not require API keys. Live vendors may be swapped in via provider adapters without changing the protocol.

## Inference

- Chronological IS/OOS split identical to the paper panel
- Block-bootstrap \(\Delta\)CE within model (block length from experiment config)
- Multiple-testing: report mean \(\bar\Delta\) with reality-check style menu correction across models
- Transcripts stored under `transcripts/` with prompt hash + response + parsed action

## What would falsify the consumer claim

1. \(\bar\Delta \le 0\) with CI covering zero after costs  
2. Compiled arm abstains less while WMI is low (calibration failure)  
3. Gains appear only for one proprietary model and reverse under mocks / alternate vendors
