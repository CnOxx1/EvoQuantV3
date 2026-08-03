#!/usr/bin/env python3
"""Render theory-first SCI PDF; EvoQuant used only as empirical validation."""

from __future__ import annotations

import csv
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"
TAB = ROOT / "tables"
OUT_EN = Path(__file__).resolve().parent / "main_acwmi_sci.pdf"
OUT = ROOT / "main_cn_acwmi_sci.pdf"


def styles():
    font, font_b, font_i = "Times-Roman", "Times-Bold", "Times-Italic"
    return {
        "journal": ParagraphStyle("journal", fontName=font_i, fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#444"), spaceAfter=8),
        "title": ParagraphStyle("title", fontName=font_b, fontSize=13.2, leading=17, alignment=TA_CENTER, spaceAfter=10),
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
    canvas.drawString(2 * cm, A4[1] - 1.2 * cm, "Li — Regime-Conditional Adaptive World Models")
    canvas.drawCentredString(A4[0] / 2, 1.2 * cm, str(doc.page))
    canvas.restoreState()


def build():
    S = styles()
    story = []
    story.append(P("SCI manuscript draft — theory first; EvoQuant as empirical validation only", S["journal"]))
    story.append(P(
        "Regime-Conditional Adaptive World Models for AI Cryptocurrency Market Analysis: "
        "Theory and Empirical Validation on EvoQuant",
        S["title"],
    ))
    story.append(P("Guocong Li", S["author"]))
    story.append(P("Independent Researcher; Email: lmu151638@gmail.com", S["affil"]))
    story.append(P("Suggested venues: <i>Expert Systems with Applications</i> / <i>Information Sciences</i> / <i>Knowledge-Based Systems</i>", S["affil"]))

    story.append(P("<b>Highlights</b>", S["h2"]))
    for h in [
        "Proposes RCA-WM: a regime-conditional theory of AI market world-model compilation.",
        "Defines ACWMI with hierarchical breadth, continuous honesty, signal integrity, and consistency.",
        "Makes degradation-aware abstention part of the world-model contract.",
        "Validates the theory on EvoQuant (43 domains / 13 bands / 39 logic modules).",
        "Cascade/crisis F1 = 0.895 / 0.793; crisis unsafe actions fall from 81% to 0 under AC policy.",
    ]:
        story.append(P("• " + h, S["hl"]))

    story.append(P("<b>Abstract</b>", S["h2"]))
    story.append(P(
        "AI-based market analysis often fails not because predictors lack capacity, but because the market world presented to "
        "the model is incomplete, stale, or silently contaminated. This paper proposes a <b>theory</b> of Regime-Conditional "
        "Adaptive World Models (RCA-WM) for AI market analysis. We define a compilation operator that maps asynchronous "
        "multi-source observations into AI-visible world objects, and introduce an Adaptive Conditional World Model Index "
        "(ACWMI) based on hierarchical breadth, stability, continuous honesty, signal integrity, and cross-evidence consistency. "
        "Regime-dependent weights and degradation-aware abstention make refusal part of the world-model contract rather than a "
        "post-hoc heuristic. To validate the theory, we instantiate and stress-test it on <b>EvoQuant</b>, an open cryptocurrency "
        "world-model system with 43 data domains, 13 audit bands, 39 logic modules, and a production baseline index "
        "WMI=B×U×H. Using EvoQuant calculators on a 1800 asset-day panel with planted structural events, cascade and crisis "
        "detection attain F1 scores of 0.895 and 0.793, coarse regime match reaches 71.6%, and an ACWMI-aware abstention policy "
        "reduces unsafe crisis actions from 81% under the baseline WMI threshold to 0. The theoretical contribution is RCA-WM/ACWMI; "
        "EvoQuant serves as project-level empirical proof, not as the source of the theory.",
        S["abs"],
    ))
    story.append(P("<b>Keywords:</b> AI market world model; regime-conditional compilation; quality governance; selective prediction; cryptocurrency; data-centric AI", S["note"]))

    story.append(P("1. Introduction", S["h1"]))
    story.append(P(
        "Public discussion of AI trading typically starts from models. In live markets, a prior constraint often binds first: "
        "whether the agent is shown a market world that is sufficiently broad, stable, and honest. In cryptocurrency markets the "
        "same price path can correspond to incompatible states once exchange fragmentation, leverage crowding, funding distortions, "
        "options walls, unlock pressure, and macro liquidity are recognized.",
        S["body"],
    ))
    story.append(P(
        "We reverse the usual order of exposition. This paper does <b>not</b> start from a software inventory and then inductively "
        "“discover” a theory. It proposes a general theoretical object—a Regime-Conditional Adaptive World Model (RCA-WM)—and only "
        "afterwards validates that theory on a concrete system. Research questions: (i) how should an AI-consumable market world be "
        "compiled from asynchronous multi-source observations? (ii) how can world-model quality be measured in a decomposable, "
        "regime-sensitive, honesty-compatible way? (iii) when should an AI abstain because the compiled world is untrustworthy? "
        "(iv) can these claims be supported by a runnable project implementation?",
        S["body"],
    ))
    story.append(P(
        "Contributions: theory (RCA-WM compilation operator); metric (ACWMI); decision rule (degradation-aware abstention); "
        "empirical proof on EvoQuant (43 domains / 13 bands / 39 logic modules / baseline WMI); and reproducible validation scripts. "
        "The logical order is theory first, project validation second.",
        S["body"],
    ))

    story.append(P("2. Related work", S["h1"]))
    story.append(P(
        "Conditional asset pricing (Fama and French, 1993; Cochrane, 2005), machine-learning pricing (Gu et al., 2020; Kelly et al., 2019; "
        "Nagel, 2021), multiple-testing critiques (Harvey et al., 2016), measurement-error/robustness theories (Fuller, 1987; Carroll et al., 2006; "
        "Hansen and Sargent, 2008), selective prediction (Chow, 1957; Geifman and El-Yaniv, 2017), data-centric AI (Zha et al., 2023), and "
        "crypto microstructure (Makarov and Schoar, 2020; Liu et al., 2022) motivate the problem. Relative to feature-expansion papers, our "
        "object is compilation and governance of an asynchronous multi-source market world. Relative to conceptual essays, we insist on "
        "empirical proof on a runnable system. The theory is proposed first; the system is the testbed.",
        S["body"],
    ))

    story.append(P("3. Theoretical framework: RCA-WM", S["h1"]))
    story.append(P("3.1 Latent state, observations, and compilation", S["h2"]))
    story.append(P(
        "Let S<sub>t</sub> be the latent market state and X<sub>j,t</sub>=h<sub>j</sub>(S<sub>t</sub>)+ν<sub>j,t</sub> the observations. "
        "Model-first pipelines jump to ŷ<sub>t+1</sub>=f(X<sub>1,t</sub>,…,X<sub>J,t</sub>). RCA-WM inserts an explicit world-compilation stage "
        "W<sub>t</sub>=G({X<sub>j,τ</sub>}, Q<sub>t</sub>, R<sub>t</sub>, A<sub>t</sub>), where Q, R, A denote quality marks, AI-readiness gates, "
        "and temporal alignment. The AI consumes W<sub>t</sub>, not ungated raw observations.",
        S["body"],
    ))
    story.append(P("3.2 Quality factors", S["h2"]))
    story.append(P(
        "Hierarchical breadth aggregates domain/band/asset readiness: "
        "B<sub>t</sub><sup>hier</sup>=α<sub>1</sub>B<sup>domain</sup>+α<sub>2</sub>B<sup>band</sup>+α<sub>3</sub>B<sup>asset</sup>. "
        "Stability U penalizes staleness. Continuous honesty rewards exclusion and penalizes contamination: "
        "H<sup>cont</sup>=exp(−β<sub>1</sub>ρ<sup>cont</sup>)·(1−β<sub>2</sub>(1−ρ<sup>ex</sup>))<sub>+</sub>. "
        "Signal integrity S aggregates half-life, crowding, and surprise; consistency C measures cross-channel directional agreement.",
        S["body"],
    ))
    story.append(P("3.3 Conditional compilation, ACWMI, and abstention", S["h2"]))
    story.append(P("Π<sub>t</sub><sup>(r,m)</sup> = B<sub>t</sub><sup>(r,m)</sup> ∘ M<sub>t</sub><sup>(r,m)</sup> ∘ A<sub>t</sub> ∘ Ψ<sub>t</sub><sup>mech</sup>.", S["eq"]))
    story.append(P(
        "ACWMI is the weighted geometric mean of {B,U,H,S,C} with regime exponents γ(r). Crisis raises honesty/consistency weights; "
        "trend raises signal-integrity weights. Abstention thresholds rise when ACWMI is low, consistency collapses, or degradation "
        "leaves NORMAL—refusal is part of the theory, not an engineering afterthought.",
        S["body"],
    ))
    story.append(P(
        "ACWMI<sub>t</sub><sup>(r)</sup> = exp( Σ<sub>x∈{B,U,H,S,C}</sub> γ<sub>x</sub>(r) log x<sub>t</sub> / Σ γ<sub>x</sub>(r) ).",
        S["eq"],
    ))

    story.append(P("4. Empirical validation: EvoQuant as proof system", S["h1"]))
    story.append(P(
        "Theory requires a falsifiable substrate. We use EvoQuant as the <b>empirical proof system—not as the origin of the theory</b>. "
        "EvoQuant implements the objects RCA-WM demands: multi-domain collection, latest_* snapshots, quality gating, mechanism engines, "
        "degradation control, and a production baseline WMI=B×U×H with abstention when WMI&lt;0.2. Table 1 and Figures 1–2 report the "
        "validation inventory. Synthetic paths are only inputs; every mechanism score is computed by importing EvoQuant calculators; "
        "planted labels are independent of ACWMI.",
        S["body"],
    ))
    story.append(KeepTogether([fig("fig1_architecture.png", 16.3*cm, 0.50), P("Fig. 1. Theoretical RCA-WM compilation chain, instantiated for validation in EvoQuant.", S["caption"])]))
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
    story.append(P("Table 1. EvoQuant inventory used as empirical proof of RCA-WM (not as theory source).", S["caption"]))
    story.append(KeepTogether([fig("fig2_coverage_compare.png", 16*cm, 0.42), P("Fig. 2. Validation-system inventory and band weights for hierarchical breadth.", S["caption"])]))

    map_rows = [
        ["Theory object", "EvoQuant instantiation", "Role"],
        ["Compilation Π", "data_layer + logic_pipeline + context", "Proof of W_t"],
        ["B_hier", "43 domains / 13 bands / asset readiness", "Breadth factor"],
        ["U", "pipeline_latency freshness", "Stability factor"],
        ["H_cont", "quality flags + exclusion/contamination", "Honesty factor"],
        ["S", "alpha_decay half-life/crowding/surprise", "Signal integrity"],
        ["C", "cross-engine directional agreement", "Consistency"],
        ["Psi_mech", "regime/cascade/contagion/flow/vol", "Mechanism layer"],
        ["Baseline WMI", "production B×U×H", "Competing index"],
    ]
    story.append(make_table(map_rows, [3.4*cm, 7.0*cm, 3.2*cm]))
    story.append(P("Table 2. Theory-to-proof mapping: RCA-WM objects and EvoQuant instantiations.", S["caption"]))

    story.append(P("5. Results", S["h1"]))
    story.append(P("5.1 Mechanism layer supports the theory", S["h2"]))
    story.append(P(
        "If RCA-WM is right that mechanism engines belong inside Ψ<sup>mech</sup>, project calculators should detect planted stress. "
        "Table 3 confirms cascade F1=0.895, crisis F1=0.793, and regime-match accuracy 71.6%.",
        S["body"],
    ))
    det = read_csv("table3_detection_metrics.csv")
    story.append(make_table(det, [3.5*cm, 2.2*cm, 2.2*cm, 2.0*cm, 1.8*cm, 2.2*cm]))
    story.append(P("Table 3. Detection performance on planted structural events.", S["caption"]))

    story.append(P("5.2 Baseline WMI versus proposed ACWMI and abstention", S["h2"]))
    story.append(P(
        "The key theoretical prediction is not that ACWMI is always larger, but that it supports better regime-conditional refusal. "
        "Under planted crisis, baseline WMI still permits action in 81% of cases, while the AC policy reduces unsafe actions to 0. "
        "In calm range regimes both policies rarely abstain (~4.7%).",
        S["body"],
    ))
    reg = read_csv("table2_regime_summary.csv")
    reg_short = [["regime", "N", "WMI", "ACWMI", "abstain_WMI", "abstain_AC", "unsafe_WMI", "unsafe_AC"]]
    for r in reg[1:]:
        reg_short.append([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]])
    story.append(make_table(reg_short, [1.7*cm] + [1.7*cm] * 7))
    story.append(P("Table 4. Regime-level scores and safety under baseline vs AC abstention.", S["caption"]))
    story.append(KeepTogether([fig("fig3_factor_paths.png", 16*cm, 0.55), P("Fig. 3. Baseline WMI versus proposed ACWMI and mechanism outputs.", S["caption"])]))
    story.append(KeepTogether([fig("fig4_regime_box.png", 15.5*cm, 0.42), P("Fig. 4. Regime heterogeneity of baseline WMI and proposed ACWMI.", S["caption"])]))
    story.append(KeepTogether([fig("fig5_quality_scatter.png", 16*cm, 0.42), P("Fig. 5. Mechanism outputs and unsafe-action rates under the two policies.", S["caption"])]))

    story.append(P("5.3 Outages, Pareto frontier, and degradation", S["h2"]))
    out = read_csv("table4_outage_event_study.csv")
    out_short = [["regime", "outage", "N", "WMI", "ACWMI", "cascade_p", "abstain_AC", "unsafe_WMI"]]
    for r in out[1:]:
        out_short.append([r[0], r[1], r[2], r[3], r[4], r[5], r[7], r[9]])
    story.append(make_table(out_short, [1.6*cm]*8))
    story.append(P("Table 5. Outage contrasts supporting degradation-aware refusal.", S["caption"]))
    story.append(KeepTogether([fig("fig6_event_study.png", 15.2*cm, 0.42), P("Fig. 6. Outage event profile in the validation panel.", S["caption"])]))
    story.append(KeepTogether([fig("fig7_pareto.png", 14.5*cm, 0.48), P("Fig. 7. Abstention–safety Pareto frontier implied by the proposed rule.", S["caption"])]))
    deg = read_csv("table5_degradation_matrix.csv")
    story.append(make_table(deg, [4.2*cm, 2.0*cm, 2.0*cm, 2.0*cm, 2.2*cm]))
    story.append(P("Table 6. Module executability under degradation levels (1=allowed).", S["caption"]))
    story.append(KeepTogether([fig("fig8_honesty_incentive.png", 15.2*cm, 0.42), P("Fig. 8. Degradation levels versus breadth, honesty, and world-model scores.", S["caption"])]))

    story.append(P("6. Discussion", S["h1"]))
    story.append(P(
        "The evidence supports the theory-first claim structure. RCA-WM predicts that mechanism integrity belongs in world-model quality, "
        "honesty must be continuous and exclusion-compatible, and abstention should be regime- and degradation-dependent. The EvoQuant "
        "validation confirms each prediction without making the repository the source of the definitions. Limitations: controlled input "
        "paths are not yet a full live PIT backtest; γ(r) is pre-specified; external validity beyond crypto remains open.",
        S["body"],
    ))

    story.append(P("7. Conclusion", S["h1"]))
    story.append(P(
        "This paper proposed Regime-Conditional Adaptive World Models and the ACWMI quality index for AI market analysis. The theory "
        "specifies how asynchronous evidence should be compiled, how world-model quality should be decomposed, and when an AI should "
        "refuse to judge. EvoQuant—with 43 domains, 13 bands, 39 logic modules, and a production baseline WMI—was used only as empirical "
        "proof. On that proof system, mechanism detection is strong and AC-aware abstention removes crisis-time unsafe actions that the "
        "baseline WMI threshold permits. The scientific order is preserved: theory first, project validation second.",
        S["body"],
    ))

    story.append(P("Appendix A. Reproducibility", S["h1"]))
    story.append(P(
        "Validation experiments: <font face='Courier'>pdf/sci/run_paper_experiments.py</font>. PDF build: "
        "<font face='Courier'>pdf/sci/generate_sci_pdf.py</font>. LaTeX: <font face='Courier'>pdf/sci/main_acwmi_sci.tex</font>. "
        "Scripts import production calculators from the EvoQuant repository used as proof system.",
        S["body"],
    ))

    story.append(P("References", S["h1"]))
    for r in [
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
    ]:
        story.append(P(r, S["ref"]))

    doc = SimpleDocTemplate(
        str(OUT_EN), pagesize=A4,
        leftMargin=2.0*cm, rightMargin=2.0*cm, topMargin=1.8*cm, bottomMargin=1.8*cm,
        title="Regime-Conditional Adaptive World Models: Theory and Validation",
        author="Guocong Li",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    OUT.write_bytes(OUT_EN.read_bytes())
    print("Wrote", OUT_EN, OUT_EN.stat().st_size)


if __name__ == "__main__":
    build()
