# ICAIF ’26 — Paper B: Seeing the Market

**Purpose (locked):**
Make public LLMs **see** crypto markets (observation layer + world bundle).
Hard refusal is only the safety valve when the view is too thin to act.

| | Paper A (`pdf/icaif26/`) | Paper B (this folder) |
| --- | --- | --- |
| Spine | Observation layer with **quality-gated refusal** as primary live ranking | **Seeing** (grounding / legibility) first; refusal second |
| Primary RQ | RQ1 gating ladder | RQ1 grounding workflow |
| Title focus | Compiling bundles **with** quality-gated refusal | Compiling bundles **so LLMs can see** |
| Shared | Same anonymized runtime, PIT panel, four arms, vendor IDs | Same |
| Differentiated claim | Soft disclosure does not enforce thin abstention | Compiled bundles make ready/missing/tilt verifiable |
| Length (optimized) | ~8 pp | **~5 pp** see-first spine |

**Submit only one narrative to a venue unless the CFP allows clearly distinct contributions.**
These two folders are intentional siblings with **different primary estimands**; do not treat them as duplicate uploads of the same paper.

## Build

```bash
make paper-icaif26-see
# → pdf/icaif26_see/main.pdf
```

## Format

ACM `sigconf,anonymous`, ≤8 pages, no appendix. Isolated from `pdf/sci/`.
