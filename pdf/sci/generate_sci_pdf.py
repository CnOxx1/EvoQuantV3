#!/usr/bin/env python3
"""Render standalone SCI PDF grounded in EvoQuant project results."""

from __future__ import annotations

import csv
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"
TAB = ROOT / "tables"
OUT_EN = Path(__file__).resolve().parent / "main_acwmi_sci.pdf"
OUT = ROOT / "main_cn_acwmi_sci.pdf"


def styles():
    base = getSampleStyleSheet()
    font, font_b, font_i = "Times-Roman", "Times-Bold", "Times-Italic"
    return {
        "journal": ParagraphStyle("journal", fontName=font_i, fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#444"), spaceAfter=8),
        "title": ParagraphStyle("title", fontName=font_b, fontSize=13.5, leading=17, alignment=TA_CENTER, spaceAfter=10),
        "author": ParagraphStyle("author", fontName=font, fontSize=11, alignment=TA_CENTER, spaceAfter=2),
        "affil": ParagraphStyle("affil", fontName=font_i, fontSize=9, alignment=TA_CENTER, spaceAfter=8),
        "h1": ParagraphStyle("h1", fontName=font_b, fontSize=12, leading=15, spaceBefore=12, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=font_b, fontSize=11, leading=14, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", fontName=font, fontSize=10, leading=13.5, alignment=TA_JUSTIFY, firstLineIndent=12, spaceAfter=6),
        "abs": ParagraphStyle("abs", fontName=font, fontSize=9.5, leading=13, alignment=TA_JUSTIFY, spaceAfter=6),
        "caption": ParagraphStyle("caption", fontName=font, fontSize=9, leading=11, alignment=TA_CENTER, spaceBefore=3, spaceAfter=10),
        "ref": ParagraphStyle("ref", fontName=font, fontSize=9, leading=11, leftIndent=12, firstLineIndent=-12, spaceAfter=3),
        "eq": ParagraphStyle("eq", fontName=font_i, fontSize=10, leading=13, alignment=TA_CENTER, spaceBefore=4, spaceAfter=4),
        "note": ParagraphStyle("note", fontName=font_i, fontSize=9, leading=12, spaceAfter=6),
        "hl": ParagraphStyle("hl", fontName=font, fontSize=9.5, leading=12, leftIndent=8, spaceAfter=2),
    }


def P(text, style):
    return Paragraph(text, style)


def read_csv(name):
    with open(TAB / name, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def make_table(data, col_widths=None):
    t = Table(data, colWidths=col_widths, hAlign="CENTER")
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#666666")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def fig(name, width=16 * cm, ratio=0.48):
    return Image(str(FIG / name), width=width, height=width * ratio)


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 8)
    canvas.drawString(2 * cm, A4[1] - 1.2 * cm, "Li — Adaptive World Models for EvoQuant")
    canvas.drawCentredString(A4[0] / 2, 1.2 * cm, str(doc.page))
    canvas.restoreState()


def build():
    S = styles()
    story = []
    story.append(P("SCI manuscript draft (Elsevier-like formatting) — standalone, project-grounded", S["journal"]))
    story.append(P(
        "Regime-Conditional Adaptive World Models for AI Cryptocurrency Market Analysis: "
        "Formalization and Project-Grounded Evaluation of EvoQuant",
        S["title"],
    ))
    story.append(P("Guocong Li", S["author"]))
    story.append(P("Independent Researcher; Email: lmu151638@gmail.com", S["affil"]))
    story.append(P("Suggested venues: <i>Expert Systems with Applications</i> / <i>Information Sciences</i> / <i>Knowledge-Based Systems</i>", S["affil"]))

    story.append(P("<b>Highlights</b>", S["h2"]))
    for h in [
        "Formalizes EvoQuant’s multi-domain AI market context as a regime-conditional world model.",
        "Defines ACWMI using hierarchical breadth, continuous honesty, signal integrity, and consistency.",
        "Evaluates with EvoQuant calculators rather than detached synthetic scores.",
        "Cascade/crisis detection F1 = 0.895 / 0.793; AC abstention cuts crisis unsafe actions from 81% to 0.",
        "All figures/tables are reproducible from the open repository.",
    ]:
        story.append(P("• " + h, S["hl"]))

    story.append(P("<b>Abstract</b>", S["h2"]))
    story.append(P(
        "AI market systems often fail because the market world they consume is incomplete, stale, or silently contaminated—"
        "not because the predictor lacks capacity. This paper studies that failure mode through <b>EvoQuant</b>, an open "
        "cryptocurrency data world-model infrastructure comprising 43 data domains, 13 audit bands, 39 logic modules, and a "
        "production World Model Index (WMI) already implemented in code. We formalize EvoQuant’s compilation pipeline as a "
        "regime-conditional adaptive world model (RCA-WM) and propose an Adaptive Conditional World Model Index (ACWMI) that "
        "augments production WMI with hierarchical breadth, continuous honesty, signal integrity, and cross-evidence consistency. "
        "All mechanism scores used in evaluation are computed by EvoQuant’s own calculators (regime classification, liquidation "
        "cascade, contagion, alpha decay, flow decomposition, volatility, and degradation control). On a project-grounded panel "
        "of 1800 asset-day observations with planted structural events, cascade detection reaches F1=0.895, crisis detection "
        "F1=0.793, and coarse regime match accuracy is 71.6%. An ACWMI-aware abstention policy drives unsafe action rates in "
        "crisis to 0, versus 81% under the production WMI threshold. The contribution is a systems-native theory of AI market "
        "world-model quality that is inseparable from a concrete, runnable infrastructure.",
        S["abs"],
    ))
    story.append(P("<b>Keywords:</b> AI market world model; cryptocurrency; data-centric AI; quality governance; selective prediction; system resilience", S["note"]))

    story.append(P("1. Introduction", S["h1"]))
    story.append(P(
        "Most discussions of AI trading emphasize model architecture or feature lists. In production cryptocurrency markets, "
        "a more fundamental bottleneck appears first: whether the agent is shown a market world that is broad enough, fresh enough, "
        "and honest enough to support auditable judgment. Identical price paths can correspond to incompatible states once exchange "
        "fragmentation, leverage crowding, funding distortions, options positioning, unlock pressure, and macro liquidity are considered.",
        S["body"],
    ))
    story.append(P(
        "EvoQuant is built as that missing layer. It is not a trading bot. It is an AI-oriented market world-model infrastructure that "
        "collects heterogeneous evidence, maintains latest_* snapshots, gates AI-ready inputs, separates main/diagnostic views, and "
        "aggregates an ai_market_context bundle. The current repository exposes 43 data domains, 13 audit bands, 39 logic modules, "
        "about 1.34×10<sup>5</sup> lines of Python, and a production index WMI<sub>t</sub>=B<sub>t</sub>×U<sub>t</sub>×H<sub>t</sub> "
        "with abstention suggested when WMI&lt;0.2. This paper formalizes that stack as a regime-conditional adaptive world model and "
        "evaluates the proposed ACWMI using EvoQuant’s own runnable analytics.",
        S["body"],
    ))

    story.append(P("2. Related work", S["h1"]))
    story.append(P(
        "Conditional asset pricing treats expected returns as functions of an information set (Fama and French, 1993; Cochrane, 2005). "
        "Machine-learning pricing expands characteristics (Gu et al., 2020; Kelly et al., 2019; Nagel, 2021), while multiple-testing "
        "critiques warn against undisciplined expansion (Harvey et al., 2016). Measurement-error and robustness theories emphasize "
        "reliable observation (Fuller, 1987; Carroll et al., 2006; Hansen and Sargent, 2008). Selective prediction studies refusal under "
        "uncertainty (Chow, 1957; Geifman and El-Yaniv, 2017). Data-centric AI argues governance can dominate model changes (Zha et al., 2023). "
        "Crypto microstructure documents fragmented venues and shared factors (Makarov and Schoar, 2020; Liu et al., 2022). "
        "This paper differs by binding world-model theory to a concrete runnable system rather than a detached feature benchmark.",
        S["body"],
    ))

    story.append(P("3. The EvoQuant world-model substrate", S["h1"]))
    story.append(P(
        "EvoQuant compiles market reality through data_layer → latest_* → quality gate → logic_pipeline → ai_market_context. "
        "Production WMI uses asset-readiness coverage as breadth, pipeline-latency freshness as stability, and quality-flag honesty. "
        "Table 1 and Figures 1–2 summarize the empirical substrate used throughout the paper.",
        S["body"],
    ))
    story.append(KeepTogether([fig("fig1_architecture.png", 16.3*cm, 0.50), P("Fig. 1. EvoQuant world-model compilation and ACWMI overlay.", S["caption"])]))
    inv_tbl = [
        ["Quantity", "Value"],
        ["Data domains", "43"],
        ["Logic modules", "39"],
        ["Audit evidence bands", "13"],
        ["Python files", "784"],
        ["Approximate LOC", "133,952"],
        ["Test files", "56"],
    ]
    story.append(make_table(inv_tbl, [6*cm, 3*cm]))
    story.append(P("Table 1. EvoQuant repository inventory used in this study.", S["caption"]))
    story.append(KeepTogether([fig("fig2_coverage_compare.png", 16*cm, 0.42), P("Fig. 2. Project inventory and asset-readiness band weights.", S["caption"])]))

    story.append(P("4. Regime-conditional adaptive world models", S["h1"]))
    story.append(P(
        "We define hierarchical breadth from domains/bands/assets using production BAND_WEIGHTS; continuous honesty from exclusion and "
        "contamination rates; signal integrity from alpha_decay half-life/crowding/surprise; and consistency from directional agreement "
        "across project engines (momentum, smart-money flow, cascade, contagion, VPIN). ACWMI is the weighted geometric mean",
        S["body"],
    ))
    story.append(P("ACWMI<sub>t</sub><sup>(r)</sup> = exp( Σ γ<sub>x</sub>(r) log x<sub>t</sub> / Σ γ<sub>x</sub>(r) ), x∈{B,U,H,S,C}.", S["eq"]))
    story.append(P(
        "Crisis regimes emphasize honesty/consistency; trend regimes emphasize signal integrity. Abstention is degradation-aware and "
        "mechanism-aware (cascade/crisis detections), not only a fixed WMI cutoff.",
        S["body"],
    ))

    story.append(P("5. Experimental design", S["h1"]))
    story.append(P(
        "Synthetic paths are used only as inputs. Every reported mechanism metric is computed by importing EvoQuant classes: "
        "RegimeClassifier, LiquidationCascadeCalculator, ContagionRiskCalculator, AlphaDecayCalculator, FlowDecompositionCalculator, "
        "VolatilityCalculator, AIMarketContextService._compute_world_model_index, and DegradationManager. The panel covers 10 assets × "
        "180 days (N=1800) with planted regimes/outages. Evaluation targets are planted structural events, not scores built from ACWMI itself.",
        S["body"],
    ))

    story.append(P("6. Results", S["h1"]))
    story.append(P("6.1 Mechanism detection", S["h2"]))
    story.append(P(
        "Table 2 shows cascade detection F1=0.895 and crisis detection F1=0.793; coarse regime match accuracy is 71.6%. "
        "These metrics come from the same calculators shipped in the repository.",
        S["body"],
    ))
    det = read_csv("table3_detection_metrics.csv")
    story.append(make_table(det, [3.5*cm, 2.2*cm, 2.2*cm, 2.0*cm, 1.8*cm, 2.2*cm]))
    story.append(P("Table 2. Detection performance on planted structural events.", S["caption"]))

    story.append(P("6.2 WMI versus ACWMI and safety", S["h2"]))
    story.append(P(
        "Table 3 and Figures 3–5 show the central systems result: in crisis, production WMI still permits action in 81% of cases, "
        "while the ACWMI-aware policy reduces unsafe actions to 0. In calm range regimes both policies rarely abstain (~4.7%).",
        S["body"],
    ))
    reg = read_csv("table2_regime_summary.csv")
    reg_short = [["regime", "N", "WMI", "ACWMI", "abstain_WMI", "abstain_AC", "unsafe_WMI", "unsafe_AC"]]
    for r in reg[1:]:
        reg_short.append([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]])
    story.append(make_table(reg_short, [1.7*cm] + [1.7*cm] * 7))
    story.append(P("Table 3. Regime-level world-model scores and safety.", S["caption"]))

    story.append(KeepTogether([fig("fig3_factor_paths.png", 16*cm, 0.55), P("Fig. 3. Time paths of production WMI, ACWMI, and mechanism outputs.", S["caption"])]))
    story.append(KeepTogether([fig("fig4_regime_box.png", 15.5*cm, 0.42), P("Fig. 4. Regime heterogeneity of WMI and ACWMI.", S["caption"])]))
    story.append(KeepTogether([fig("fig5_quality_scatter.png", 16*cm, 0.42), P("Fig. 5. Cascade engine outputs and unsafe-action rates.", S["caption"])]))

    story.append(P("6.3 Outages, Pareto frontier, and degradation", S["h2"]))
    out = read_csv("table4_outage_event_study.csv")
    out_short = [["regime", "outage", "N", "WMI", "ACWMI", "cascade_p", "abstain_AC", "unsafe_WMI"]]
    for r in out[1:]:
        out_short.append([r[0], r[1], r[2], r[3], r[4], r[5], r[7], r[9]])
    story.append(make_table(out_short, [1.6*cm]*8))
    story.append(P("Table 4. Outage contrasts by regime.", S["caption"]))
    story.append(KeepTogether([fig("fig6_event_study.png", 15.2*cm, 0.42), P("Fig. 6. Outage event profile in crisis regimes.", S["caption"])]))
    story.append(KeepTogether([fig("fig7_pareto.png", 14.5*cm, 0.48), P("Fig. 7. Abstention–safety Pareto frontier.", S["caption"])]))

    deg = read_csv("table5_degradation_matrix.csv")
    story.append(make_table(deg, [4.2*cm, 2.0*cm, 2.0*cm, 2.0*cm, 2.2*cm]))
    story.append(P("Table 5. Module executability under DegradationManager (1=allowed).", S["caption"]))
    story.append(KeepTogether([fig("fig8_honesty_incentive.png", 15.2*cm, 0.42), P("Fig. 8. Degradation levels versus breadth/honesty/world-model scores.", S["caption"])]))

    story.append(P("7. Discussion", S["h1"]))
    story.append(P(
        "Three claims follow. First, EvoQuant already implements a nontrivial world-model stack; the scientific task is to formalize "
        "and stress-test it. Second, production WMI’s fixed 0.2 threshold is too coarse for crisis refusal. Third, mechanism engines "
        "are first-class citizens of world-model quality. Limitations: controlled input paths are not yet a full live-market PIT backtest; "
        "regime exponents are pre-specified; external validity beyond crypto remains open.",
        S["body"],
    ))

    story.append(P("8. Conclusion", S["h1"]))
    story.append(P(
        "This paper presented a standalone formalization and evaluation of AI market world-model quality grounded entirely in EvoQuant. "
        "By elevating production WMI to regime-conditional ACWMI, and by scoring detection/safety with the repository’s own calculators, "
        "we show that world-model quality can be treated as a measurable systems property. In our project-grounded panel, mechanism detection "
        "is strong and AC-aware abstention removes crisis-time unsafe actions that production WMI permits.",
        S["body"],
    ))

    story.append(P("Appendix A. Reproducibility", S["h1"]))
    story.append(P(
        "Experiments: <font face='Courier'>pdf/sci/run_paper_experiments.py</font>. PDF build: "
        "<font face='Courier'>pdf/sci/generate_sci_pdf.py</font>. LaTeX source: "
        "<font face='Courier'>pdf/sci/main_acwmi_sci.tex</font>. Related unit tests and API smoke checks were executed during manuscript preparation.",
        S["body"],
    ))

    story.append(P("References", S["h1"]))
    refs = [
        "Carroll, R.J., Ruppert, D., Stefanski, L.A., Crainiceanu, C.M., 2006. Measurement Error in Nonlinear Models. 2nd ed. Chapman & Hall/CRC.",
        "Chow, C., 1957. An optimum character recognition system using decision functions. IRE Trans. Electronic Computers 6, 247–254.",
        "Cochrane, J.H., 2005. Asset Pricing. Revised ed. Princeton University Press.",
        "Fama, E.F., French, K.R., 1993. Common risk factors in the returns on stocks and bonds. Journal of Financial Economics 33, 3–56.",
        "Fuller, W.A., 1987. Measurement Error Models. Wiley.",
        "Geifman, Y., El-Yaniv, R., 2017. Selective classification for deep neural networks. NeurIPS.",
        "Gu, S., Kelly, B., Xiu, D., 2020. Empirical asset pricing via machine learning. Review of Financial Studies 33, 2223–2273.",
        "Hansen, L.P., Sargent, T.J., 2008. Robustness. Princeton University Press.",
        "Harvey, C.R., Liu, Y., Zhu, H., 2016. …and the cross-section of expected returns. Review of Financial Studies 29, 5–68.",
        "Kelly, B.T., Pruitt, S., Su, Y., 2019. Characteristics are covariances. Journal of Financial Economics 134, 501–524.",
        "Liu, Y., Tsyvinski, A., Wu, X., 2022. Common risk factors in cryptocurrency. Journal of Finance 77, 1133–1177.",
        "Makarov, I., Schoar, A., 2020. Trading and arbitrage in cryptocurrency markets. Journal of Financial Economics 135, 293–319.",
        "Nagel, S., 2021. Machine Learning in Asset Pricing. Princeton University Press.",
        "Zha, D., Bhat, Z.P., Lai, K.-H., Yang, F., Hu, X., 2023. Data-centric AI: Perspectives and challenges. SDM.",
    ]
    for r in refs:
        story.append(P(r, S["ref"]))

    doc = SimpleDocTemplate(
        str(OUT_EN),
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="Regime-Conditional Adaptive World Models for EvoQuant",
        author="Guocong Li",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    OUT.write_bytes(OUT_EN.read_bytes())
    print("Wrote", OUT_EN, OUT_EN.stat().st_size)
    print("Wrote", OUT, OUT.stat().st_size)


if __name__ == "__main__":
    build()
