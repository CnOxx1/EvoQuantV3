# Theory-first JF / SCI manuscript + paper lab

**Theory first, project second.**

## Complete JF/RFS working paper (canonical)

| Artifact | Path |
| --- | --- |
| English TeX (full) | `pdf/sci/main_jf_rfs.tex` |
| English PDF | `pdf/sci/main_jf_rfs.pdf` (`make paper-full`) |
| Chinese full draft | `pdf/cn/main_cn_jf.md` / `.pdf` |
| Original theory source | `pdf/original/main_cn_pm.txt` |

- Proof system: EvoQuant (multi-band collectors, readiness, WMI/ACWMI, time-slice PIT)
- EvoQuant is **not** the source of the theory — it is the empirical instrument

## Project APIs that serve the paper

| Concern | Production API |
| --- | --- |
| Multi-band PIT \(W_t\) | `logic_layer.time_slice.band_pit.BandPITService` / domain `band_readiness` |
| Availability shocks \(O_t\) | `data_layer.data_quality.availability.load_availability_shocks` |
| WMI / ACWMI + abstain | `AIMarketContextService._compute_world_model_index` + env thresholds |
| Daily audit trail | pipeline module `data_quality_audit` → market-world audit snapshots |

Env knobs (see `config/settings.py`):

```bash
export WORLD_MODEL_INDEX_MODE=acwmi   # or wmi (default)
export WMI_ABSTAIN_THRESHOLD=0.2
export ACWMI_ABSTAIN_THRESHOLD=0.35
```

## Reproduce (Makefile)

```bash
make paper-smoke          # production API smoke
make paper-pit            # rebuild PIT panel from local SQLite history
make paper-lab            # PIT → JF experiments → core figures/PDF → SCI PDF
make paper-lab WITH_BOOTSTRAP=1   # also bootstrap multi-band archive first
make paper-core           # World-Model-First core figures + Chinese PDF only
make paper-pdf
make test-paper
```

> Paper lab forces `DB_SPLIT_ENABLED=1` so readiness is read from
> `exchange_data.db` / `market_data.db` / `analytics.db` (not empty `crypto_data.db`).

Or via the orchestrator / scripts:

```bash
PYTHONPATH=. python3 pdf/sci/paper_lab.py smoke
PYTHONPATH=. python3 pdf/sci/paper_lab.py all
PYTHONPATH=. python3 pdf/sci/paper_lab.py all --with-bootstrap

# equivalent low-level path
PYTHONPATH=. python3 pdf/sci/bootstrap_multiband_archive.py
PYTHONPATH=. python3 pdf/sci/build_pit_archive.py
PYTHONPATH=. python3 pdf/sci/run_pit_jf_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
```

## Scripts

| Script | Role |
| --- | --- |
| `paper_lab.py` | one-command orchestrator |
| `bootstrap_multiband_archive.py` | fill history tables (OKX-reachable envs) |
| `build_pit_archive.py` | PIT panel via `BandPITService` + production WMI/ACWMI |
| `run_pit_jf_experiments.py` | OOS econ / LOBO / thin–thick on real PIT |
| `run_jf_experiments.py` | Yahoo-return JF suite (constructed readiness) |
| `run_paper_experiments.py` | earlier synthetic/project analytics suite |
| `generate_sci_pdf.py` | compile `main_acwmi_sci.tex` |

Durable historical bands in the current checked-in archive summary: **exchange, macro, alternative**.  
News/onchain/options/tokenomics may be thin or collection-day right-censored depending on bootstrap depth.
