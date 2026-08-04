#!/usr/bin/env python3
"""Render an ICAIF '26 shaped anonymous draft PDF (≤8 pages target).

Isolated from pdf/sci JF/RFS generators. Canonical TeX: pdf/icaif26/main.tex.
For CMT submission prefer Overleaf + ACM acmart sigconf anonymous.
"""

from __future__ import annotations

import csv
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
TAB_LOCAL = ROOT / "tables"
TAB_SRC = ROOT / "tables_src"
OUT = ROOT / "main_icaif26.pdf"
CONTENT_WIDTH = 6.5 * inch


def styles():
    font, font_b, font_i = "Times-Roman", "Times-Bold", "Times-Italic"
    return {
        "banner": ParagraphStyle(
            "banner", fontName=font_i, fontSize=8, alignment=TA_CENTER,
            textColor=colors.HexColor("#444"), spaceAfter=6,
        ),
        "title": ParagraphStyle(
            "title", fontName=font_b, fontSize=12.5, leading=15,
            alignment=TA_CENTER, spaceAfter=6,
        ),
        "author": ParagraphStyle(
            "author", fontName=font, fontSize=10, alignment=TA_CENTER, spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "h1", fontName=font_b, fontSize=11, leading=13, spaceBefore=9, spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "h2", fontName=font_b, fontSize=10, leading=12, spaceBefore=6, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "body", fontName=font, fontSize=9, leading=11.5,
            alignment=TA_JUSTIFY, firstLineIndent=10, spaceAfter=4,
        ),
        "abs": ParagraphStyle(
            "abs", fontName=font, fontSize=8.5, leading=11,
            alignment=TA_JUSTIFY, spaceAfter=4,
        ),
        "eq": ParagraphStyle(
            "eq", fontName=font_i, fontSize=9, leading=11,
            alignment=TA_CENTER, spaceBefore=2, spaceAfter=2,
        ),
        "caption": ParagraphStyle(
            "caption", fontName=font_i, fontSize=8, leading=10,
            alignment=TA_CENTER, spaceBefore=2, spaceAfter=6,
        ),
        "note": ParagraphStyle(
            "note", fontName=font_i, fontSize=8, leading=10, spaceAfter=4,
        ),
        "ref": ParagraphStyle(
            "ref", fontName=font, fontSize=7.5, leading=9.5,
            leftIndent=10, firstLineIndent=-10, spaceAfter=2,
        ),
        "kw": ParagraphStyle(
            "kw", fontName=font, fontSize=8, leading=10, spaceAfter=6,
        ),
    }


def P(text, style):
    return Paragraph(text, style)


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 7.5)
    canvas.drawString(
        0.75 * inch,
        letter[1] - 0.45 * inch,
        "Anonymous — ICAIF '26 draft (Financial World-Model Runtime)",
    )
    canvas.drawCentredString(letter[0] / 2, 0.45 * inch, str(doc.page))
    canvas.restoreState()


