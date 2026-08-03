# Standalone SCI manuscript (EvoQuant-grounded)

This package is a **standalone** SCI submission. It does **not** depend on any unused prior paper. All theory is formalized from the EvoQuant repository; all mechanism metrics are computed by importing production calculators.

## Files

| File | Role |
| --- | --- |
| `main_acwmi_sci.tex` | Elsevier elsarticle source |
| `main_acwmi_sci.pdf` | English PDF with figures/tables |
| `run_paper_experiments.py` | Project-bound experiment runner |
| `generate_sci_pdf.py` | PDF renderer |
| `EXPERIMENT_RESULTS.md` | Latest numeric summary |

## Reproduce

```bash
PYTHONPATH=. python3 pdf/sci/run_paper_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
PYTHONPATH=. python3 -m pytest tests/ai_market_context tests/asset_readiness \
  tests/test_contagion_risk.py tests/test_alpha_decay.py \
  tests/test_liquidation_cascade.py -q
```
