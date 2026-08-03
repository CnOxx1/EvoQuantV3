# SCI manuscript package

This folder contains the English SCI-ready manuscript that optimizes the first-generation World Model Index (WMI) into a Regime-Conditional Adaptive World Model (RCA-WM / ACWMI).

## Files

| File | Description |
| --- | --- |
| `main_acwmi_sci.tex` | Elsevier `elsarticle` LaTeX source (submission-ready structure) |
| `main_acwmi_sci.pdf` | Rendered English PDF with figures/tables |
| `run_paper_experiments.py` | Reproducible experiment runner (imports production WMI) |
| `generate_sci_pdf.py` | PDF renderer embedding `pdf/figures` and `pdf/tables` |
| `EXPERIMENT_RESULTS.md` | Latest numeric summary |
| `experiment_summary.json` | Machine-readable summary |

## Reproduce

```bash
# from repo root
PYTHONPATH=. python3 pdf/sci/run_paper_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
```

Related unit tests used for validation:

```bash
PYTHONPATH=. python3 -m pytest tests/ai_market_context tests/test_contagion_risk.py \
  tests/test_alpha_decay.py tests/test_liquidation_cascade.py tests/asset_readiness -q
```

## Suggested SCI venues

- Expert Systems with Applications
- Information Sciences
- Knowledge-Based Systems
- Finance Research Letters (shorter version)
