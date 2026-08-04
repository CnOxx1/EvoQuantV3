# ICAIF '26 — Financial World-Model Runtime

**Isolated from** `pdf/sci/` (JF/RFS). Submit **only** artifacts from this folder.

| Item | Value |
| --- | --- |
| Venue | [ACM ICAIF '26](https://icaif2026.org/) (Milan, 14–17 Nov 2026) |
| Deadline | **9 Aug 2026, 23:59 AOE** |
| Format | ACM `acmart` **`sigconf,anonymous,review`** |
| Limit | **≤ 8 pages** total (figures + references); **no appendix** |
| Submit | [CMT ICAIF2026](https://cmt3.research.microsoft.com/ICAIF2026/) |
| Template | [ACM proceedings template](https://www.acm.org/publications/proceedings-template) / [Overleaf ACM](https://www.overleaf.com/gallery/tagged/acm-official) |

## Build (local)

```bash
make paper-icaif26
# → pdf/icaif26/main.pdf
```

Requires TeX Live with `acmart` dependencies (Libertine/newtx). This repo vendors `acmart.cls` and `ACM-Reference-Format.bst` generated from CTAN `acmart`.

Manual:

```bash
cd pdf/icaif26
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

## Key files

| File | Role |
| --- | --- |
| `main.tex` | **Canonical ACM anonymous submission source** |
| `main.pdf` / `main_icaif26.pdf` | Compiled PDF |
| `refs.bib` | Bibliography |
| `acmart.cls` | Vendored ACM class |
| `ACM-Reference-Format.bst` | ACM bib style |
| `REVISION_PLAN.md` | Framing / page-budget checklist |
| `figures/` | Curated figures for this submission |

## Anonymity

- Authors set to Anonymous; no org/repo URLs in the PDF.
- Camera-ready: drop `anonymous,review`, restore authors, fix DOI/ISBN placeholders.
