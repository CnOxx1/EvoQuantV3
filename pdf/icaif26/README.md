# ICAIF '26 — Market World-Model Runtime

**Isolated from** `pdf/sci/` (JF/RFS) and `pdf/sci/main_ai_wm.*` (long AI framing draft).  
Do **not** mix submission PDFs or anonymization state with those folders.

| Item | Value |
| --- | --- |
| Venue | [ACM ICAIF '26](https://icaif2026.org/) (Milan, 14–17 Nov 2026) |
| Deadline | **9 Aug 2026, 23:59 AOE** (extended from 2 Aug) |
| Format | ACM `sigconf` + `anonymous`, **≤ 8 pages total** (figures + references included) |
| Review | Double-blind; **no appendix / no supplementary** |
| Submit | [CMT ICAIF2026](https://cmt3.research.microsoft.com/ICAIF2026/) |
| Thesis | A financial **world-model runtime** compiles raw async evidence into an LLM-analyzable, abstention-aware, tradeable state; trading metrics validate nonempty content—not a strategy Holy Grail. |

## Folder layout

```
pdf/icaif26/
  README.md                 ← this file
  REVISION_PLAN.md          ← detailed rewrite checklist (CN+EN)
  main.tex                  ← 8-page ACM-oriented draft (anonymous)
  refs.bib                  ← bibliography
  generate_icaif26_pdf.py   ← ReportLab PDF when pdflatex unavailable
  main_icaif26.pdf          ← generated submission-shaped draft
  figures/ tables/          ← local copies or curated subsets
  figures_src/ tables_src/  ← symlinks to shared empirics (read-only)
  SOURCE_AI_WM.tex          ← symlink to long AI framing sibling (not for submit)
  vendor/                   ← ACM bst + notes for Overleaf/acmart.cls
```

## Regenerate PDF (no TeX)

```bash
python pdf/icaif26/generate_icaif26_pdf.py
# → pdf/icaif26/main_icaif26.pdf
```

## Compile ACM PDF (Overleaf / local TeX Live)

1. Upload `main.tex`, `refs.bib`, figures, and ACM template (`acmart` with `sigconf,anonymous`).
2. Or: `pdflatex && bibtex && pdflatex && pdflatex` after placing `acmart.cls` in `vendor/` / TEXINPUTS.
3. Check **page count ≤ 8** before CMT upload.

## Anonymization checklist

- [ ] No author names / emails / affiliations in PDF
- [ ] No `EvoQuant`, GitHub org, or identifiable repo URLs
- [ ] Self-cites in third person; do not cite anonymous arXiv preprint of *this* paper
- [ ] Replication code referred to as “anonymous repository” if needed
- [ ] Camera-ready: switch to `\documentclass[sigconf]{acmart}` and restore authors

## Make target

```bash
make paper-icaif26
```
