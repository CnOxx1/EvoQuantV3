#!/usr/bin/env python3
"""Render the complete JF/RFS working-paper PDF (English) + Chinese theory PDF.

This is the deliverable manuscript package when pdflatex is unavailable.
Canonical TeX source: pdf/sci/main_jf_rfs.tex
Canonical Chinese source: pdf/cn/main_cn_jf.md
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
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

CONTENT_WIDTH = 6.5 * inch
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CN_FONT = None


def _register_cjk_font() -> str | None:
    global _CN_FONT
    if _CN_FONT is not None:
        return _CN_FONT or None
    for path, kwargs in (
        ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", {}),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", {"subfontIndex": 0}),
    ):
        if not Path(path).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("PaperCJK", path, **kwargs))
            _CN_FONT = "PaperCJK"
            return _CN_FONT
        except Exception:
            continue
    _CN_FONT = ""
    return None


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _fmt_cell(val: str) -> str:
    s = str(val).strip()
    try:
        if re.fullmatch(r"-?\d+\.\d+", s):
            # Only compress long floats; keep short literals like 0.3 / 0.05
            if len(s) > 8:
                x = float(s)
                if abs(x) >= 1:
                    return f"{x:.3f}"
                return f"{x:.4f}"
            return s
    except ValueError:
        pass
    # Escape XML specials for Paragraph
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

ROOT = Path(__file__).resolve().parents[1]
SCI = Path(__file__).resolve().parent
FIG = ROOT / "figures"
TAB = ROOT / "tables"
DATA = ROOT / "data"
CN = ROOT / "cn"
OUT_EN = SCI / "main_jf_rfs.pdf"
OUT_EN_ALIAS = SCI / "main_acwmi_sci.pdf"
OUT_CN_MIRROR = CN / "main_jf_rfs.pdf"


def styles():
    font, font_b, font_i = "Times-Roman", "Times-Bold", "Times-Italic"
    return {
        "journal": ParagraphStyle("journal", fontName=font_i, fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#444"), spaceAfter=8),
        "title": ParagraphStyle("title", fontName=font_b, fontSize=13.5, leading=17, alignment=TA_CENTER, spaceAfter=10),
        "author": ParagraphStyle("author", fontName=font, fontSize=11, alignment=TA_CENTER, spaceAfter=2),
        "affil": ParagraphStyle("affil", fontName=font_i, fontSize=9, alignment=TA_CENTER, spaceAfter=12),
        "h1": ParagraphStyle("h1", fontName=font_b, fontSize=12, leading=15, spaceBefore=14, spaceAfter=7),
        "h2": ParagraphStyle("h2", fontName=font_b, fontSize=11, leading=14, spaceBefore=10, spaceAfter=5),
        "h3": ParagraphStyle("h3", fontName=font_b, fontSize=10.5, leading=13, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", fontName=font, fontSize=10, leading=13.5, alignment=TA_JUSTIFY, firstLineIndent=14, spaceAfter=6),
        "abs": ParagraphStyle("abs", fontName=font, fontSize=9.5, leading=13, alignment=TA_JUSTIFY, spaceAfter=6),
        "eq": ParagraphStyle("eq", fontName=font, fontSize=10, leading=14, alignment=TA_CENTER, spaceBefore=4, spaceAfter=4),
        "caption": ParagraphStyle("caption", fontName=font, fontSize=9, leading=11, alignment=TA_CENTER, spaceBefore=3, spaceAfter=10),
        "ref": ParagraphStyle("ref", fontName=font, fontSize=9, leading=11, leftIndent=12, firstLineIndent=-12, spaceAfter=3),
        "note": ParagraphStyle("note", fontName=font_i, fontSize=9, leading=12, spaceAfter=6),
        "bullet": ParagraphStyle("bullet", fontName=font, fontSize=10, leading=13, leftIndent=12, spaceAfter=3),
    }


def P(text, style):
    return Paragraph(text, style)


def read_csv(name):
    with open(TAB / name, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def _cell_style(header: bool = False, cjk: bool = False) -> ParagraphStyle:
    cjk_font = _register_cjk_font()
    if cjk and cjk_font:
        font = cjk_font
    else:
        font = "Times-Bold" if header else "Times-Roman"
    return ParagraphStyle(
        f"cell_{'h' if header else 'b'}_{'cjk' if cjk else 'en'}",
        fontName=font,
        fontSize=7.5 if not header else 8,
        leading=9.5,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )


def make_table(data, col_widths=None, font_size: float = 8):
    """Build a page-fitting table with wrapping Paragraph cells (CJK-safe)."""
    if not data:
        return Spacer(1, 1)
    n_cols = max(len(r) for r in data)
    # Normalize ragged rows
    norm = [list(r) + [""] * (n_cols - len(r)) for r in data]

    if col_widths is None:
        col_widths = [CONTENT_WIDTH / n_cols] * n_cols
    elif abs(sum(col_widths) - CONTENT_WIDTH) > 0.05 * inch:
        # Scale to content width so wide tables do not overflow the page
        scale = CONTENT_WIDTH / float(sum(col_widths))
        col_widths = [w * scale for w in col_widths]

    styled = []
    for i, row in enumerate(norm):
        out_row = []
        for cell in row:
            text = _fmt_cell(cell)
            cjk = _has_cjk(str(cell))
            # If no CJK font, drop CJK glyphs rather than showing tofu boxes
            if cjk and not _register_cjk_font():
                text = _CJK_RE.sub("", str(cell)).strip() or "[zh]"
                text = _fmt_cell(text)
                cjk = False
            style = _cell_style(header=(i == 0), cjk=cjk)
            style.fontSize = font_size if i else font_size
            style.leading = font_size + 1.5
            out_row.append(Paragraph(text, style))
        styled.append(out_row)

    t = Table(styled, colWidths=col_widths, hAlign="CENTER", repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#666666")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return t


def modules_as_grid(names: list[str], n_cols: int = 3) -> list[list[str]]:
    """Turn a 1-column module list into an n-column grid table."""
    body = [n for n in names if n and n != "logic_module"]
    header = [f"Module ({i+1})" for i in range(n_cols)]
    rows = [header]
    for i in range(0, len(body), n_cols):
        chunk = body[i : i + n_cols]
        rows.append(chunk + [""] * (n_cols - len(chunk)))
    return rows


# English role blurbs used when we want a clean Latin-1 appendix table
BAND_ROLE_EN = {
    "exchange": "Microstructure, prices, book, funding, basis",
    "macro": "Macro vintages / rates / liquidity proxies",
    "news": "News and narrative evidence",
    "event_calendar": "ETF / unlock / event calendar",
    "onchain": "On-chain activity / TVL proxies",
    "tokenomics": "Unlocks / supply-side tokenomics",
    "options": "Options surface / gamma walls",
    "alternative": "Alt data (stablecoins, GitHub, trends)",
    "perpetual_dex": "Perp DEX funding / OI",
    "onchain_address": "Address-level on-chain labels",
    "dex_liquidity": "DEX TVL / tick liquidity",
    "gas_network": "Gas / network congestion",
    "governance": "DAO governance events",
}


def fig(name, width=6.3 * inch, ratio=0.45):
    path = FIG / name
    if not path.exists():
        return Spacer(1, 1)
    return Image(str(path), width=width, height=width * ratio)


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 8)
    canvas.drawString(1 * inch, letter[1] - 0.55 * inch, "Li — Compiling the Market Information Set (JF/RFS working paper)")
    canvas.drawCentredString(letter[0] / 2, 0.55 * inch, str(doc.page))
    canvas.restoreState()


def build():
    S = styles()
    inv = json.loads((TAB / "table1_project_inventory.json").read_text())
    arch = json.loads((DATA / "archive_inventory.json").read_text())
    pit = inv.get("pit", {})
    thr = inv.get("frozen_thresholds", {})
    story = []

    story.append(P("Working paper draft — Journal of Finance / Review of Financial Studies", S["journal"]))
    story.append(P(
        "Compiling the Market Information Set: World-Model Quality, Selective Prediction, "
        "and Economic Value in Cryptocurrency Markets",
        S["title"],
    ))
    story.append(P("Guocong Li", S["author"]))
    story.append(P("Independent Researcher · lmu151638@gmail.com", S["affil"]))
    story.append(P(
        "Canonical TeX with displayed equations: <font face='Courier'>pdf/sci/main_jf_rfs.tex</font>. "
        "Chinese full manuscript: <font face='Courier'>pdf/cn/main_cn_jf.md</font>. "
        "Theory source: <font face='Courier'>pdf/original/</font>. EvoQuant is the laboratory, not the theory source.",
        S["note"],
    ))

    # Abstract
    story.append(P("<b>Abstract</b>", S["h2"]))
    story.append(P(
        "Conditional asset pricing treats the investor’s information set as primitive. In cryptocurrency markets that premise fails: "
        "evidence arrives asynchronously and is intermittently unavailable. This paper develops a finance-native theory of "
        "<i>information-set compilation</i>. We define epistemic observations, asynchronous reconstruction bounds, a compilation "
        "operator from raw to AI-visible filtrations, WMI, and regime-conditional ACWMI; and we formalize ECP, MIG, an "
        "availability-shock identification DAG, Bayesian abstention, and explanation metrics EAR/UCR/EV.",
        S["abs"],
    ))
    story.append(P(
        f"Empirically, on a real PIT multi-band panel ({pit.get('n_days', 400)} days × 10 assets; durable bands: exchange, macro, "
        "alternative), vintage-safe macro and stablecoin-flow <i>content</i> enters a transparent action rule under a previous-close "
        "decision clock. The pre-specified contrast—mechanism versus same-input momentum—is positive OOS (ΔCE 0.334, p = 0.034). "
        "LOBO deletions of macro or alternative destroy value (ΔCE −0.42 / −0.40; p = 0.010 / 0.008), mainly through the content "
        "channel; joint deletion and a date-scrambled content placebo discipline redundancy and timing. A 2017–2026 audit shows no "
        "unconditional edge over momentum when band archives are absent. Menu-wide claims versus always-long remain weaker after a "
        "reality-check correction. A pre-registered multi-model AI-consumer protocol (Compiled vs Raw) is secondary validation of "
        "the theory’s AI interface, not primary identification.",
        S["abs"],
    ))
    story.append(P(
        "<b>Keywords:</b> information set; selective prediction; cryptocurrency; point-in-time; measurement error; world models. "
        "&nbsp; <b>JEL:</b> G12, G14, C58, C55",
        S["note"],
    ))

    # 1 Intro
    story.append(P("1. Introduction", S["h1"]))
    story.append(P(
        "Modern asset pricing conditions on an information set I<sub>t</sub>. The literature’s discipline has focused on how I<sub>t</sub> "
        "is used—for discount factors, return prediction, and machine-learning pricing kernels—not on how I<sub>t</sub> is compiled from "
        "asynchronous, quality-heterogeneous evidence. In cryptocurrency markets, compilation is first-order: venue fragmentation, "
        "perpetual leverage, options walls, unlocks, on-chain flows, and macro liquidity can map the same price path into incompatible states.",
        S["body"],
    ))
    story.append(P(
        "This paper makes three contributions. <b>Theory:</b> Regime-Conditional Adaptive World Models (RCA-WM) with a proposition "
        "chain — compilation ≠ feature expansion, an SDF interface constraining pricing to the compiled filtration, reconstruction "
        "bounds, world-conditional abstention, ACWMI monotonicity, and LOBO value with a content/gating decomposition. "
        "<b>Instrument:</b> a reproducible multi-band collection laboratory. <b>Identification:</b> a real PIT archive where band "
        "content enters a transparent action rule, with bootstrap inference, costs/funding, a reality check, and a 2017–2026 "
        "long-span external-validity audit.",
        S["body"],
    ))

    # 2 Literature
    story.append(P("2. Related literature", S["h1"]))
    story.append(P(
        "<b>Information sets in asset pricing.</b> Classic and modern frameworks treat I<sub>t</sub> as given (Cochrane 2005; "
        "Fama–French 1993; Gu–Kelly–Xiu 2020; Kelly–Pruitt–Su 2019; Nagel 2021; Harvey–Liu–Zhu 2016). Machine-learning asset pricing "
        "expands the feature span inside I<sub>t</sub> but typically assumes synchronized panels. We study the prior step: compilation.",
        S["body"],
    ))
    story.append(P(
        "<b>Cryptocurrency market structure.</b> Fragmentation and distinctive risk factors (Makarov–Schoar 2020; Liu–Tsyvinski–Wu 2022) "
        "motivate multi-band worlds rather than price-only predictors.",
        S["body"],
    ))
    story.append(P(
        "<b>Selective prediction and measurement timing.</b> When the world is thin or dishonest, abstention can be optimal. Macro vintages "
        "and crypto freshness/missingness make measurement timing first-class.",
        S["body"],
    ))

    # 3 Theory
    story.append(P("3. Theory", S["h1"]))
    story.append(P(
        "This section restores the formal World-Model-First / RCA-WM apparatus. Empirics instantiate these objects; they do not replace them.",
        S["body"],
    ))

    story.append(P("3.1 World-model quality: breadth, stability, honesty", S["h2"]))
    story.append(P(
        "Let K be the number of critical evidence bands and a<sub>k,t</sub>∈{0,1} an AI-usable indicator. Breadth, stability, and honesty are:",
        S["body"],
    ))
    story.append(P(
        "B<sub>t</sub> = (1/K) Σ<sub>k</sub> a<sub>k,t</sub>, &nbsp;&nbsp; "
        "U<sub>t</sub> = exp(−Σ<sub>j</sub> ω<sub>j</sub> d<sub>j,t</sub>), &nbsp;&nbsp; "
        "H<sub>t</sub> = 1 − (1/J) Σ<sub>j</sub> m<sub>j,t</sub>.",
        S["eq"],
    ))
    story.append(P("The production baseline World Model Index is the product form", S["body"]))
    story.append(P("WMI<sub>t</sub> = B<sub>t</sub> × U<sub>t</sub> × H<sub>t</sub>.", S["eq"]))
    story.append(P(
        "Hierarchical breadth and continuous honesty used in the PIT panel:",
        S["body"],
    ))
    story.append(P(
        "B<sup>hier</sup><sub>t</sub> = 0.25 B<sup>dom</sup><sub>t</sub> + 0.35 B<sup>band</sup><sub>t</sub> + 0.40 B<sup>asset</sup><sub>t</sub>,",
        S["eq"],
    ))
    story.append(P(
        "H<sup>cont</sup><sub>t</sub> = exp(−2c<sub>t</sub>) max(0, 1 − 0.5(1−e<sub>t</sub>)),",
        S["eq"],
    ))
    story.append(P("where e<sub>t</sub> is the ready-share and c<sub>t</sub> a contamination share.", S["body"]))

    story.append(P("3.2 Epistemic observations", S["h2"]))
    story.append(P(
        "An AI-consumable market observation is not a bare scalar:",
        S["body"],
    ))
    story.append(P(
        "O<sub>j,t</sub> = (x<sub>j,t</sub>, τ<sub>j,t</sub>, q<sub>j,t</sub>, g<sub>j,t</sub>, r<sub>j,t</sub>),",
        S["eq"],
    ))
    story.append(P(
        "with value, latest-available time, quality, main-view gate, and semantic role. Numerically identical x with different "
        "(τ,q,g,r) are different world-model objects.",
        S["body"],
    ))

    story.append(P("3.3 Asynchronous state space and lag error", S["h2"]))
    story.append(P(
        "Latent states evolve as S<sub>t+1</sub> = F(S<sub>t</sub>, η<sub>t+1</sub>). Source j observes a lagged map "
        "X<sup>obs</sup><sub>j,t</sub> = h<sub>j</sub>(S<sub>t−ℓ</sub>) + ν<sub>j,t</sub>. If h<sub>j</sub> is Lipschitz, "
        "reconstruction error admits a bound with delay, noise, and missingness terms:",
        S["body"],
    ))
    story.append(P(
        "‖S̃<sub>t</sub> − S<sub>t</sub>‖ ≤ C<sub>1</sub> Σ ω<sub>j</sub>ℓ<sub>j,t</sub> + C<sub>2</sub> Σ ω<sub>j</sub>‖ν<sub>j,t</sub>‖ "
        "+ C<sub>3</sub> Σ ω<sub>j</sub>(1−z<sub>j,t</sub>).",
        S["eq"],
    ))
    story.append(P(
        "Latest-snapshot, freshness/TTL, and readiness gates target these three terms.",
        S["body"],
    ))

    story.append(P("3.4 Filters and the compilation operator", S["h2"]))
    story.append(P(
        "F<sup>raw</sup><sub>t</sub> = σ({X<sup>obs</sup><sub>j,τ</sub>}), &nbsp; "
        "F<sup>AI</sup><sub>t</sub> = σ(W<sup>AI</sup><sub>t</sub>, D<sub>t</sub>), &nbsp; "
        "Π<sub>t</sub> = B<sub>t</sub> ∘ M<sub>t</sub> ∘ A<sub>t</sub>, &nbsp; "
        "W<sup>AI</sup><sub>t</sub> = Π<sub>t</sub>(F<sup>raw</sup><sub>t</sub>).",
        S["eq"],
    ))
    story.append(P(
        "<b>Proposition 1 (compilation ≠ feature expansion).</b> Enlarging F<sup>raw</sup> without a well-defined Π need not enlarge "
        "decision-relevant F<sup>AI</sup>: ungated, stale, or role-incoherent evidence can expand raw span while shrinking usable "
        "world quality via H<sub>t</sub> and U<sub>t</sub>.",
        S["body"],
    ))
    story.append(P(
        "<i>Proof sketch.</i> Add a source j* with large lag or missingness flag. If M<sub>t</sub> fails to exclude it, H falls by Δ&gt;0 "
        "and freshness penalties weakly lower U. Breadth rises by at most 1/K, but multiplicative WMI = BUH can fall when UH losses "
        "dominate. Since W<sup>AI</sup> = Π(F<sup>raw</sup>) inherits gated objects, raw σ-field expansion need not enlarge "
        "payoff-relevant AI-visible information. □",
        S["body"],
    ))
    story.append(P(
        "<b>Proposition 2 (SDF interface: compilation constrains pricing).</b> An agent whose usable conditioning information is "
        "F<sup>AI</sup> can only implement pricing statements E[m R | F<sup>AI</sup>] = 1. Evaluating the same agent against the finer "
        "F<sup>raw</sup> produces a <i>compilation wedge</i> w<sub>t</sub> = E[mR|F<sup>raw</sup>] − E[mR|F<sup>AI</sup>], which is zero "
        "for all payoffs iff compilation loses no pricing-relevant information. Alpha measured against the raw filtration confounds "
        "skill with compilation loss.",
        S["body"],
    ))
    story.append(P(
        "<i>Proof sketch.</i> By iterated expectations E[w<sub>t</sub>|F<sup>AI</sup>] = 0, but w<sub>t</sub> ≠ 0 pointwise unless the "
        "raw-conditional moment is F<sup>AI</sup>-measurable. If a band with MIG&gt;0 is discarded, a payoff exists whose raw-conditional "
        "expectation varies with that band while the compiled one does not. □",
        S["body"],
    ))
    story.append(P(
        "<b>Proposition 3 (lag reconstruction bound).</b> Under Lipschitz observation maps and bounded increments ‖S<sub>u</sub>−S<sub>u−1</sub>‖≤δ̄, "
        "reconstruction error admits the delay / noise / missingness bound above with C′₁ = C₁δ̄ independent of the AI model class.",
        S["body"],
    ))
    story.append(P(
        "<i>Proof sketch.</i> Lipschitz gives ‖h<sub>j</sub>(S<sub>t</sub>)−h<sub>j</sub>(S<sub>t−ℓ</sub>)‖ ≤ L<sub>j</sub>δ̄ ℓ<sub>j,t</sub>. "
        "Decompose S̃−S into lagged-map bias, ν, and missingness; triangle inequality + weights ω<sub>j</sub> yield the bound. "
        "TTL / readiness operators shrink exactly those three terms. □",
        S["body"],
    ))

    story.append(P("3.5 ECP, MIG, and causal DAG", S["h2"]))
    story.append(P(
        "ECP<sub>t</sub> = 1{conf<sub>t</sub> &gt; c̄} 1{WMI<sub>t</sub> &lt; w}.",
        S["eq"],
    ))
    story.append(P(
        "Thick versus thin information sets differ by conditional mutual information; band k’s marginal information gain on task m is "
        "MIG<sup>(m)</sup><sub>k,t</sub> = I(R<sup>(m)</sup><sub>t</sub>; E<sub>k,t</sub> | I<sup>(−k)</sup><sub>t</sub>).",
        S["body"],
    ))
    story.append(P(
        "Identification DAG: O<sub>t</sub> → W<sub>t</sub> → A<sub>t</sub>, with market complexity M<sub>t</sub> and latent configuration "
        "C<sub>t</sub> as confounders. Availability shocks O<sub>t</sub> are the preferred quasi-exogenous lever.",
        S["body"],
    ))

    story.append(P("3.6 Bayesian abstention", S["h2"]))
    story.append(P(
        "With action set A = {bullish, bearish, neutral, abstain},",
        S["body"],
    ))
    story.append(P(
        "a*<sub>t</sub> = arg min<sub>a</sub> E[ℓ(a, R<sub>t</sub>) | W<sub>t</sub>].",
        S["eq"],
    ))
    story.append(P(
        "Abstain when every non-abstain action has expected loss above a world-dependent cost c<sub>abs</sub>(W<sub>t</sub>).",
        S["body"],
    ))
    story.append(P(
        "<b>Proposition 4 (world-conditional abstention).</b> If ℓ(abstain)≡c<sub>abs</sub>(W) and every non-abstain action has "
        "E[ℓ|W]&gt;c<sub>abs</sub>(W), then a*=abstain. Under a single-crossing assumption (now formalized as Assumption 1), with "
        "non-abstain loss and c<sub>abs</sub> weakly decreasing in WMI, the abstention region is a lower set in WMI "
        "(implemented by IS-frozen ACWMI thresholds).",
        S["body"],
    ))
    story.append(P(
        "<i>Proof sketch.</i> First claim is the Bayes argmin. Second: let L̲(W)=min<sub>a≠abs</sub> E[ℓ|W]; single crossing makes "
        "{W: L̲&gt;c<sub>abs</sub>} a lower contour set. □",
        S["body"],
    ))

    story.append(P("3.7 ACWMI and explanation metrics", S["h2"]))
    story.append(P(
        "ACWMI<sub>t</sub> = exp( Σ<sub>i</sub> γ<sub>i</sub>(r<sub>t</sub>) log x<sub>i,t</sub> / Σ<sub>i</sub> γ<sub>i</sub> ), "
        "with x = (B<sup>hier</sup>, U, H<sup>cont</sup>, S, C).",
        S["eq"],
    ))
    story.append(P(
        "EAR<sub>t</sub> = (# evidence-bound claims)/(# claims), &nbsp; UCR<sub>t</sub> = 1 − EAR<sub>t</sub>, &nbsp; "
        "EV<sub>t</sub> = d(Φ<sub>t</sub>, Φ<sub>t−1</sub>) / (1 + d(W<sub>t</sub>, W<sub>t−1</sub>)). "
        "Thin and thick worlds also differ in explanation sets Φ<sub>t</sub>.",
        S["body"],
    ))
    story.append(P(
        "<b>Proposition 5 (ACWMI factor monotonicity).</b> With γ≫0 and x∈(0,1], ∂ACWMI/∂x<sub>k</sub>&gt;0 and log ACWMI is concave "
        "in log x. A proportional honesty deterioration cannot be offset one-for-one by raising breadth with equal weight.",
        S["body"],
    ))
    story.append(P(
        "<i>Proof sketch.</i> log ACWMI = Σ w<sub>i</sub> log x<sub>i</sub> with w<sub>i</sub>=γ<sub>i</sub>/Σγ; "
        "∂ACWMI/∂x<sub>k</sub> = ACWMI·w<sub>k</sub>/x<sub>k</sub>&gt;0. Under contamination, Δlog H is large while Δlog B = O(1/K), "
        "so net Σ w Δlog x &lt; 0. □",
        S["body"],
    ))
    story.append(P(
        "<b>Proposition 6 (LOBO as economic MIG, with channel decomposition).</b> Let V(I) be OOS CE of a fixed rule on information set I and "
        "MIĜ<sub>k</sub>=V(I)−V(I∖E<sub>k</sub>). Under Blackwell monotonicity and non-redundancy, MIĜ<sub>k</sub>&gt;0. "
        "Band k enters through a <i>content</i> channel (its signal changes the action) and a <i>gating</i> channel (its availability changes B/U/H and abstention); the MIG telescopes exactly into the two channel effects. In the PIT laboratory, forcing the band tilt to zero implements content deletion; setting band status to missing implements gating deletion; both together implement I∖E<sub>k</sub>.",
        S["body"],
    ))
    story.append(P(
        "<i>Proof sketch.</i> Blackwell ⇒ V(I)≥V(I∖E<sub>k</sub>); strict when E<sub>k</sub> has unique predictive content. "
        "The decomposition is a telescoping identity over the three experiment arms (content-only, gating-only, both). □",
        S["body"],
    ))
    story.append(P(
        "<b>Proposition chain (summary).</b> Prop.1 separates raw span from usable world quality; Prop.2 constrains any pricing "
        "kernel to the compiled filtration (alpha vs compilation wedge); Prop.3 grounds freshness/TTL as reconstruction "
        "controls; Prop.4 justifies world-conditional abstention; Prop.5 makes ACWMI a strict quality index; Prop.6 maps "
        "LOBO CE drops to economic MIG and separates content from gating. Empirics below instantiate this chain—they do "
        "not replace it.",
        S["body"],
    ))

    story.append(PageBreak())

    # 4 Lab
    story.append(P("4. The EvoQuant laboratory as measurement instrument", S["h1"]))
    story.append(P(
        "EvoQuant supplies multi-band collectors, readiness scoring, BandPITService / time_slice PIT reconstruction, "
        "availability-shock queries over collection_runs, and configurable WMI/ACWMI thresholds "
        "(WORLD_MODEL_INDEX_MODE, WMI_ABSTAIN_THRESHOLD, ACWMI_ABSTAIN_THRESHOLD). Epistemological order: theory first, laboratory second.",
        S["body"],
    ))

    story.append(PageBreak())
    # 5 Data
    story.append(P("5. Data and real multi-band PIT archive", S["h1"]))
    story.append(P("5.1 Populated archive", S["h2"]))
    story.append(P(
        f"Exchange (OKX): ~{arch['exchange']['klines']} klines/merged bars, daily "
        f"{arch['exchange']['range_1d'][0]} → {arch['exchange']['range_1d'][1]}; "
        f"~{arch['exchange']['funding_rates']} funding rows. "
        f"Macro: {arch['market']['macro_timeseries']} vintaged points. "
        f"Alternative: {arch['market']['alternative_timeseries']} points. "
        f"News/on-chain/options/tokenomics populated but mostly right-censored to collection day. "
        "Analytics snapshots remain sparse historically; multi-band PIT uses raw history tables via build_pit_archive.py "
        "(production path prefers BandPITService).",
        S["body"],
    ))
    story.append(P("5.2 PIT panel", S["h2"]))
    story.append(P(
        f"For each date t and asset, band status ∈ {{ready, limited, missing}} is inferred from the latest observation time ≤ t "
        f"and band-specific freshness thresholds. Panel: {pit.get('start')} → {pit.get('end')}, "
        f"{pit.get('n_days')} days × 10 assets = {pit.get('n_rows')} rows. "
        f"Durable bands: {', '.join(inv.get('hist_bands', []))}. Yahoo daily returns provide payoffs; engines use only pre-t returns.",
        S["body"],
    ))
    br = pit.get("band_ready_rates", {})
    story.append(P(
        "Empirical ready rates (approx.): "
        + ", ".join(f"{k}={v:.3f}" for k, v in br.items())
        + ".",
        S["body"],
    ))

    story.append(PageBreak())
    # 6 Design
    story.append(P("6. Empirical design", S["h1"]))
    story.append(P(
        f"Chronological IS/OOS split at {inv.get('is_oos_cut')} (200/200 days). "
        f"AC thresholds frozen on IS by Sharpe maximization with abstain rate ∈ [5%, 55%]: "
        f"ACWMI &lt; {thr.get('ac_thr', 0.25):.2f} or C &lt; {thr.get('c_thr', 0.25):.2f} (calibration selects minimal gating). "
        "Production WMI threshold 0.2 is never tuned on OOS. "
        "Policies: always-long; momentum; mechanism with band content; simple outage; cascade; WMI; ACWMI (IS-frozen). "
        "Economic value: annualized return/vol, Sharpe, CRRA CE (γ=2), max DD. "
        "<b>Inference:</b> circular block bootstrap on OOS daily PnL (n_boot=999, block=5) with block-length sensitivity "
        "{5,10,21} and a White (2000) reality check; costs 10/25/50 bps on turnover plus perp-funding adjustment. "
        "Identification: thin vs thick (content+gating); LOBO with channel decomposition; scarce-world event study; "
        "2017–2026 long-span audit.",
        S["body"],
    ))
    story.append(P("6.1 Mechanism signals: transparent rule with band content", S["h2"]))
    story.append(P(
        "Directional actions are a deterministic rule on named production calculators, and band <i>content</i> enters directly: "
        "macro_tilt (vintaged VIX/DXY 5d changes: both down = risk-on +1, both up = risk-off −1) and alt_tilt "
        "(stablecoin 7d net-supply sign, latest obs &lt; t). Tilts are forced to 0 when the band is not PIT-ready, so LOBO deletes "
        "content, not only gating. Rule: R1 crisis ∧ cascade_p≥0.60 → short (evidence conjunction); "
        "R2 trend ∧ mom5&gt;0 ∧ cascade_p&lt;0.45 ∧ macro_tilt≥0 → long; R2b range ∧ both tilts&gt;0 ∧ mom5≥0 → long; "
        "R3 sign(mom5) with a double-risk-off long veto (→ flat), ties broken by sign(tilt sum). "
        "C = pairwise sign agreement among {mom5, flow, −1_{casc&gt;0.55}, −1_{sys&gt;55}, macro_tilt, alt_tilt}.",
        S["body"],
    ))
    story.append(P(
        "<b>Calibration audit and engine-input repair (disclosed).</b> A long-span audit exposed two harness flaws: full-history "
        "drawdowns made crisis an absorbing state, and the cascade input map saturated at 0.86 (a constant short that won a bear "
        "OOS by construction). Repaired with 60-day windows, volatility-standardized tail intensity, and real RSI/ADX proxies; "
        "cascade_p is now monotone in realized next-day left tails (P(r&lt;−5%) rising 0.039 → 0.110 across deciles). "
        "The repair was driven by the audit, not by OOS performance search.",
        S["body"],
    ))
    try:
        mech = read_csv("table_mechanism_definition.csv")
        story.append(make_table(mech, font_size=6.5))
        story.append(P("Table. Mechanism component definitions (audit).", S["caption"]))
    except Exception:
        pass

    story.append(PageBreak())
    # 7 Results
    story.append(P("7. Main results", S["h1"]))
    story.append(P("7.1 Band content beats momentum out of sample", S["h2"]))
    story.append(P(
        "Always-long loses badly in this bear window (CE −1.157); momentum is nearly flat (Sharpe 0.101, CE −0.202); the transparent "
        "rule with band content earns Sharpe 0.767 and CE +0.132, standing aside on 7.5% of asset-days via content-driven vetoes. "
        "<b>Headline: mechanism − momentum ΔCE = 0.334, p = 0.034, 95% CI [0.03, 0.68] excludes zero.</b> The two policies share all "
        "return-based inputs and differ only in vintaged macro/alternative content, so this contrast isolates compiled band content.",
        S["body"],
    ))
    econ = read_csv("table_econ_oos.csv")
    story.append(make_table(econ, font_size=7.5))
    story.append(P("Table 1. OOS economic value on real PIT panel (200 days).", S["caption"]))
    story.append(KeepTogether([fig("fig1_architecture.png"), P("Figure 1. OOS cumulative wealth.", S["caption"])]))
    story.append(KeepTogether([fig("fig2_coverage_compare.png", 6.2 * inch, 0.42), P("Figure 2. OOS Sharpe and CE by policy.", S["caption"])]))

    story.append(P("7.2 Thick vs thin worlds", S["h2"]))
    story.append(P(
        "The thin exchange-only observer (content AND gating deleted) abstains 45% and earns CE −0.388; the thick world earns +0.132. "
        "ΔSharpe = 1.62 (p = 0.044, CI excludes zero); ΔCE = 0.52 (p = 0.22, not yet significant at 200 days).",
        S["body"],
    ))
    tt = read_csv("table_thin_thick.csv")
    story.append(make_table(tt, [2.5 * inch] + [0.7 * inch] * 6))
    story.append(P("Table 2. Thin vs thick on the real PIT archive (OOS).", S["caption"]))
    story.append(KeepTogether([fig("fig6_event_study.png"), P("Figure 3. Thin vs thick worlds (real PIT).", S["caption"])]))

    story.append(P("7.3 Leave-one-band-out: significant, and driven by content", S["h2"]))
    story.append(P(
        "Deleting macro costs ΔCE −0.418 (p = 0.010); alternative −0.402 (p = 0.008); exchange status −0.056 (p = 0.394; exchange "
        "content is the return data itself). The decomposition shows the loss runs mainly through the <i>content</i> channel "
        "(−0.334, p = 0.034 for both bands) with a smaller significant gating contribution (macro −0.066, p = 0.026; alternative "
        "−0.040, p = 0.044). Band information changes <i>what</i> the rule trades, not merely <i>when</i> it abstains. Content-only "
        "losses coincide across bands because R2b and the double-risk-off veto require both tilts to agree.",
        S["body"],
    ))
    lobo = read_csv("table_lobo.csv")
    story.append(make_table(lobo, font_size=7.5))
    story.append(P("Table 3. Leave-one-band-out on durable PIT bands (total effect).", S["caption"]))
    try:
        dec = read_csv("table_lobo_decomposition.csv")
        story.append(make_table(dec, font_size=7.5))
        story.append(P("Table 4. LOBO channel decomposition: content vs gating.", S["caption"]))
    except Exception:
        pass
    story.append(KeepTogether([fig("fig4_regime_box.png", 6.2 * inch, 0.42), P("Figure 4. LOBO marginal CE on durable bands.", S["caption"])]))

    story.append(P("7.4 Long-span external-validity audit (2017–2026)", S["h2"]))
    story.append(P(
        "The identical rule (tilts zero: no band archive before 2025) on BTC/ETH over 3,471 days: annualized return 0.456, "
        "Sharpe 0.664, CE −0.009, positive in 8 of 10 years including 2018 (+2.13 in a −1.08 always-long year) — and no significant "
        "advantage over momentum (ΔCE 0.017, p = 0.55). The return-based core has no hidden alpha; the significant OOS gains load "
        "on compiled band content, which exists only where the multi-band archive exists.",
        S["body"],
    ))
    try:
        ls = read_csv("table_longspan_by_year.csv")
        story.append(make_table(ls, font_size=7))
        story.append(P("Table 5. Long-span audit by year (BTC/ETH; crisis_share is the classifier's label share).", S["caption"]))
    except Exception:
        pass
    try:
        cal = read_csv("table_cascade_calibration.csv")
        story.append(make_table(cal, font_size=7))
        story.append(P("Table 6. cascade_p calibration: deciles vs realized next-day left tails.", S["caption"]))
    except Exception:
        pass

    story.append(P("7.5 Bootstrap contrasts, costs, and inference robustness", S["h2"]))
    story.append(P(
        "Block-bootstrap (999 × 5-day) contrasts: the mechanism − momentum content contrast is significant (p = 0.034); contrasts "
        "against always-long remain wide at 200 days. Conclusions are stable across block lengths {5, 10, 21}. The White (2000) "
        "reality check across the policy menu vs always-long gives p = 0.144 — the menu-wide claim is weaker than the single "
        "pre-specified content contrast, disclosed side by side. With 10 bps one-way costs the mechanism keeps Sharpe 0.467 "
        "(CE −0.019 vs momentum −0.352); at 25 bps both are negative but the ranking is preserved; the perp-funding adjustment "
        "moves CE by less than 0.005. B_hier weight perturbations leave CE unchanged to three decimals.",
        S["body"],
    ))
    try:
        boot = read_csv("table_bootstrap_oos.csv")
        if boot:
            keep = ["contrast", "dSharpe", "dCE", "p_CE", "ci_dCE_05", "ci_dCE_95"]
            hdr = boot[0]
            idx = [hdr.index(k) for k in keep if k in hdr]
            slim = [[hdr[i] for i in idx]] + [[row[i] for i in idx] for row in boot[1:]]
            story.append(make_table(slim, font_size=7))
            story.append(P("Table 7. OOS block-bootstrap contrasts.", S["caption"]))
    except Exception:
        pass
    try:
        cost = read_csv("table_cost_sensitivity.csv")
        story.append(make_table(cost, font_size=7))
        story.append(P("Table 8. Transaction-cost and funding sensitivity (OOS).", S["caption"]))
    except Exception:
        pass

    story.append(P("7.6 Selective prediction on a sparse archive", S["h2"]))
    story.append(P(
        "IS calibration selects minimal additional index gating (frozen ACWMI &lt; 0.25 binds on ~1% of days beyond content "
        "stand-asides) and the production WMI &lt; 0.2 rule abstains 100%: quality thresholds are not portable across "
        "information-set supports. The measured epistemic calibration penalty is high (ECP = 0.688 at conf &gt; 0.7, WMI &lt; 0.2): "
        "the classifier is often confident while the world is thin — the state ECP is designed to flag. All actions bind to named "
        "calculator evidence (EAR = 1, UCR = 0).",
        S["body"],
    ))
    story.append(P(
        "Implications: (i) compilation quality has first-order economic content and the content channel dominates gating; "
        "(ii) mechanism − momentum isolates band content by construction and is significant; (iii) the long-span audit rules out "
        "hidden return-rule alpha; (iv) thresholds must be frozen to archive support; (v) remaining contrasts vs always-long are "
        "not yet significant at 200 days — point estimates and significance reported separately.",
        S["body"],
    ))

    story.append(PageBreak())
    # 8 AI-consumer validation (secondary)
    story.append(P("8. AI-consumer validation (secondary)", S["h1"]))
    story.append(P(
        "The SDF interface and world-conditional abstention are statements about agents that condition on "
        "ℱ<sup>AI</sup><sub>t</sub>. We pre-register a <i>within-model</i> Compiled versus Raw protocol: for each model m, "
        "Δ<sub>m</sub> = V<sub>m</sub>(Compiled) − V<sub>m</sub>(Raw), with frozen prompts, temperature 0, and the same action "
        "schema {bullish, bearish, neutral, abstain}. Compiled bundles expose PIT-safe epistemic fields and abstention guidance; "
        "Raw bundles expose only thin return/momentum views. The estimand is the cross-model mean Δ̄, not a vendor leaderboard. "
        "Offline deterministic mock consumers ship in the replication package (pdf/sci/llm_consumer/) so the protocol is "
        "CI-testable without API keys; live vendors may be substituted behind the same interface. This design is deliberately "
        "secondary to PIT/LOBO identification.",
        S["body"],
    ))
    llm_path = TAB / "table_llm_consumer_summary.json"
    if llm_path.exists():
        try:
            llm = json.loads(llm_path.read_text(encoding="utf-8"))
            story.append(P(
                f"Offline mock suite on the current OOS window: mean ΔCE(Compiled−Raw) = {llm.get('mean_dCE')}; "
                f"models = {', '.join(llm.get('models') or [])}. Interpret as protocol smoke / calibration check, not as "
                "unconditional LLM alpha.",
                S["body"],
            ))
        except Exception:
            pass

    # 9 Robustness
    story.append(P("9. Robustness, threats, and the JF/RFS agenda", S["h1"]))
    for line in [
        "<b>Right-censored bands.</b> News/on-chain/options/tokenomics lack durable history; continuous multi-year collection is required.",
        "<b>Content vintages.</b> Band-content identification rests on a single 400-day archive window; extend content calendars to multiple regimes.",
        "<b>Natural outages.</b> Hard institutional outages are rare in continuous OKX backfill; logged collection_runs and planted shocks sharpen O<sub>t</sub>.",
        "<b>Snapshot density.</b> Daily readiness/AI-context snapshots will enable pure time_slice replay.",
        "<b>External validity.</b> Expand beyond ten liquid names; the 2017–2026 audit anchors the return core only.",
        "<b>Multiple testing.</b> The headline contrast is a single pre-specified comparison; the menu-wide reality check (p = 0.144) is reported alongside; add stationary-bootstrap confirmation.",
    ]:
        story.append(P(line, S["body"]))

    story.append(P(
        "<b>Timing / ACWMI disclosure.</b> Features for earning r<sub>t</sub> are evaluated at (t−1) 23:59. Live API bundles "
        "disclose acwmi_input_source ∈ {paper_engines, production_proxy}; paper empirics use engine (S,C).",
        S["body"],
    ))

    # 10 Conclusion
    story.append(P("10. Conclusion", S["h1"]))
    story.append(P(
        "Information-set compilation is a first-order object in cryptocurrency markets. This paper develops the RCA-WM / ACWMI theory "
        "as a proposition chain — compilation ≠ feature expansion, an SDF interface, reconstruction bounds, world-conditional "
        "abstention, ACWMI monotonicity, and LOBO value with a content/gating decomposition — and instantiates every object on a real "
        "multi-band PIT archive. Vintage-safe macro and stablecoin-flow content carries significant OOS economic value (ΔCE vs "
        "momentum 0.334, p = 0.034; LOBO macro/alternative p = 0.010/0.008 with the content channel dominant), while the long-span "
        "audit shows the return-based rule itself has no hidden alpha — exactly the pattern compilation theory predicts. The path to "
        "a final submission is institutional: deepen vintaged histories, log outages, snapshot daily, and expand the cross-section — "
        "without abandoning the formal apparatus.",
        S["body"],
    ))

    story.append(PageBreak())
    # Appendix
    story.append(P("Appendix A. Notation", S["h1"]))
    note = [
        ["Symbol", "Meaning"],
        ["O_j,t", "Epistemic observation"],
        ["B_t, U_t, H_t", "Breadth, stability, honesty"],
        ["WMI_t / ACWMI_t", "Production / regime-conditional index"],
        ["Pi_t", "Compilation operator"],
        ["ECP / MIG", "Calibration penalty / band information gain"],
        ["Phi_t; EAR/UCR/EV", "Explanation set and metrics"],
        ["O_t", "Availability shock (DAG)"],
    ]
    story.append(make_table(note, [2.2 * inch, 4.2 * inch]))
    story.append(P("Table A1. Core notation.", S["caption"]))

    story.append(P("Appendix B. Evidence bands and laboratory map", S["h1"]))
    story.append(P(
        "The laboratory organizes collectors into evidence bands that feed readiness and AI context. "
        "Table B1 lists band-level inventory used by the paper’s readiness weights; Table B2 samples logic modules.",
        S["body"],
    ))
    try:
        bands_raw = read_csv("table1_evidence_bands.csv")
        # Keep 5 columns but use English roles so Latin PDF never shows tofu boxes;
        # CJK font path still works if Role retains Chinese.
        bands = [bands_raw[0]]
        for row in bands_raw[1:14]:
            band = row[0] if row else ""
            role = BAND_ROLE_EN.get(band) or (row[4] if len(row) > 4 else "")
            bands.append([row[0], row[1], row[2], row[3], role])
        story.append(
            make_table(
                bands,
                [0.95 * inch, 1.35 * inch, 0.7 * inch, 0.75 * inch, 2.75 * inch],
                font_size=7.5,
            )
        )
        story.append(P("Table B1. Evidence bands (excerpt).", S["caption"]))
    except Exception as e:
        story.append(P(f"[Table B1 unavailable: {e}]", S["note"]))
    try:
        mods = read_csv("table_a2_logic_modules.csv")
        names = [r[0] for r in mods if r]
        grid = modules_as_grid(names[:30], n_cols=3)
        story.append(make_table(grid, [2.166 * inch] * 3, font_size=8))
        story.append(P("Table B2. Logic modules (excerpt, 3-column grid).", S["caption"]))
    except Exception as e:
        story.append(P(f"[Table B2 unavailable: {e}]", S["note"]))
    try:
        tmap = read_csv("table5_theory_implementation_map.csv")
        # Keep whole B3 together — previous split dropped leading rows across the page break.
        story.append(PageBreak())
        story.append(
            KeepTogether(
                [
                    make_table(tmap, [1.7 * inch, 2.7 * inch, 2.1 * inch], font_size=7.5),
                    P("Table B3. Theory-to-implementation map.", S["caption"]),
                ]
            )
        )
    except Exception as e:
        story.append(P(f"[Table B3 unavailable: {e}]", S["note"]))

    story.append(PageBreak())
    story.append(P("Appendix C. Additional empirics", S["h1"]))
    story.append(P(
        "IS/OOS stability and conditional IC tables from the experiment suite are reported below for completeness. "
        "They complement the main CE/Sharpe horse-race and should be read under the same frozen-threshold protocol.",
        S["body"],
    ))
    try:
        stab = read_csv("table_is_oos_stability.csv")
        story.append(
            KeepTogether(
                [
                    make_table(stab, [1.2 * inch, 1.5 * inch, 1.9 * inch, 1.9 * inch], font_size=8),
                    P("Table C1. IS/OOS stability.", S["caption"]),
                ]
            )
        )
    except Exception as e:
        story.append(P(f"[Table C1 unavailable: {e}]", S["note"]))
    try:
        cic = read_csv("table_conditional_ic.csv")
        story.append(
            KeepTogether(
                [
                    make_table(
                        cic,
                        [0.7 * inch, 0.9 * inch, 0.55 * inch, 0.85 * inch, 0.8 * inch, 0.7 * inch, 1.0 * inch, 0.9 * inch],
                        font_size=7,
                    ),
                    P("Table C2. Conditional IC.", S["caption"]),
                ]
            )
        )
    except Exception as e:
        story.append(P(f"[Table C2 unavailable: {e}]", S["note"]))
    try:
        ts = read_csv("table_timeslice_grid.csv")
        # Slim 16-col grid + short headers (long names were wrapping mid-word).
        keep = [
            "timestamp",
            "domains_ready",
            "domains_stale",
            "domains_missing",
            "overall_freshness",
            "dom_klines",
            "dom_asset_readiness",
            "dom_ai_market_context",
        ]
        short_h = ["date", "ready", "stale", "missing", "freshness", "klines", "readiness", "ai_ctx"]
        header = ts[0]
        idx = [header.index(k) for k in keep if k in header]
        slim = [short_h[: len(idx)]]
        for row in ts[1:13]:
            slim.append([row[i] if i < len(row) else "" for i in idx])
        for r in slim[1:]:
            if r and "T" in r[0]:
                r[0] = r[0].split("T", 1)[0]
        story.append(
            KeepTogether(
                [
                    make_table(
                        slim,
                        [0.9 * inch, 0.65 * inch, 0.65 * inch, 0.75 * inch, 0.95 * inch, 0.75 * inch, 0.95 * inch, 0.9 * inch],
                        font_size=7.5,
                    ),
                    P(
                        "Table C3. time_slice monthly grid (summary; analytics snapshots remain sparse historically).",
                        S["caption"],
                    ),
                ]
            )
        )
    except Exception as e:
        story.append(P(f"[Table C3 unavailable: {e}]", S["note"]))

    story.append(P("Appendix D. Reproducibility", S["h1"]))
    story.append(P(
        "make paper-full &nbsp;|&nbsp; make paper-lab &nbsp;|&nbsp; "
        "python3 pdf/sci/bootstrap_multiband_archive.py &nbsp;|&nbsp; "
        "build_pit_archive.py &nbsp;|&nbsp; "
        "run_pit_jf_experiments.py &nbsp;|&nbsp; "
        "generate_full_manuscript_pdf.py. "
        "Artifacts: pdf/data/pit_multiband_panel.csv; pdf/sci/main_jf_rfs.tex; pdf/cn/main_cn_jf.md.",
        S["body"],
    ))
    story.append(P(
        "Draft status: structurally complete working paper (theory + real PIT empirics + agenda). "
        "Acceptance at JF/RFS still requires deeper vintaged histories, logged outages, broader cross-section, "
        "and journal-format polishing—without dropping the formal apparatus again.",
        S["note"],
    ))

    story.append(PageBreak())
    story.append(P("References", S["h1"]))
    for r in [
        "Cochrane, J.H., 2005. Asset Pricing. Princeton University Press.",
        "Fama, E.F., French, K.R., 1993. Journal of Financial Economics 33, 3–56.",
        "Gu, S., Kelly, B., Xiu, D., 2020. Review of Financial Studies 33, 2223–2273.",
        "Harvey, C.R., Liu, Y., Zhu, H., 2016. Review of Financial Studies 29, 5–68.",
        "Kelly, B.T., Pruitt, S., Su, Y., 2019. Journal of Financial Economics 134, 501–524.",
        "Liu, Y., Tsyvinski, A., Wu, X., 2022. Journal of Finance 77, 1133–1177.",
        "Makarov, I., Schoar, A., 2020. Journal of Financial Economics 135, 293–319.",
        "Nagel, S., 2021. Machine Learning in Asset Pricing. Princeton University Press.",
    ]:
        story.append(P(r, S["ref"]))

    CN.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT_EN),
        pagesize=letter,
        leftMargin=1.0 * inch,
        rightMargin=1.0 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
        title="Compiling the Market Information Set (JF/RFS Working Paper)",
        author="Guocong Li",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    OUT_EN_ALIAS.write_bytes(OUT_EN.read_bytes())
    OUT_CN_MIRROR.write_bytes(OUT_EN.read_bytes())
    print("Wrote", OUT_EN, OUT_EN.stat().st_size)


def build_chinese_pdf():
    """Render Chinese full manuscript if a CJK font is available."""
    md_path = CN / "main_cn_jf.md"
    out = CN / "main_cn_jf.pdf"
    if not md_path.exists():
        return
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return
    font_path = None
    for cand in (
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ):
        if Path(cand).exists():
            font_path = cand
            break
    if not font_path:
        print("No CJK font; skip Chinese PDF (markdown source remains).")
        return
    try:
        pdfmetrics.registerFont(TTFont("CN", font_path))
        font_name = "CN"
    except Exception:
        # .ttc may need subfontIndex
        try:
            pdfmetrics.registerFont(TTFont("CN", font_path, subfontIndex=0))
            font_name = "CN"
        except Exception as e:
            print("CJK font register failed:", e)
            return

    body = ParagraphStyle("cnb", fontName=font_name, fontSize=10, leading=15, alignment=TA_JUSTIFY, spaceAfter=6)
    h1 = ParagraphStyle("cnh1", fontName=font_name, fontSize=13, leading=18, spaceBefore=12, spaceAfter=8)
    h2 = ParagraphStyle("cnh2", fontName=font_name, fontSize=11, leading=16, spaceBefore=8, spaceAfter=5)
    title = ParagraphStyle("cnt", fontName=font_name, fontSize=14, leading=20, alignment=TA_CENTER, spaceAfter=10)
    story = []
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip():
            story.append(Spacer(1, 4))
            continue
        if line.startswith("# "):
            story.append(P(line[2:].replace("$", ""), title))
        elif line.startswith("## "):
            story.append(P(line[3:].replace("$", ""), h1))
        elif line.startswith("### "):
            story.append(P(line[4:].replace("$", ""), h2))
        elif line.startswith("|") or line.startswith("```") or line.startswith("---"):
            continue
        else:
            t = line
            for a, b in (
                ("**", ""),
                ("`", ""),
                ("$", ""),
                ("\\(", ""),
                ("\\)", ""),
                ("\\[", ""),
                ("\\]", ""),
                ("<", "＜"),
                (">", "＞"),
                ("&", "＆"),
            ):
                t = t.replace(a, b)
            if t.lstrip().startswith("＞"):
                t = t.lstrip()[1:].strip()
            if t.strip():
                story.append(P(t, body))
    doc = SimpleDocTemplate(
        str(out),
        pagesize=letter,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="编译市场信息集（完整中文稿）",
        author="李国聪",
    )
    doc.build(story)
    print("Wrote", out, out.stat().st_size)


if __name__ == "__main__":
    build()
    build_chinese_pdf()
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            PdfReader = None
    if PdfReader:
        r = PdfReader(str(OUT_EN))
        print("English pages:", len(r.pages))
        cn = CN / "main_cn_jf.pdf"
        if cn.exists():
            print("Chinese pages:", len(PdfReader(str(cn)).pages))
