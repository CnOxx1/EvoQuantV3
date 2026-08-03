# Theory-first SCI manuscript

**Theory first, project second.**

- Theory: RCA-WM / ACWMI / conditional compilation / degradation-aware abstention  
- Proof system: EvoQuant (43 domains / 13 bands / 39 logic modules / baseline WMI)  
- EvoQuant is **not** the source of the theory

## Reproduce

```bash
PYTHONPATH=. python3 pdf/sci/run_paper_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
```
