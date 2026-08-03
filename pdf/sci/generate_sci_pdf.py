#!/usr/bin/env python3
"""Render JF/RFS-oriented manuscript PDF from experiment tables/figures."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"
TAB = ROOT / "tables"
OUT_EN = Path(__file__).resolve().parent / "main_acwmi_sci.pdf"
OUT = ROOT / "main_cn_acwmi_sci.pdf"


def styles():
    font, font_b, font_i = "Times-Roman", "Times-Bold", "Times-Italic"
    return {
        "journal": ParagraphStyle("journal", fontName=font_i, fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#444"), spaceAfter=8),
        "title": ParagraphStyle("title", fontName=font_b, fontSize=13.5, leading=17, alignment=TA_CENTER, spaceAfter=10),
        "author": ParagraphStyle("author", fontName=font, fontSize=11, alignment=TA_CENTER, spaceAfter=2),
        "affil": ParagraphStyle("affil", fontName=font_i, fontSize=9, alignment=TA_CENTER, spaceAfter=10),
        "h1": ParagraphStyle("h1", fontName=font_b, fontSize=12, leading=15, spaceBefore=12, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=font_b, fontSize=11, leading=14, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", fontName=font, fontSize=10, leading=13.5, alignment=TA_JUSTIFY, firstLineIndent=14, spaceAfter=6),
        "abs": ParagraphStyle("abs", fontName=font, fontSize=9.5, leading=13, alignment=TA_JUSTIFY, spaceAfter=6),
        "caption": ParagraphStyle("caption", fontName=font, fontSize=9, leading=11, alignment=TA_CENTER, spaceBefore=3, spaceAfter=10),
        "ref": ParagraphStyle("ref", fontName=font, fontSize=9, leading=11, leftIndent=12, firstLineIndent=-12, spaceAfter=3),
        "eq": ParagraphStyle("eq", fontName=font_i, fontSize=10, leading=13, alignment=TA_CENTER, spaceBefore=4, spaceAfter=4),
        "note": ParagraphStyle("note", fontName=font_i, fontSize=9, leading=12, spaceAfter=6),
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


def fig(name, width=6.5 * inch, ratio=0.48):
    return Image(str(FIG / name), width=width, height=width * ratio)


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 8)
    canvas.drawString(1 * inch, letter[1] - 0.6 * inch, "Li — Compiling the Market Information Set")
    canvas.drawCentredString(letter[0] / 2, 0.6 * inch, str(doc.page))
    canvas.restoreState()


def build():
    S = styles()
    inv = json.loads((TAB / "table1_project_inventory.json").read_text())
    thr = inv.get("frozen_thresholds", {})
    story = []
    story.append(P("Draft targeted at Journal of Finance / Review of Financial Studies", S["journal"]))
    story.append(P(
        "Compiling the Market Information Set: World-Model Quality, Selective Prediction, "
        "and Economic Value in Cryptocurrency Markets",
        S["title"],
    ))
    story.append(P("Guocong Li", S["author"]))
    story.append(P("Independent Researcher; Email: lmu151638@gmail.com", S["affil"]))

    story.append(P("<b>Abstract</b>", S["h2"]))
    story.append(P(
        "Conditional asset pricing and machine-learning return prediction treat the investor’s information set as given. "
        "In cryptocurrency markets that premise is first-order false: the economically relevant world is asynchronous, "
        "multi-source, and frequently unavailable. This paper formalizes <i>information-set compilation</i> as an object of study. "
        "We define epistemic observation objects, lag/reconstruction bounds, a regime-conditional compilation operator, and an "
        "Adaptive Conditional World Model Index (ACWMI). Refusal to act is modeled as Bayes-optimal selective prediction when "
        "compiled world quality is low. Empirically, we construct a point-in-time panel on real daily returns for ten major "
        f"cryptocurrencies ({inv['start']} to {inv['end']}), freeze abstention thresholds in-sample, and evaluate out-of-sample "
        "economic value against strong baselines. Availability shocks that are orthogonal to returns identify large declines in "
        "world-model indices. Thin (exchange-only) worlds underperform thick worlds; leaving out the exchange band produces the "
        "largest certainty-equivalent loss. Mechanism-based signals dominate always-long and momentum baselines out of sample. "
        "An IS-frozen ACWMI gate is more conservative than ungated thick signals and does <b>not</b> dominate on certainty equivalent "
        "in this sample—a result we report rather than conceal. The contribution is a finance-native theory and identification "
        "protocol; a full JF/RFS test requires vintaged multi-band archives.",
        S["abs"],
    ))
    story.append(P("<b>Keywords:</b> information set; selective prediction; cryptocurrency; measurement error; abstention. &nbsp;&nbsp; <b>JEL:</b> G12, G14, C58, C55", S["note"]))

    story.append(P("1. Introduction", S["h1"]))
    story.append(P(
        "The central state variable in modern asset pricing is an information set. The literature’s discipline has focused on how "
        "that information is used—linear betas, nonlinear learners, multiple-testing controls—not on how it is compiled from "
        "asynchronous, quality-heterogeneous market evidence. Cryptocurrency markets make the compilation problem unavoidable: "
        "fragmented venues, leverage, options walls, unlocks, on-chain flows, and macro liquidity can map the same price path into "
        "incompatible economic states.",
        S["body"],
    ))
    story.append(P(
        "This paper does not propose another alpha factor. It asks how an investor-facing market world should be formalized as a "
        "compiled information set; how world-model quality can be measured in an honesty-compatible way; when refusal is Bayes-optimal; "
        "and whether compiled world quality has measurable OOS economic consequences. Empirically we use real Yahoo daily returns, "
        f"chronological IS/OOS freeze at {inv['is_oos_cut']}, and production EvoQuant calculators only as laboratory infrastructure.",
        S["body"],
    ))

    story.append(P("2. Theory (RCA-WM / ACWMI)", S["h1"]))
    story.append(P(
        "An epistemic observation is O<sub>j,t</sub>=(x,τ,q,g,r). Asynchronous lags induce a Lipschitz reconstruction bound with "
        "terms for delay, noise, and missingness. The compilation operator maps raw filters into AI-visible worlds. ACWMI is the "
        "regime-conditional geometric mean of hierarchical breadth, stability, continuous honesty, signal integrity, and consistency. "
        "Abstention is optimal when expected loss of every non-abstain action exceeds a world-dependent cost. Identification uses "
        "availability shocks O<sub>t</sub>→W<sub>t</sub>→A<sub>t</sub>, with market complexity as a confounder.",
        S["body"],
    ))
    story.append(P("ACWMI<sub>t</sub><sup>(r)</sup> = exp( Σ<sub>x</sub> γ<sub>x</sub>(r) log x<sub>t</sub> / Σ γ<sub>x</sub>(r) ).", S["eq"]))

    story.append(P("3. Empirical design", S["h1"]))
    story.append(P(
        f"Sample: {inv['n_assets']} assets, {inv['start']}–{inv['end']}, real Yahoo daily returns; signals use only pre-t history. "
        f"IS/OOS cut {inv['is_oos_cut']}. Frozen AC rule from IS Sharpe maximization with abstain rate in [5%,55%]: "
        f"ACWMI&lt;{thr.get('ac_thr', 0.55)} or C&lt;{thr.get('c_thr', 0.25)}; production WMI threshold 0.2 never tuned. "
        "Band readiness uses production weights with return-orthogonal Bernoulli availability shocks (p=0.08). This is a stepping-stone "
        "to full vintaged multi-band PIT via time_slice.",
        S["body"],
    ))

    story.append(P("4. Results", S["h1"]))
    story.append(P("4.1 Availability shocks identify world-quality variation", S["h2"]))
    story.append(P(
        "At event day 0, mean WMI falls from ~0.88 to 0.23 and ACWMI from ~0.58 to 0.44, while contemporaneous equal-weight returns "
        "remain near zero—supporting O<sub>t</sub>→W<sub>t</sub> without a mechanical return confound.",
        S["body"],
    ))
    story.append(KeepTogether([fig("fig5_quality_scatter.png", 6.3*inch, 0.48), P("Fig. 1. Event study around return-orthogonal availability shocks.", S["caption"])]))

    story.append(P("4.2 Out-of-sample economic value", S["h2"]))
    story.append(P(
        "Always-long and momentum lose money OOS. Thick ungated mechanism signals deliver Sharpe 1.26 and CE 0.40. Production WMI "
        "never binds. IS-frozen ACWMI abstains 21.7% and delivers Sharpe 0.58 / CE≈0. <b>We do not claim CE dominance for ACWMI in this sample</b>; "
        "gating is economically consequential but conservative relative to ungated thick signals.",
        S["body"],
    ))
    econ = read_csv("table_econ_oos.csv")
    story.append(make_table(econ, [1.7*inch] + [0.7*inch] * 7))
    story.append(P("Table 1. OOS economic value with IS-frozen thresholds.", S["caption"]))
    story.append(KeepTogether([fig("fig1_architecture.png", 6.4*inch, 0.48), P("Fig. 2. OOS cumulative wealth of selective strategies.", S["caption"])]))
    story.append(KeepTogether([fig("fig2_coverage_compare.png", 6.4*inch, 0.42), P("Fig. 3. OOS Sharpe and certainty equivalent by policy.", S["caption"])]))

    story.append(P("4.3 Thin vs thick and leave-one-band-out", S["h2"]))
    story.append(P(
        "Exchange-only thin worlds produce OOS Sharpe −0.24 and CE −0.19, while thick worlds are strongly positive. Dropping the "
        "exchange band produces the largest CE loss (−0.085); news and on-chain follow. Alternative data is not valuable in this window.",
        S["body"],
    ))
    tt = read_csv("table_thin_thick.csv")
    story.append(make_table(tt, [1.8*inch] + [0.75*inch] * 6))
    story.append(P("Table 2. Thin vs thick-ungated vs thick-gated worlds (OOS).", S["caption"]))
    lobo = read_csv("table_lobo.csv")
    story.append(make_table(lobo, [1.4*inch] + [0.9*inch] * 4))
    story.append(P("Table 3. Leave-one-band-out OOS CE changes.", S["caption"]))
    story.append(KeepTogether([fig("fig6_event_study.png", 5.8*inch, 0.48), P("Fig. 4. Thin vs thick-ungated vs thick-gated (OOS).", S["caption"])]))
    story.append(KeepTogether([fig("fig4_regime_box.png", 6.2*inch, 0.42), P("Fig. 5. Leave-one-band-out marginal CE.", S["caption"])]))

    story.append(P("4.4 Conditional signal value (qualification)", S["h2"]))
    story.append(P(
        "Sorting on ACWMI alone does not produce a clean monotonic collapse of signal IC in this OOS window (including the no-outage "
        "subsample). Low-quality states partly coincide with periods where short mechanism signals performed well. This qualifies the "
        "abstention motive and motivates regime×quality double-sorts and cleaner vintaged outages.",
        S["body"],
    ))
    cond = read_csv("table_conditional_ic.csv")
    story.append(make_table(cond, [0.9*inch, 0.9*inch] + [0.7*inch] * 6))
    story.append(P("Table 4. Conditional signal value by ACWMI tercile (OOS).", S["caption"]))
    story.append(KeepTogether([fig("fig8_honesty_incentive.png", 6.0*inch, 0.42), P("Fig. 6. IS vs OOS stability under frozen thresholds.", S["caption"])]))

    story.append(P("5. Path to JF/RFS", S["h1"]))
    story.append(P(
        "Remaining binding constraints: (i) multi-year vintaged multi-band archive with available_at semantics; (ii) logged collector/API "
        "outages as institutional O<sub>t</sub>; (iii) real leave-one-source MIG; (iv) analyst/LLM EAR–ECP on frozen bundles; "
        "(v) external validity beyond ten liquid cryptos. The accompanying system already exposes time_slice, readiness, WMI, and "
        "degradation machinery for that archive.",
        S["body"],
    ))

    story.append(P("6. Conclusion", S["h1"]))
    story.append(P(
        "Information-set compilation is a first-order asset-pricing object where evidence is asynchronous and intermittently unavailable. "
        "RCA-WM/ACWMI formalize that object. On real crypto returns with frozen thresholds, thick compiled worlds and mechanism signals "
        "matter, availability shocks identify world-quality variation, and band ablations are economically heterogeneous. Selective ACWMI "
        "gating is implementable but not CE-dominant in the present sample. Keep the theory and identification protocol; replace the "
        "constructed information-set layer with a full vintaged PIT archive.",
        S["body"],
    ))

    story.append(P("Appendix. Reproducibility", S["h1"]))
    story.append(P(
        "Returns: <font face='Courier'>pdf/data/crypto_daily_yahoo.csv</font>. Experiments: "
        "<font face='Courier'>pdf/sci/run_jf_experiments.py</font>. Thresholds: "
        "<font face='Courier'>pdf/sci/frozen_thresholds.json</font>.",
        S["body"],
    ))

    story.append(P("References", S["h1"]))
    for r in [
        "Carroll, R.J., et al., 2006. Measurement Error in Nonlinear Models. Chapman & Hall/CRC.",
        "Chow, C., 1957. IRE Trans. Electronic Computers 6, 247–254.",
        "Cochrane, J.H., 2005. Asset Pricing. Princeton.",
        "Fama, E.F., French, K.R., 1993. Journal of Financial Economics 33, 3–56.",
        "Fuller, W.A., 1987. Measurement Error Models. Wiley.",
        "Geifman, Y., El-Yaniv, R., 2017. NeurIPS.",
        "Gu, S., Kelly, B., Xiu, D., 2020. Review of Financial Studies 33, 2223–2273.",
        "Hansen, L.P., Sargent, T.J., 2008. Robustness. Princeton.",
        "Harvey, C.R., Liu, Y., Zhu, H., 2016. Review of Financial Studies 29, 5–68.",
        "Kelly, B.T., Pruitt, S., Su, Y., 2019. Journal of Financial Economics 134, 501–524.",
        "Liu, Y., Tsyvinski, A., Wu, X., 2022. Journal of Finance 77, 1133–1177.",
        "Makarov, I., Schoar, A., 2020. Journal of Financial Economics 135, 293–319.",
        "Nagel, S., 2021. Machine Learning in Asset Pricing. Princeton.",
    ]:
        story.append(P(r, S["ref"]))

    doc = SimpleDocTemplate(
        str(OUT_EN), pagesize=letter,
        leftMargin=1.0*inch, rightMargin=1.0*inch, topMargin=0.85*inch, bottomMargin=0.85*inch,
        title="Compiling the Market Information Set",
        author="Guocong Li",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    OUT.write_bytes(OUT_EN.read_bytes())
    print("Wrote", OUT_EN, OUT_EN.stat().st_size)


if __name__ == "__main__":
    build()
