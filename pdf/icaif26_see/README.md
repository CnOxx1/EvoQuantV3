# ICAIF ’26 — Paper B: Data End of Crypto Quant

**Purpose (locked):**
Build the **data end** of end-to-end crypto quant for public LLMs (observation layer + world bundle).
Hard refusal is only the safety valve when the view is too thin to act.
Stack framing: **data/observation → decision → execution**; this paper owns only the data end.

| | Paper A (`pdf/icaif26/`) | Paper B (this folder) |
| --- | --- | --- |
| Spine | Observation layer with **quality-gated refusal** as primary live ranking | **Data-end seeing** (grounding / legibility) first; refusal = valve |
| Primary RQ | RQ1 gating ladder | RQ1 grounding workflow |
| Title focus | Compiling bundles **with** quality-gated refusal | Data end that compiles bundles **so LLMs can see** |
| Shared | Same anonymized runtime, PIT panel, four arms, vendor IDs | Same |
| Differentiated claim | Soft disclosure does not enforce thin abstention | Compiled data end makes ready/missing/tilt verifiable |
| Length (opt2) | ~8 pp | **~6 pp** see-first + open-slice/content tables |

**Submit only one narrative to a venue unless the CFP allows clearly distinct contributions.**
These two folders are intentional siblings with **different primary estimands**; do not treat them as duplicate uploads of the same paper.

## Build

```bash
make paper-icaif26-see
# → pdf/icaif26_see/main.pdf
```

## Format

ACM `sigconf,anonymous`, ≤8 pages, no appendix. Isolated from `pdf/sci/`.
