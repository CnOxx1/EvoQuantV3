# Paper B optimization plan — execution status

## Plan (locked)

1. Submit **B** (see-market spine).
2. Use existing panel for nonempty / open-slice content (no fake Compiled-open).
3. Path to production open: historical multi-band backfill to lift WMI ≥ 0.2.

## Done in this pass

| Item | Status |
| --- | --- |
| Open-slice / WMI / dense tables | Done (opt2) |
| Case study: grounding C vs R + Raw mom5 action | Done |
| Structural WMI ceiling explained (5/8 bands missing) | Done |
| Counterfactual open protocol labeled as non-production | Done |
| Same-day news/event collector probe | Attempted; feeds flaky; **cannot** lift historical WMI |

## Not done (needs data program, not copy edits)

| Item | Blocker |
| --- | --- |
| Production Compiled-open live | max WMI≈0.093 until historical bands backfilled |
| Ungated grounding table | needs new LLM eval run |
| Stronger Raw baseline | optional; not required for see-first claim |

## Recommendation

Ship B now with see / valve / content lower bound.
Schedule multi-band historical backfill as the only path to a production-open chapter.