def make_table(data, col_widths=None, font_size=7.5):
    if not data:
        return Spacer(1, 1)
    n = max(len(r) for r in data)
    norm = [list(r) + [""] * (n - len(r)) for r in data]
    if col_widths is None:
        col_widths = [CONTENT_WIDTH / n] * n
    style_h = ParagraphStyle("th", fontName="Times-Bold", fontSize=font_size, leading=font_size + 1.5)
    style_b = ParagraphStyle("tb", fontName="Times-Roman", fontSize=font_size, leading=font_size + 1.5)
    styled = []
    for i, row in enumerate(norm):
        styled.append([
            Paragraph(str(c).replace("&", "&amp;"), style_h if i == 0 else style_b)
            for c in row
        ])
    t = Table(styled, colWidths=col_widths, hAlign="CENTER", repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#666")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    return t


def read_csv(name: str):
    for base in (TAB_LOCAL, TAB_SRC):
        path = base / name
        if path.exists():
            with open(path, newline="", encoding="utf-8") as f:
                return list(csv.reader(f))
    return None


def build():
    S = styles()
    story = []

    story.append(P(
        "ACM ICAIF '26 · anonymous draft · isolated folder <font face='Courier'>pdf/icaif26/</font> · "
        "not the JF/RFS manuscript",
        S["banner"],
    ))
    story.append(P(
        "Financial World-Model Runtime: Compiling Asynchronous Market Evidence for LLM Agents",
        S["title"],
    ))
    story.append(P("Anonymous Author(s)", S["author"]))
    story.append(P(
        "Canonical TeX: <font face='Courier'>pdf/icaif26/main.tex</font>. "
        "For CMT: compile with ACM <font face='Courier'>sigconf,anonymous</font> on Overleaf (≤8 pages incl. refs; no appendix). "
        "Deadline: 9 Aug 2026 AOE. Detailed rewrite checklist: <font face='Courier'>REVISION_PLAN.md</font>.",
        S["note"],
    ))

    story.append(P("<b>Abstract</b>", S["h1"]))
    story.append(P(
        "Large language models and autonomous agents increasingly consume market evidence, yet raw financial feeds are "
        "asynchronous, intermittently missing, and quality-heterogeneous. Generative world models assume a usable observation "
        "stream; financial agents often lack that stream. We propose a <i>financial world-model runtime</i>: a point-in-time "
        "compiler that maps raw multi-band evidence into an AI-consumable world state with explicit quality scores and "
        "abstention. The primitive is an epistemic observation O<sub>j,t</sub>=(x,τ,q,g,r); a compilation operator Π<sub>t</sub> "
        "yields ℱ<sup>AI</sup><sub>t</sub>; WMI/ACWMI gate actions. Empirically, on a cryptocurrency PIT panel, vintaged macro "
        "and stablecoin-flow <i>content</i> changes a transparent consumer rule relative to same-input momentum "
        "(ΔCE 0.334, p=0.034), with LOBO losses dominated by content. A Compiled-versus-Raw protocol tests the agent interface. "
        "<b>Thesis:</b> trading metrics validate that the compiled world has content—they do not proclaim a strategy Holy Grail.",
        S["abs"],
    ))
    story.append(P(
        "<b>Keywords:</b> world models; LLM agents; information-set compilation; selective prediction; point-in-time; cryptocurrency",
        S["kw"],
    ))

    story.append(P("1. Introduction", S["h1"]))
    story.append(P(
        "AI agents that analyze or trade markets do not observe a clean panel. Venue fragmentation, derivatives, on-chain flows, "
        "news, and macro vintages arrive on incompatible clocks. Literatures on ML asset pricing and on generative world models "
        "(Ha &amp; Schmidhuber; Dreamer; JEPA-style proposals) largely assume observations are already aligned. For LLM and "
        "tool-using agents, the prior systems problem is different: <i>compile</i> asynchronous evidence into a world state that "
        "can be read, refused when thin, and acted on when ready.",
        S["body"],
    ))
    story.append(P(
        "<b>Thesis.</b> We build a financial <i>world-model runtime</i>—an observation-side world model that compiles raw market "
        "evidence into a quality-tagged state for AI consumers. Trading statistics show nonempty content; they are not "
        "unconditional strategy alpha.",
        S["body"],
    ))
    story.append(P(
        "<b>Contributions.</b> (1) <i>Semantics:</i> epistemic observations, Π<sub>t</sub>, reconstruction bound, WMI/ACWMI, "
        "world-conditional abstention. (2) <i>Runtime:</i> PIT multi-band system, quality-tagged bundles, availability shocks, "
        "Compiled-versus-Raw protocol. (3) <i>Validation:</i> PIT content yields significant OOS CE vs same-input momentum; "
        "LOBO is content-dominated.",
        S["body"],
    ))

    story.append(P("2. Related Work", S["h1"]))
    story.append(P(
        "<b>World models in AI.</b> World models learn compact states and often dynamics for imagination/control. We address the "
        "complementary <i>observation-side</i> problem in markets: PIT-safe state construction with explicit quality before any "
        "dynamics model or LLM policy.",
        S["body"],
    ))
    story.append(P(
        "<b>LLM agents / selective prediction / PIT.</b> Tool-using LLMs need a compiled world interface. Selective classification "
        "justifies abstention under noise; we tie abstention to world quality. Macro vintages and crypto fragmentation motivate "
        "multi-band compilation.",
        S["body"],
    ))

    story.append(P("3. Financial World-Model Runtime", S["h1"]))
    story.append(P(
        "<b>Definition (epistemic observation).</b> O<sub>j,t</sub>=(x,τ,q,g,r): value, latest-available time, quality, main-view "
        "gate, semantic role.",
        S["body"],
    ))
    story.append(P(
        "<b>Definition (compilation).</b> W<sub>t</sub>=Π<sub>t</sub>(ℱ<sup>raw</sup><sub>t</sub>) with "
        "Π<sub>t</sub>=B<sub>t</sub>∘M<sub>t</sub>∘A<sub>t</sub>; ℱ<sup>AI</sup><sub>t</sub>=σ(W<sub>t</sub>). "
        "WMI<sub>t</sub>=B<sub>t</sub>U<sub>t</sub>H<sub>t</sub> scores world quality; ACWMI provides regime-conditional gating.",
        S["body"],
    ))
    story.append(P(
        "‖S̃<sub>t</sub>−S<sub>t</sub>‖ ≤ C<sub>1</sub>·delay + C<sub>2</sub>·noise + C<sub>3</sub>·missingness.",
        S["eq"],
    ))
    story.append(P(
        "<b>Prop. 1 (compilation ≠ feature expansion).</b> Enlarging raw span without Π need not enlarge usable ℱ<sup>AI</sup>. "
        "<b>Prop. 2 (world-conditional abstention).</b> If all non-abstain actions exceed c<sub>abs</sub>(W), abstain. "
        "<b>Def. (LOBO).</b> Band value = content channel + gating channel.",
        S["body"],
    ))
    story.append(P(
        "<b>Remark (scope).</b> We do <i>not</i> claim a learned p(s<sub>t+1</sub>|s<sub>t</sub>,a<sub>t</sub>). This paper is a "
        "<i>state compiler + abstention runtime</i>; generative dynamics are future work. Do not read this as Dreamer-for-markets.",
        S["body"],
    ))

    story.append(P("4. System", S["h1"]))
    story.append(P(
        "Anonymized prototype: multi-band collectors → vintage stores → BandPIT under previous-close clock "
        "(payoff r<sub>t</sub> uses info at (t−1) 23:59) → readiness/WMI/ACWMI → availability shocks O<sub>t</sub> → "
        "quality-tagged bundles → Compiled-versus-Raw consumers (frozen prompts, T=0, actions include abstain). "
        "Durable bands: {exchange, macro, alternative}.",
        S["body"],
    ))
    story.append(P(
        "Raw feeds → Π<sub>t</sub> / quality → World bundle W<sub>t</sub> → LLM or rule consumer → {trade, abstain}",
        S["eq"],
    ))
    story.append(P("Figure 1 (schematic). Observation-side financial world-model runtime.", S["caption"]))

    story.append(P("5. Experiments", S["h1"]))
    story.append(P(
        "<b>Setup.</b> PIT ~399 days, 10 liquid crypto names, prev-close clock, IS/OOS 200/200. Pre-specified contrast: "
        "mechanism (band content) − momentum. Bootstrap n=999, block=5; stationary confirmation.",
        S["body"],
    ))
    story.append(P(
        "<b>RQ1 Content.</b> Mechanism Sharpe/CE 0.767/0.132 vs momentum 0.101/−0.202; ΔCE=0.334 (p=0.034; stationary 0.022). "
        "Relative gap survives 10–25 bps costs; absolute CE is cost-fragile.",
        S["body"],
    ))
    story.append(P(
        "<b>RQ2 LOBO.</b> Dropping macro or alternative collapses to momentum (ΔCE=−0.334); content share=1.0 under ungated "
        "mechanism (gating residual 0). Identifies content channel; nontrivial gating needs denser archives.",
        S["body"],
    ))
    story.append(P(
        "<b>RQ3 Interface.</b> Compiled-versus-Raw offline mocks keep the protocol executable; EAR≈1. No live LLM alpha claimed.",
        S["body"],
    ))
    story.append(P(
        "<b>RQ4 Audit.</b> 2017–2026 without vintaged band archives: no hidden return-rule edge over momentum; unsigned proxies "
        "can fire without recreating PIT CE. Gains load on compiled PIT content.",
        S["body"],
    ))

    econ = read_csv("table_econ_oos.csv")
    if econ:
        # slim columns
        header = econ[0]
        keep = [0, 3, 4, 6, 7] if len(header) > 7 else list(range(len(header)))
        slim = [[r[i] if i < len(r) else "" for i in keep] for r in econ[:6]]
        story.append(KeepTogether([
            make_table(slim, font_size=7),
            P("Table 1. OOS economic value (content validation for the world state).", S["caption"]),
        ]))

    boot = read_csv("table_bootstrap_oos.csv")
    if boot:
        slim = [boot[0][:6]] + [r[:6] for r in boot[1:3]]
        story.append(KeepTogether([
            make_table(slim, font_size=7),
            P("Table 2. Headline bootstrap contrast (Mechanism − Momentum first).", S["caption"]),
        ]))

    lobo = read_csv("table_lobo_decomposition.csv")
    if lobo:
        story.append(KeepTogether([
            make_table(lobo[:5], font_size=6.5),
            P("Table 3. LOBO content vs gating under ungated mechanism.", S["caption"]),
        ]))

    story.append(P("6. Limitations", S["h1"]))
    story.append(P(
        "Sparse bands beyond exchange/macro/alternative; support-matched WMI thresholds required; absolute CE cost-fragile; "
        "consumer tests are protocol-first (mocks); observation-side runtime ≠ generative dynamics WM; no menu-wide claim "
        "versus always-long.",
        S["body"],
    ))

    story.append(P("7. Conclusion", S["h1"]))
    story.append(P(
        "Financial AI agents need a world to read. We formalize and implement a world-model runtime that compiles asynchronous "
        "evidence into an analyzable, abstention-aware, tradeable state, and show that compiled band content is economically "
        "nonempty under a disciplined PIT design. Generative dynamics and live multi-vendor LLM consumers are natural next "
        "layers on the same interface.",
        S["body"],
    ))

    story.append(P("References (selected)", S["h1"]))
    for r in [
        "Ha, D., Schmidhuber, J., 2018. World Models. NeurIPS.",
        "Hafner, D., et al., 2020. Dream to Control. ICLR.",
        "LeCun, Y., 2022. A Path Towards Autonomous Machine Intelligence.",
        "El-Yaniv, R., Wiener, Y., 2010. JMLR 11, 1605–1641.",
        "Geifman, Y., El-Yaniv, R., 2017. NeurIPS.",
        "Yao, S., et al., 2023. ReAct. ICLR.",
        "Gu, S., Kelly, B., Xiu, D., 2020. RFS 33, 2223–2273.",
        "Makarov, I., Schoar, A., 2020. JFE 135, 293–319.",
        "Liu, Y., Tsyvinski, A., Wu, X., 2022. JF 77, 1133–1177.",
        "Croushore, D., Stark, T., 2001. Journal of Econometrics 105, 111–130.",
        "White, H., 2000. Econometrica 68, 1097–1126.",
        "Politis, D.N., Romano, J.P., 1994. JASA 89, 1303–1313.",
    ]:
        story.append(P(r, S["ref"]))

    story.append(Spacer(1, 8))
    story.append(P(
        "Draft note: this ReportLab PDF approximates an 8-page conference shape for reading; "
        "replace with ACM sigconf PDF from main.tex before CMT upload and verify page count ≤ 8.",
        S["note"],
    ))

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="Financial World-Model Runtime (ICAIF '26 anonymous draft)",
        author="Anonymous",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print("Wrote", OUT, OUT.stat().st_size)


if __name__ == "__main__":
    build()
    try:
        from PyPDF2 import PdfReader
        print("pages:", len(PdfReader(str(OUT)).pages))
    except Exception:
        try:
            from pypdf import PdfReader
            print("pages:", len(PdfReader(str(OUT)).pages))
        except Exception as e:
            print("page count unavailable:", e)
