# LLM Consumer Protocol — Market World Model for Public LLMs

**Thesis:** Most quant stacks start from *strategy*. This runtime starts from *understanding*: before a public LLM (GPT / DeepSeek / GLM class) decides, it needs a complete, honest, auditable market cognition base.

**Role:** Primary AI-consumer validation for the ICAIF framing; content/CE probes remain secondary evidence that the world is nonempty.

## Claim under test

\[
\Delta_m = V_m(\mathrm{Compiled}) - V_m(\mathrm{Raw})
\]

plus understanding metrics:

- `thin_world_abstain_rate`: when the world model marks thin/dishonest support, does the agent abstain?
- `ear_proxy`: are actions evidence-bound to the bundle?
- completeness disclosure in the compiled bundle (`n_ready` / `n_missing`)

We do **not** claim unconditional LLM trading alpha.

## Treatments

| Arm | Information set |
| --- | --- |
| **Compiled** | PIT-safe world-model bundle: band statuses, completeness, honesty \((B,U,H)\), WMI/ACWMI, tilts, regime, cascade, evidence_ids, abstention guidance |
| **Raw** | Thin ungated feed: momentum only; no world index; no band roles; no abstention guidance |

## Public LLM adapters

- Offline: `public-llm-compiled-follower` (+ diagnostic mocks)
- Live (optional): OpenAI-compatible chat via `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `GLM_API_KEY`

Frozen prompts under `prompts/frozen/`; temperature `0.0`.
