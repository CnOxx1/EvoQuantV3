# Paper B optimization plan — execution status

## Plan (locked)

1. Submit **only Paper B** (data-end / see-first spine).
2. Use existing panel for nonempty / handoff / open-slice content (no fake Compiled-open).
3. Path to production open: historical multi-band **archive** to lift WMI ≥ 0.2 (not same-day RSS).

## Keys / collectors

| Band | Needs API key? | Notes |
| --- | --- | --- |
| News | **No** (public RSS) | Live collect works (~days of lookback only) |
| Event calendar | Needs **source URLs** configured (not a vendor key by default) | Unconfigured → 0 events |
| On-chain / options / tokenomics | Often yes (Etherscan etc.) | Not required for B submit |
| LLM re-eval | Vendor/gateway key | **Unavailable**; use frozen transcripts |

Same-day keyless news (**~241** articles, ~4 pub days) **cannot** lift historical OOS WMI on the 2025-07..2026-08 panel.

## Done

| Item | Status |
| --- | --- |
| Open-slice / WMI / dense / LOBO | Done |
| Handoff backtest table (prod gate vs tilts) | Done |
| Case study + sufficiency dissociation | Done |
| Keyless news probe | Done; no historical WMI lift |
| LLM re-runs | Skipped (no quota) |

## Not done (needs historical archive, not copy edits)

| Item | Blocker |
| --- | --- |
| Production Compiled-open live | max WMI≈0.093 until historical bands backfilled |
| Ungated grounding table | needs LLM quota |

## Recommendation

Ship **B only** with see / valve / handoff lower bound.
Schedule historical multi-band archive as the only path to a production-open chapter.
