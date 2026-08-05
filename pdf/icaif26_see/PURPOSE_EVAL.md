# Paper B — purpose evaluation (opt2)

## Locked purpose

- **Goal:** Let public LLMs **see** the market (observation layer + world bundle).
- **Valve:** Hard refuse when the view is too thin to act.

## Opt2 enrichment (existing data only)

| Addition | Source tables | Role |
| --- | --- | --- |
| WMI gate open-share | `table_wmi_threshold_open_share.csv` | Production never opens |
| Open-slice Ungated live | `table_llm_band_thick_split.csv` | Content lower bound |
| Dense content split | `table_dense_world_content.csv` | Rule backtest by thickness |
| LOBO content share | `table_lobo_decomposition.csv` | Tilts nonempty via content channel |
| Archive scope honesty | panel statuses | Only 3 bands live; others missing |

## Fit scores (post-opt2)

| Criterion | Score |
| --- | --- |
| Purpose alignment | High |
| Spine clarity (see → valve → content) | High |
| Empiric thickness with available data | High (for what data allows) |
| Production Compiled-open claim | None (correctly refused) |
| Pages | ~6 / ≤8 |

## Dual-submission

Still sibling of Paper A (`pdf/icaif26/`). Prefer submitting **B** for the see-market pitch.
