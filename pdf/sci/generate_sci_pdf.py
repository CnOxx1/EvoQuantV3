#!/usr/bin/env python3
"""Render an SCI-style English PDF with embedded figures and tables."""

from __future__ import annotations

import csv
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
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
OUT = ROOT / "main_cn_acwmi_sci.pdf"
# Also English-named alias
OUT_EN = Path(__file__).resolve().parent / "main_acwmi_sci.pdf"


def styles():
    base = getSampleStyleSheet()
    font = "Times-Roman"
    font_b = "Times-Bold"
    font_i = "Times-Italic"
    return {
        "journal": ParagraphStyle("journal", fontName=font_i, fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#444444"), spaceAfter=8),
        "title": ParagraphStyle("title", fontName=font_b, fontSize=14, leading=18, alignment=TA_CENTER, spaceAfter=10),
        "author": ParagraphStyle("author", fontName=font, fontSize=11, alignment=TA_CENTER, spaceAfter=2),
        "affil": ParagraphStyle("affil", fontName=font_i, fontSize=9, alignment=TA_CENTER, spaceAfter=8),
        "h1": ParagraphStyle("h1", fontName=font_b, fontSize=12, leading=16, spaceBefore=12, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=font_b, fontSize=11, leading=14, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", fontName=font, fontSize=10, leading=13.5, alignment=TA_JUSTIFY, firstLineIndent=12, spaceAfter=6),
        "abs": ParagraphStyle("abs", fontName=font, fontSize=9.5, leading=13, alignment=TA_JUSTIFY, spaceAfter=6),
        "caption": ParagraphStyle("caption", fontName=font, fontSize=9, leading=11, alignment=TA_CENTER, spaceBefore=3, spaceAfter=10),
        "ref": ParagraphStyle("ref", fontName=font, fontSize=9, leading=11, leftIndent=12, firstLineIndent=-12, spaceAfter=3),
        "eq": ParagraphStyle("eq", fontName=font_i, fontSize=10, leading=13, alignment=TA_CENTER, spaceBefore=4, spaceAfter=4),
        "note": ParagraphStyle("note", fontName=font_i, fontSize=9, leading=12, alignment=TA_LEFT, spaceAfter=6),
        "hl": ParagraphStyle("hl", fontName=font, fontSize=9.5, leading=12, leftIndent=8, spaceAfter=2),
        "footer": ParagraphStyle("footer", fontName=font, fontSize=8, alignment=TA_CENTER),
    }


def P(text, style):
    return Paragraph(text, style)


def read_csv(name: str):
    with open(TAB / name, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def make_table(data, col_widths=None):
    sty = TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#666666")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
    )
    t = Table(data, colWidths=col_widths, hAlign="CENTER")
    t.setStyle(sty)
    return t


def fig(name, width=16 * cm):
    path = FIG / name
    return Image(str(path), width=width, height=width * 0.48 if "fig1" in name or "fig3" in name else width * 0.45)


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 8)
    canvas.drawCentredString(A4[0] / 2, 1.2 * cm, f"{doc.page}")
    canvas.drawString(2 * cm, A4[1] - 1.2 * cm, "Li — Regime-Conditional Adaptive World Models")
    canvas.restoreState()


def build():
    S = styles()
    story = []

    story.append(P("Manuscript draft for SCI submission (Elsevier-like formatting)", S["journal"]))
    story.append(P("Beyond Breadth–Stability–Honesty: Regime-Conditional Adaptive World Models for AI-Based Cryptocurrency Market Analysis", S["title"]))
    story.append(P("Guocong Li", S["author"]))
    story.append(P("Independent Researcher; Email: lmu151638@gmail.com", S["affil"]))
    story.append(P("Target journals: <i>Expert Systems with Applications</i> / <i>Information Sciences</i> / <i>Knowledge-Based Systems</i>", S["affil"]))

    story.append(P("<b>Highlights</b>", S["h2"]))
    for h in [
        "Diagnoses five structural limits of the first-generation WMI = B × U × H index.",
        "Proposes hierarchical breadth, continuous honesty, signal integrity, and consistency.",
        "Defines regime–task conditional compilation and a weighted-geometric ACWMI.",
        "Maps the theory onto EvoQuant with 43 domains, 13 audit bands, and mechanism engines.",
        "Shows factor models dominate scalar WMI for analysis-quality explanation (R² 0.484 vs 0.115).",
    ]:
        story.append(P("• " + h, S["hl"]))

    story.append(P("<b>Abstract</b>", S["h2"]))
    story.append(P(
        "Many AI-based market systems fail less because the predictor is weak than because the market world "
        "presented to the model is thin, stale, or dishonest. Prior work formalized this observation as a data "
        "world-model infrastructure and defined a World Model Index WMI<sub>t</sub>=B<sub>t</sub>×U<sub>t</sub>×H<sub>t</sub> "
        "along breadth, stability, and honesty. While useful, the product form is non-decomposable, honesty is often "
        "discrete, compilation is task-agnostic, and evidence remains flat. This paper develops a second-generation "
        "<b>Regime-Conditional Adaptive World Model (RCA-WM)</b>. We replace flat breadth with a hierarchy from 43 data "
        "domains through 13 audit bands and asset readiness; redefine honesty via exclusion and contamination rates; "
        "introduce signal integrity and cross-evidence consistency; and define a regime–task conditional compilation "
        "operator together with a weighted-geometric Adaptive Conditional World Model Index (ACWMI). Using the open "
        "EvoQuant implementation and a controlled Monte Carlo panel (N=2160 asset-day observations), factor-decomposed "
        "models explain analysis quality far better than scalar WMI (R²=0.484 vs 0.115), and ACWMI induces substantially "
        "more state-dependent abstention in crisis regimes. The contribution is to elevate market world modeling from a "
        "static product score to a conditional, auditable, and operationally degradable scientific object.",
        S["abs"],
    ))
    story.append(P("<b>Keywords:</b> AI market world model; cryptocurrency; data-centric AI; quality governance; point-in-time correctness; abstention", S["note"]))
    story.append(P("<b>JEL:</b> G10, G17, C55, C82, O33 &nbsp;&nbsp; <b>MSC:</b> 91G70, 68T05", S["note"]))

    # 1
    story.append(P("1. Introduction", S["h1"]))
    story.append(P(
        "In public narratives, failures of AI trading systems are often attributed to model capacity or prompt design. "
        "In live markets, the binding constraint is frequently epistemic: the agent does not observe a sufficiently broad, "
        "stable, and honest market world. Cryptocurrency markets amplify this problem because identical price paths can "
        "correspond to different structural states once exchange fragmentation, leverage crowding, funding distortions, "
        "options walls, unlock schedules, and macro liquidity are recognized.",
        S["body"],
    ))
    story.append(P(
        "Prior work on the EvoQuant project formalized a world-model-first agenda and defined WMI<sub>t</sub>=B<sub>t</sub>×U<sub>t</sub>×H<sub>t</sub>. "
        "Engineering counterparts include latest_* snapshots, quality gating, main/diagnostic view separation, and multi-band bundles. "
        "This first-generation object is valuable but insufficient for systems that already expose asset-level readiness matrices, "
        "mechanism engines, point-in-time reconstruction, and multi-level degradation. This paper therefore asks: "
        "<i>how should a market world model be compiled for AI under regime, task, and resource constraints, rather than merely made thicker?</i>",
        S["body"],
    ))
    story.append(P("1.1 Contributions", S["h2"]))
    story.append(P(
        "(i) Diagnostic: five formal limits of product-form WMI. (ii) Theoretical: RCA-WM with hierarchical breadth, continuous honesty, "
        "signal integrity S<sub>t</sub>, consistency C<sub>t</sub>, and conditional compilation Π<sub>t</sub><sup>(r,m)</sup>. "
        "(iii) Metric: weighted-geometric ACWMI. (iv) Systems mapping onto EvoQuant. (v) Project-grounded Monte Carlo / event-study evidence.",
        S["body"],
    ))

    # 2
    story.append(P("2. Related work", S["h1"]))
    story.append(P(
        "Asset pricing treats expected returns as conditional on an information set (Fama and French, 1993; Cochrane, 2005). "
        "Machine-learning asset pricing expands that set with high-dimensional characteristics (Gu et al., 2020; Kelly et al., 2019; Nagel, 2021), "
        "while multiple-testing critiques warn against naive feature expansion (Harvey et al., 2016). Measurement-error and robustness "
        "literatures emphasize decisions under noisy information worlds (Fuller, 1987; Carroll et al., 2006; Hansen and Sargent, 2008). "
        "Our object is not “more predictors,” but the governance and compilation of an asynchronous multi-source market world.",
        S["body"],
    ))

    # 3
    story.append(P("3. Limitations of first-generation WMI", S["h1"]))
    story.append(P(
        "Product collapse makes breadth improvements invisible when U or H is near zero. Discrete honesty discards exclusion/contamination intensities. "
        "Task- and regime-agnostic compilation uses the same weights in tranquil and crisis markets. Flat evidence assumptions understate the hierarchy "
        "from 43 domains to 13 audit bands and asset readiness. Finally, point-in-time leakage and degraded-mode honesty are operationally present but "
        "absent from the first-generation score.",
        S["body"],
    ))

    # 4 Theory
    story.append(P("4. Regime-Conditional Adaptive World Models", S["h1"]))
    story.append(P("4.1 Hierarchical breadth", S["h2"]))
    story.append(P(
        "Let D<sub>d,t</sub> denote data domains (D=43), E<sub>k,t</sub> audit bands (K=13), and A<sub>i,t</sub> asset readiness. "
        "Hierarchical breadth is the convex combination",
        S["body"],
    ))
    story.append(P("B<sub>t</sub><sup>hier</sup> = α<sub>1</sub> B<sub>t</sub><sup>domain</sup> + α<sub>2</sub> B<sub>t</sub><sup>band</sup> + α<sub>3</sub> B<sub>t</sub><sup>asset</sup>,", S["eq"]))
    story.append(P("with α<sub>1</sub>+α<sub>2</sub>+α<sub>3</sub>=1.", S["body"]))

    story.append(P("4.2 Continuous honesty, signal integrity, consistency", S["h2"]))
    story.append(P(
        "Continuous honesty rewards exclusion of non-AI-ready sources and penalizes main-view contamination:",
        S["body"],
    ))
    story.append(P("H<sub>t</sub><sup>cont</sup> = exp(−β<sub>1</sub> ρ<sub>t</sub><sup>cont</sup>) · (1 − β<sub>2</sub>(1 − ρ<sub>t</sub><sup>ex</sup>))<sub>+</sub>.", S["eq"]))
    story.append(P(
        "Signal integrity S<sub>t</sub> aggregates half-life, crowding, and surprise from mechanism engines (e.g., alpha-decay). "
        "Consistency C<sub>t</sub> measures pairwise directional agreement across available evidence bands.",
        S["body"],
    ))

    story.append(P("4.3 Conditional compilation and ACWMI", S["h2"]))
    story.append(P("For regime r and task m,", S["body"]))
    story.append(P("Π<sub>t</sub><sup>(r,m)</sup> = B<sub>t</sub><sup>(r,m)</sup> ∘ M<sub>t</sub><sup>(r,m)</sup> ∘ A<sub>t</sub> ∘ Ψ<sub>t</sub><sup>mech</sup>.", S["eq"]))
    story.append(P(
        "ACWMI is defined as a weighted geometric mean, keeping the index on a [0,1] scale while remaining decomposable in logs:",
        S["body"],
    ))
    story.append(P(
        "ACWMI<sub>t</sub><sup>(r,m)</sup> = exp( Σ<sub>x∈{B,U,H,S,C}</sub> γ<sub>x</sub>(r) log x<sub>t</sub> / Σ γ<sub>x</sub>(r) ).",
        S["eq"],
    ))
    story.append(P(
        "Crisis regimes raise γ<sub>H</sub> and γ<sub>C</sub>; trend regimes raise γ<sub>S</sub>. State-dependent abstention thresholds increase when ACWMI is low, "
        "consistency collapses, or the system enters degraded mode.",
        S["body"],
    ))

    # Figure 1-2
    story.append(KeepTogether([fig("fig1_architecture.png", 16.5 * cm), P("Fig. 1. Hierarchical evidence composition and conditional compilation in RCA-WM.", S["caption"])]))
    story.append(KeepTogether([fig("fig2_coverage_compare.png", 16.5 * cm), P("Fig. 2. Evidence coverage under thin, thick (Gen-1), and RCA-WM (Gen-2) worlds.", S["caption"])]))

    # 5 Systems
    story.append(P("5. Systems mapping to EvoQuant", S["h1"]))
    story.append(P(
        "The repository currently exposes 43 data-layer domains, 39 logic modules, and 13 audit bands. Production WMI is computed in "
        "<font face='Courier'>ai_market_context</font> as B×U×H, with U derived from pipeline-latency freshness and a default abstain suggestion when WMI&lt;0.2. "
        "Table 1 maps theoretical objects to concrete modules.",
        S["body"],
    ))
    map_rows = read_csv("table5_theory_implementation_map.csv")
    story.append(make_table(map_rows, col_widths=[3.2 * cm, 7.2 * cm, 4.2 * cm]))
    story.append(P("Table 1. Theory–implementation map between RCA-WM and EvoQuant.", S["caption"]))

    band_rows = read_csv("table1_evidence_bands.csv")
    # shorten for page
    short = [band_rows[0]] + [[r[0], r[1], r[2], r[3]] for r in band_rows[1:]]
    short[0] = ["Band", "Module", "Required", "Asset weight"]
    story.append(make_table(short, col_widths=[3.5 * cm, 4.5 * cm, 2.2 * cm, 2.5 * cm]))
    story.append(P("Table 2. Audit evidence bands and asset-readiness weights used by the system.", S["caption"]))

    # 6 Design
    story.append(P("6. Experimental design", S["h1"]))
    story.append(P(
        "We combine live code inventory statistics with a controlled Monte Carlo panel that calls the repository’s real WMI implementation "
        "for the first-generation benchmark. The panel uses 18 assets and 120 days (N=2160), Markov regime switches among "
        "{trend, range, crisis}, and source outages with probability 0.12 in crises and 0.03 otherwise. For each asset-day we construct "
        "B<sup>hier</sup>, U, H<sup>cont</sup>, S, C; compute production WMI; form ACWMI; and record analysis quality Q, explanation volatility EV, "
        "and unsupported-claim rate UCR.",
        S["body"],
    ))

    # 7 Results
    story.append(P("7. Results", S["h1"]))
    story.append(P("7.1 Regime heterogeneity", S["h2"]))
    story.append(P(
        "Table 3 shows that crisis states exhibit lower world-model scores and much higher ACWMI-based abstention (94.7%) than "
        "WMI-threshold abstention (1.4%). First-generation WMI therefore under-triggers refusal precisely when conflict is highest.",
        S["body"],
    ))
    reg = read_csv("table2_regime_summary.csv")
    # select columns
    header = ["regime", "N", "WMI", "ACWMI", "C", "S", "Q", "abstain_WMI", "abstain_AC"]
    body = []
    for r in reg[1:]:
        body.append([r[0], r[1], r[2], r[3], r[5], r[6], r[7], r[10], r[11]])
    story.append(make_table([header] + body, col_widths=[1.8*cm]+[1.6*cm]*8))
    story.append(P("Table 3. Regime-level means from the Monte Carlo panel.", S["caption"]))

    story.append(KeepTogether([fig("fig3_factor_paths.png", 16.2 * cm), P("Fig. 3. Time paths of WMI, ACWMI, quality, and constituent factors.", S["caption"])]))
    story.append(KeepTogether([fig("fig4_regime_box.png", 15.5 * cm), P("Fig. 4. Distribution of WMI and ACWMI across regimes.", S["caption"])]))

    story.append(P("7.2 Quality regressions", S["h2"]))
    story.append(P(
        "Standardized OLS fits (Table 4) show that scalar WMI yields R²=0.115. Factor decomposition raises R² to 0.484; "
        "ACWMI alone achieves 0.345; combining ACWMI with factors reaches 0.489. Honesty, signal integrity, and consistency "
        "dominate breadth/stability coefficients, confirming that second-generation objects carry incremental content.",
        S["body"],
    ))
    # Compact regression table from known results
    reg_tbl = [
        ["Variable", "Model A", "Model B", "Model C", "Model D"],
        ["WMI", "0.340", "", "", ""],
        ["B_hier", "", "0.084", "", "0.058"],
        ["U", "", "0.067", "", "0.041"],
        ["H_cont", "", "0.434", "", "0.394"],
        ["S", "", "0.381", "", "0.207"],
        ["C", "", "0.349", "", "0.261"],
        ["ACWMI", "", "", "0.587", "0.238"],
        ["R²", "0.115", "0.484", "0.345", "0.489"],
    ]
    story.append(make_table(reg_tbl, col_widths=[2.8*cm, 2.4*cm, 2.4*cm, 2.4*cm, 2.4*cm]))
    story.append(P("Table 4. Standardized regressions of analysis quality Q.", S["caption"]))
    story.append(KeepTogether([fig("fig5_quality_scatter.png", 16*cm), P("Fig. 5. Association between world-model indices and analysis quality.", S["caption"])]))

    story.append(P("7.3 Outages, Pareto frontier, and honesty incentives", S["h2"]))
    story.append(P(
        "Outages reduce Q by about 0.21–0.23 and raise unsupported claims (Table 5). ACWMI abstention approaches one under outages, "
        "whereas WMI remains comparatively insensitive. Figure 7 shows that ACWMI abstention policies dominate WMI thresholds on the "
        "abstain-rate versus supported-claim-accuracy frontier. Figure 8 shows that higher exclusion raises continuous honesty without "
        "collapsing ACWMI in the manner implied by naive product penalties.",
        S["body"],
    ))
    out = read_csv("table4_outage_event_study.csv")
    out_short = [["regime", "outage", "N", "Q", "UCR", "WMI", "ACWMI", "abstain_AC"]]
    for r in out[1:]:
        out_short.append([r[0], r[1], r[2], r[3], r[5], r[6], r[7], r[8]])
    story.append(make_table(out_short, col_widths=[1.8*cm]+[1.7*cm]*7))
    story.append(P("Table 5. Outage versus non-outage contrasts.", S["caption"]))

    story.append(KeepTogether([fig("fig6_event_study.png", 15.5*cm), P("Fig. 6. Event-time profile around source outages in crisis regimes.", S["caption"])]))
    story.append(KeepTogether([fig("fig7_pareto.png", 14.5*cm), P("Fig. 7. Pareto frontier of abstention versus supported-claim accuracy.", S["caption"])]))
    story.append(KeepTogether([fig("fig8_honesty_incentive.png", 15.5*cm), P("Fig. 8. Honesty incentive: exclusion improves H_cont without ACWMI collapse.", S["caption"])]))

    # 8 Discussion
    story.append(P("8. Discussion", S["h1"]))
    story.append(P(
        "The results support a shift from “thicken the world” to “compile the right world.” World-model evaluation should be multi-objective—"
        "prediction, explanation stability, calibration, auditability, mechanism coverage, and PIT non-leakage. Abstention is part of the "
        "world-model contract, not a post-hoc heuristic. Mechanism engines belong inside the compilation operator. Limitations remain: the "
        "panel is controlled rather than a full live backtest; regime exponents require estimation discipline; and mechanism engines can "
        "misclassify regimes, motivating second-order uncertainty gates.",
        S["body"],
    ))

    # 9 Conclusion
    story.append(P("9. Conclusion", S["h1"]))
    story.append(P(
        "This paper optimized the first-generation world-model index into a regime-conditional adaptive framework. By combining hierarchical "
        "breadth, continuous honesty, signal integrity, consistency, conditional compilation, and PIT/degradation semantics, ACWMI becomes a "
        "decomposable and operationally meaningful scientific object. In project-grounded experiments, factor models and ACWMI substantially "
        "outperform scalar WMI for analysis-quality explanation and induce crisis-aware abstention. For long-lived AI market systems, the scarce "
        "asset is not a prompt or a single model, but a stable, conditional, and auditable data world model.",
        S["body"],
    ))

    # Appendix / repro
    story.append(P("Appendix A. Reproducibility", S["h1"]))
    story.append(P(
        "Figures and tables are generated by <font face='Courier'>pdf/sci/run_paper_experiments.py</font>, which imports production WMI from "
        "<font face='Courier'>logic_layer.ai_market_context.service</font>. Related unit tests "
        "(ai_market_context, contagion_risk, alpha_decay, liquidation_cascade, asset_readiness) passed in the accompanying repository run (15/15). "
        "LaTeX source for journal submission is provided as <font face='Courier'>pdf/sci/main_acwmi_sci.tex</font> (elsarticle).",
        S["body"],
    ))

    story.append(P("References", S["h1"]))
    refs = [
        "Carroll, R.J., Ruppert, D., Stefanski, L.A., Crainiceanu, C.M., 2006. Measurement Error in Nonlinear Models. 2nd ed. Chapman and Hall/CRC.",
        "Cochrane, J.H., 2005. Asset Pricing. Revised ed. Princeton University Press.",
        "Fama, E.F., French, K.R., 1993. Common risk factors in the returns on stocks and bonds. Journal of Financial Economics 33, 3–56.",
        "Fuller, W.A., 1987. Measurement Error Models. Wiley.",
        "Gu, S., Kelly, B., Xiu, D., 2020. Empirical asset pricing via machine learning. Review of Financial Studies 33, 2223–2273.",
        "Hansen, L.P., Sargent, T.J., 2008. Robustness. Princeton University Press.",
        "Harvey, C.R., Liu, Y., Zhu, H., 2016. …and the cross-section of expected returns. Review of Financial Studies 29, 5–68.",
        "Kelly, B.T., Pruitt, S., Su, Y., 2019. Characteristics are covariances. Journal of Financial Economics 134, 501–524.",
        "Li, G., 2026. From “Model-First” to “World-Model-First”: A study of cryptocurrency data world model infrastructure for AI-based market analysis. Working paper.",
        "Liu, Y., Tsyvinski, A., Wu, X., 2022. Common risk factors in cryptocurrency. Journal of Finance 77, 1133–1177.",
        "Makarov, I., Schoar, A., 2020. Trading and arbitrage in cryptocurrency markets. Journal of Financial Economics 135, 293–319.",
        "Nagel, S., 2021. Machine Learning in Asset Pricing. Princeton University Press.",
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
        title="Beyond Breadth-Stability-Honesty: Regime-Conditional Adaptive World Models",
        author="Guocong Li",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print("Wrote", OUT_EN, OUT_EN.stat().st_size)
    # Keep a stable copy at pdf/ root for the manuscript package.
    OUT.write_bytes(OUT_EN.read_bytes())
    print("Wrote", OUT, OUT.stat().st_size)


if __name__ == "__main__":
    build()
