# Paper optimization policy (core theory first)

## When to edit prose only
- Abstract / intro / conclusion framing
- Demoting secondary empirics (ACWMI horse-race, AI-consumer)
- Disclosure text (migration, limits)
- Theory reading guides that do **not** change formulas

## When you **must** run project code
| Change | Command |
| --- | --- |
| PIT clock / panel rebuild | `make paper-pit` (or migrate fallback) |
| LOBO / bootstrap / costs / placebos | `python pdf/sci/run_pit_jf_experiments.py` or `make paper-lab` |
| Long-span joint content (macro+stablecoin) | `python pdf/sci/run_longspan_content_audit.py` |
| Persist paper objects to analytics | runs inside `run_pit_jf_experiments.py` → `paper_world_model_snapshots` |
| Return reconciliation | `make paper-reconcile` |
| AI-consumer transcripts | `make paper-llm-consumer` |
| Manuscript PDF after TeX/generator edits | `python pdf/sci/generate_full_manuscript_pdf.py` |
| Regression tests | `make test-paper` |

## Core theory that must not be deleted
1. Epistemic observations \(O_{j,t}=(x,\tau,q,g,r)\)
2. Compilation operator \(\Pi_t:\mathcal{F}^{raw}\to\mathcal{F}^{AI}\)
3. Reconstruction bound (delay / noise / missingness)
4. SDF interface / compilation wedge
5. LOBO = content + gating
6. WMI/ACWMI + world-conditional abstention (keep as apparatus; empirics may be secondary)

## Headline empirical claim (lock)
Pre-specified **mechanism − momentum** on PIT band content, plus content-dominant LOBO; long-span audit rules out hidden return-rule alpha.
