# ICAIF ’26 — Paper B: See First, Refuse When Thin

**Title:** *See First, Refuse When Thin: Compiling Point-in-Time World Bundles for LLM Agents in Crypto Markets*

**Purpose (locked):**
Build the **data end** of end-to-end crypto quant for public LLMs (observation layer + world bundle).
Hard refusal is only the safety valve when the view is too thin to act.
Stack framing: **data/observation → decision → execution**; this paper owns only the data end.

| | Paper A (`pdf/icaif26/`) | Paper B (this folder) |
| --- | --- | --- |
| Spine | Observation layer with **quality-gated refusal** as primary live ranking | **Data-end seeing** (grounding / legibility) first; refusal = valve |
| Primary RQ | RQ1 gating ladder | RQ1 grounding workflow |
| Title focus | Compiling bundles **with** quality-gated refusal | See first; compile PIT world bundles for LLM agents |
| Shared | Same anonymized runtime, PIT panel, five arms, vendor IDs | Same |
| Differentiated claim | Soft disclosure does not enforce thin abstention | Compiled data end makes ready/missing/tilt verifiable |
| Length | ~8 pp | **~8 pp** systems + seeing empirics (≤8) |

**Submission (locked): Paper B only.** Paper A remains a sibling archive with a different estimand; do not dual-upload.

## Build

```bash
make paper-icaif26-see
# → pdf/icaif26_see/main.pdf
```

## Format

ACM `sigconf,anonymous`, ≤8 pages, no appendix. Isolated from `pdf/sci/`.
