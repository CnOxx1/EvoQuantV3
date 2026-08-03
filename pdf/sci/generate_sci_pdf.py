#!/usr/bin/env python3
"""Render JF/RFS PDF from real multi-band PIT experiment outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"
TAB = ROOT / "tables"
DATA = ROOT / "data"
OUT_EN = Path(__file__).resolve().parent / "main_acwmi_sci.pdf"
CN = ROOT / "cn"
OUT_CN_MIRROR = CN / "main_cn_acwmi_sci.pdf"
OUT_LEGACY = ROOT / "main_cn_acwmi_sci.pdf"  # legacy path until pdf/cn package lands


def styles():
    font, font_b, font_i = "Times-Roman", "Times-Bold", "Times-Italic"
    return {
        "journal": ParagraphStyle("journal", fontName=font_i, fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#444"), spaceAfter=8),
        "title": ParagraphStyle("title", fontName=font_b, fontSize=13.2, leading=16.5, alignment=TA_CENTER, spaceAfter=10),
        "author": ParagraphStyle("author", fontName=font, fontSize=11, alignment=TA_CENTER, spaceAfter=2),
        "affil": ParagraphStyle("affil", fontName=font_i, fontSize=9, alignment=TA_CENTER, spaceAfter=10),
        "h1": ParagraphStyle("h1", fontName=font_b, fontSize=12, leading=15, spaceBefore=12, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=font_b, fontSize=11, leading=14, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", fontName=font, fontSize=10, leading=13.5, alignment=TA_JUSTIFY, firstLineIndent=14, spaceAfter=6),
        "abs": ParagraphStyle("abs", fontName=font, fontSize=9.5, leading=13, alignment=TA_JUSTIFY, spaceAfter=6),
        "caption": ParagraphStyle("caption", fontName=font, fontSize=9, leading=11, alignment=TA_CENTER, spaceBefore=3, spaceAfter=10),
        "ref": ParagraphStyle("ref", fontName=font, fontSize=9, leading=11, leftIndent=12, firstLineIndent=-12, spaceAfter=3),
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
    canvas.drawString(1 * inch, letter[1] - 0.6 * inch, "Li — Compiling the Market Information Set (Real PIT)")
    canvas.drawCentredString(letter[0] / 2, 0.6 * inch, str(doc.page))
    canvas.restoreState()


def build():
    S = styles()
    inv = json.loads((TAB / "table1_project_inventory.json").read_text())
    arch = json.loads((DATA / "archive_inventory.json").read_text())
    pit = inv.get("pit", {})
    thr = inv.get("frozen_thresholds", {})
    story = []
    story.append(P("JF/RFS-oriented draft — real multi-band PIT archive", S["journal"]))
    story.append(P(
        "Compiling the Market Information Set: World-Model Quality, Selective Prediction, "
        "and Economic Value in Cryptocurrency Markets",
        S["title"],
    ))
    story.append(P("Guocong Li", S["author"]))
    story.append(P("Independent Researcher; Email: lmu151638@gmail.com", S["affil"]))

    story.append(P("<b>Abstract</b>", S["h2"]))
    story.append(P(
        "Conditional asset pricing treats the investor’s information set as given. In cryptocurrency markets that premise fails: "
        "evidence is asynchronous, multi-source, and intermittently unavailable. This paper formalizes information-set compilation "
        "and measures world-model quality with ACWMI. Empirically, we populate a real multi-band archive (OKX exchange bars, macro "
        "vintages, alternative series, plus thinner news/on-chain/options/tokenomics snapshots) and construct a "
        f"{pit.get('n_days', 400)}-day point-in-time panel ({pit.get('n_rows', 4000)} asset-days) aligned to Yahoo returns. "
        "Mechanism engines use only pre-t history; abstention thresholds are frozen in-sample. Out of sample, thick real PIT worlds "
        "dominate exchange-only thin worlds (CE 0.47 vs −0.01). Leave-one-band-out on durable bands shows large CE losses from dropping "
        "macro (−0.53), alternative (−0.53), or exchange (−0.34). An IS-frozen ACWMI gate remains implementable (Sharpe 0.90, CE 0.20) "
        "but does not dominate ungated thick signals on CE. The production WMI&lt;0.2 rule is mis-scaled for sparse archives (100% abstention). "
        "Contribution: finance-native compilation theory plus a reproducible PIT identification protocol on a live multi-band laboratory.",
        S["abs"],
    ))
    story.append(P("<b>Keywords:</b> information set; selective prediction; cryptocurrency; point-in-time; measurement error. &nbsp; <b>JEL:</b> G12, G14, C58, C55", S["note"]))

    story.append(P("1. Introduction", S["h1"]))
    story.append(P(
        "Asset pricing conditions on an information set I<sub>t</sub>. The literature’s discipline has focused on how I<sub>t</sub> is used, "
        "not how it is compiled from asynchronous evidence. This paper restores the World-Model-First / RCA-WM formal objects "
        "(definitions, lag bounds, compilation operator, ECP/MIG, DAG, abstention, ACWMI, EAR/UCR/EV), then instantiates them on a "
        "real multi-band PIT archive with frozen thresholds and leave-one-band-out identification. EvoQuant is the empirical laboratory, "
        "not the source of the theory. Formal LaTeX source with displayed equations: pdf/sci/main_acwmi_sci.tex; Chinese theory: pdf/cn/.",
        S["body"],
    ))

    story.append(P("2. Theory (restored from original paper)", S["h1"]))
    story.append(P(
        "<b>2.1 WMI triad.</b> Breadth, stability, and honesty:",
        S["body"],
    ))
    story.append(P(
        "B<sub>t</sub> = (1/K) Σ<sub>k</sub> a<sub>k,t</sub>, &nbsp; "
        "U<sub>t</sub> = exp(−Σ<sub>j</sub> ω<sub>j</sub> d<sub>j,t</sub>), &nbsp; "
        "H<sub>t</sub> = 1 − (1/J) Σ<sub>j</sub> m<sub>j,t</sub>, &nbsp; "
        "WMI<sub>t</sub> = B<sub>t</sub> × U<sub>t</sub> × H<sub>t</sub>.",
        S["note"],
    ))
    story.append(P(
        "Hierarchical breadth and continuous honesty used in the PIT panel: "
        "B<sup>hier</sup><sub>t</sub> = 0.25 B<sup>dom</sup><sub>t</sub> + 0.35 B<sup>band</sup><sub>t</sub> + 0.40 B<sup>asset</sup><sub>t</sub>; "
        "H<sup>cont</sup><sub>t</sub> = exp(−2c<sub>t</sub>) max(0, 1 − 0.5(1−e<sub>t</sub>)).",
        S["body"],
    ))
    story.append(P(
        "<b>2.2 Epistemic observations.</b> "
        "O<sub>j,t</sub> = (x<sub>j,t</sub>, τ<sub>j,t</sub>, q<sub>j,t</sub>, g<sub>j,t</sub>, r<sub>j,t</sub>) "
        "carries value, time, quality, gate, and role — not a bare feature.",
        S["body"],
    ))
    story.append(P(
        "<b>2.3 Lag bound.</b> With lagged observation X<sup>obs</sup><sub>j,t</sub> = h<sub>j</sub>(S<sub>t−ℓ</sub>) + ν<sub>j,t</sub> "
        "and Lipschitz h<sub>j</sub>, reconstruction error decomposes into delay, noise, and missingness terms "
        "(latest_* / TTL / is_ready_for_ai target these terms).",
        S["body"],
    ))
    story.append(P(
        "<b>2.4 Compilation operator.</b> "
        "F<sup>raw</sup><sub>t</sub> = σ({X<sup>obs</sup><sub>j,τ</sub>}), "
        "F<sup>AI</sup><sub>t</sub> = σ(W<sup>AI</sup><sub>t</sub>, D<sub>t</sub>), "
        "Π<sub>t</sub> = B<sub>t</sub> ∘ M<sub>t</sub> ∘ A<sub>t</sub>, "
        "W<sup>AI</sup><sub>t</sub> = Π<sub>t</sub>(F<sup>raw</sup><sub>t</sub>).",
        S["body"],
    ))
    story.append(P(
        "<b>2.5 ECP, MIG, DAG.</b> "
        "ECP<sub>t</sub> = 1{conf<sub>t</sub> &gt; c̄} 1{WMI<sub>t</sub> &lt; w}; "
        "MIG<sup>(m)</sup><sub>k,t</sub> = I(R<sup>(m)</sup><sub>t</sub>; E<sub>k,t</sub> | I<sup>(−k)</sup><sub>t</sub>); "
        "identification DAG: O<sub>t</sub> → W<sub>t</sub> → A<sub>t</sub> (with M<sub>t</sub>, C<sub>t</sub> confounders).",
        S["body"],
    ))
    story.append(P(
        "<b>2.6 Bayesian abstention.</b> "
        "a*<sub>t</sub> = arg min<sub>a</sub> E[ℓ(a,R<sub>t</sub>) | W<sub>t</sub>]; abstain when every non-abstain action "
        "has expected loss above c<sub>abs</sub>(W<sub>t</sub>).",
        S["body"],
    ))
    story.append(P(
        "<b>2.7 ACWMI and explanation metrics.</b> "
        "ACWMI<sub>t</sub> = exp( Σ γ<sub>i</sub>(r<sub>t</sub>) log x<sub>i,t</sub> / Σ γ<sub>i</sub> ) with "
        "x = (B<sup>hier</sup>, U, H<sup>cont</sup>, S, C). "
        "EAR<sub>t</sub> = (# evidence-bound claims)/(# claims), UCR<sub>t</sub> = 1 − EAR<sub>t</sub>, "
        "EV<sub>t</sub> = d(Φ<sub>t</sub>, Φ<sub>t−1</sub>) / (1 + d(W<sub>t</sub>, W<sub>t−1</sub>)).",
        S["body"],
    ))
    story.append(P(
        "<i>Note on length:</i> a five-page empirics-only sketch is not a JF/RFS submission. "
        "The displayed-equation theory lives in main_acwmi_sci.tex; this PDF keeps the formal core readable while reporting real-PIT results.",
        S["note"],
    ))

    story.append(P("3. Real multi-band PIT archive", S["h1"]))
    story.append(P(
        f"Exchange (OKX): ~{arch['exchange']['klines']} klines/merged bars, daily {arch['exchange']['range_1d'][0]}→{arch['exchange']['range_1d'][1]}. "
        f"Macro: {arch['market']['macro_timeseries']} vintaged points. Alternative: {arch['market']['alternative_timeseries']} points. "
        f"News/on-chain/options/tokenomics populated but mostly right-censored to collection day. "
        f"PIT panel: {pit.get('start')}→{pit.get('end')}, {pit.get('n_rows')} rows. "
        "time_slice historically resolves klines; analytics snapshots remain sparse, so multi-band PIT uses raw history tables "
        "(build_pit_archive.py) while time_slice provides logic-domain probes.",
        S["body"],
    ))

    story.append(P("4. Design", S["h1"]))
    story.append(P(
        f"IS/OOS cut {inv.get('is_oos_cut')}. Frozen AC rule: ACWMI&lt;{thr.get('ac_thr', 0.35)} or C&lt;{thr.get('c_thr', 0.35)}. "
        "Production WMI threshold 0.2 never tuned. Engines use only pre-t returns. Durable LOBO bands: exchange, macro, alternative.",
        S["body"],
    ))

    story.append(P("5. Results", S["h1"]))
    story.append(P("5.1 Thick real PIT dominates thin", S["h2"]))
    story.append(P(
        "Exchange-only thin worlds deliver OOS Sharpe ≈ 0 and CE −0.01. Thick real PIT worlds deliver Sharpe 1.40 and CE 0.47. "
        "IS-frozen AC gating keeps Sharpe 0.90 / CE 0.20 while abstaining 29.7%.",
        S["body"],
    ))
    tt = read_csv("table_thin_thick.csv")
    story.append(make_table(tt, [2.4*inch] + [0.65*inch] * 6))
    story.append(P("Table 1. Thin vs thick on the real PIT archive (OOS).", S["caption"]))
    story.append(KeepTogether([fig("fig6_event_study.png", 5.8*inch, 0.48), P("Fig. 1. Thin vs thick-gated worlds (real PIT).", S["caption"])]))

    story.append(P("5.2 Leave-one-band-out identification", S["h2"]))
    story.append(P(
        "Dropping durable bands destroys OOS CE: macro −0.53, alternative −0.53, exchange −0.34. Thickness has direct economic MIG content.",
        S["body"],
    ))
    lobo = read_csv("table_lobo.csv")
    story.append(make_table(lobo, [1.5*inch] + [1.0*inch] * 4))
    story.append(P("Table 2. Leave-one-band-out on durable PIT bands.", S["caption"]))
    story.append(KeepTogether([fig("fig4_regime_box.png", 6.2*inch, 0.42), P("Fig. 2. LOBO marginal CE on durable bands.", S["caption"])]))

    story.append(P("5.3 OOS policy horse-race", S["h2"]))
    story.append(P(
        "Always-long loses; momentum is near zero; thick ungated mechanism signals win on CE. IS-frozen ACWMI is a strong selective rule "
        "(Sharpe 0.90). Production WMI&lt;0.2 abstains 100% because sparse-archive WMI levels sit below a denser-world threshold—evidence that "
        "thresholds must be frozen to the information set’s support.",
        S["body"],
    ))
    econ = read_csv("table_econ_oos.csv")
    story.append(make_table(econ, [1.7*inch] + [0.7*inch] * 7))
    story.append(P("Table 3. OOS economic value on real PIT panel.", S["caption"]))
    story.append(KeepTogether([fig("fig1_architecture.png", 6.4*inch, 0.48), P("Fig. 3. OOS cumulative wealth.", S["caption"])]))
    story.append(KeepTogether([fig("fig2_coverage_compare.png", 6.4*inch, 0.42), P("Fig. 4. OOS Sharpe and CE by policy.", S["caption"])]))

    story.append(P("6. Path to JF/RFS", S["h1"]))
    story.append(P(
        "A short empirics sketch is not enough for JF/RFS. Required next steps: multi-year continuous collection so news/on-chain/options/"
        "tokenomics cease to be right-censored; persist daily readiness/AI-context snapshots for pure time_slice replay; replace scarce-world "
        "proxies with logged institutional outages; expand external validity; and keep the full equation apparatus in the submission PDF "
        "(see main_acwmi_sci.tex).",
        S["body"],
    ))

    story.append(P("7. Conclusion", S["h1"]))
    story.append(P(
        "Theory first: RCA-WM / ACWMI and the World-Model-First objects define what a compiled information set is. Empirically, on a real "
        "multi-band PIT archive, thick worlds dominate thin worlds and durable bands have large leave-one-out economic value. Selective "
        "ACWMI gating is implementable under frozen thresholds but is not CE-dominant versus ungated thick signals here. EvoQuant remains "
        "the laboratory, not the theory source.",
        S["body"],
    ))

    story.append(P("Appendix. Reproducibility", S["h1"]))
    story.append(P(
        "Bootstrap <font face='Courier'>pdf/sci/bootstrap_multiband_archive.py</font>; PIT "
        "<font face='Courier'>pdf/sci/build_pit_archive.py</font>; empirics "
        "<font face='Courier'>pdf/sci/run_pit_jf_experiments.py</font>; panel "
        "<font face='Courier'>pdf/data/pit_multiband_panel.csv</font>.",
        S["body"],
    ))

    story.append(P("References", S["h1"]))
    for r in [
        "Cochrane, J.H., 2005. Asset Pricing. Princeton.",
        "Fama, E.F., French, K.R., 1993. Journal of Financial Economics 33, 3–56.",
        "Gu, S., Kelly, B., Xiu, D., 2020. Review of Financial Studies 33, 2223–2273.",
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
        title="Compiling the Market Information Set (Real PIT)",
        author="Guocong Li",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    CN.mkdir(parents=True, exist_ok=True)
    OUT_CN_MIRROR.write_bytes(OUT_EN.read_bytes())
    OUT_LEGACY.write_bytes(OUT_EN.read_bytes())
    print("Wrote", OUT_EN, OUT_EN.stat().st_size)
    print("Mirrored", OUT_CN_MIRROR)


if __name__ == "__main__":
    build()
