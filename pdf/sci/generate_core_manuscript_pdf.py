#!/usr/bin/env python3
"""Render the World-Model-First core Chinese manuscript PDF with figures.

Source: pdf/cn/main_cn_core.md
Output: pdf/cn/main_cn_core.pdf (+ mirror under pdf/ and pdf/original/)
"""

from __future__ import annotations

import re
from pathlib import Path

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
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
CN = ROOT / "cn"
FIG = ROOT / "figures"
SCI = Path(__file__).resolve().parent
MD = CN / "main_cn_core.md"
OUT = CN / "main_cn_core.pdf"
OUT_MIRROR = ROOT / "main_cn_core.pdf"
OUT_ORIG = ROOT / "original" / "main_cn_core.pdf"

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def register_font() -> str:
    for path, kwargs in (
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", {"subfontIndex": 0}),
        ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", {}),
    ):
        if not Path(path).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("CoreCJK", path, **kwargs))
            return "CoreCJK"
        except Exception:
            continue
    raise SystemExit("No CJK font available")


def latex_to_rl(s: str) -> str:
    """Lightweight LaTeX → ReportLab markup for inline / display math."""
    if not s:
        return s
    out = s
    # Escape XML specials first (before we inject tags)
    out = out.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    repl = [
        (r"\\mathrm\{([^}]+)\}", r"\1"),
        (r"\\mathbb\{([^}]+)\}", r"\1"),
        (r"\\mathcal\{([^}]+)\}", r"\1"),
        (r"\\mathbf\{([^}]+)\}", r"<b>\1</b>"),
        (r"\\text\{([^}]+)\}", r"\1"),
        (r"\\hat\{([^}]+)\}", r"\1̂"),
        (r"\\widetilde\{([^}]+)\}", r"\1̃"),
        (r"\\tilde\{([^}]+)\}", r"\1̃"),
        (r"\\bar\{([^}]+)\}", r"\1̄"),
        (r"\\exp", "exp"),
        (r"\\log", "log"),
        (r"\\max", "max"),
        (r"\\min", "min"),
        (r"\\arg", "arg"),
        (r"\\sum", "Σ"),
        (r"\\prod", "Π"),
        (r"\\times", "×"),
        (r"\\cdot", "·"),
        (r"\\circ", "∘"),
        (r"\\le(?!f)", "≤"),
        (r"\\ge", "≥"),
        (r"\\leq", "≤"),
        (r"\\geq", "≥"),
        (r"\\neq", "≠"),
        (r"\\approx", "≈"),
        (r"\\rightarrow", "→"),
        (r"\\to\b", "→"),
        (r"\\ldots", "…"),
        (r"\\cdots", "⋯"),
        (r"\\infty", "∞"),
        (r"\\gamma", "γ"),
        (r"\\omega", "ω"),
        (r"\\ell", "ℓ"),
        (r"\\nu", "ν"),
        (r"\\eta", "η"),
        (r"\\sigma", "σ"),
        (r"\\Delta", "Δ"),
        (r"\\Phi", "Φ"),
        (r"\\phi", "φ"),
        (r"\\Pi", "Π"),
        (r"\\bigl", ""),
        (r"\\bigr", ""),
        (r"\\big", ""),
        (r"\\left", ""),
        (r"\\right", ""),
        (r"\\,", " "),
        (r"\\!", ""),
        (r"\\;", " "),
        (r"\\quad", "  "),
        (r"\\qquad", "   "),
        (r"\\%", "%"),
    ]
    for a, b in repl:
        out = re.sub(a, b, out)
    out = re.sub(r"([A-Za-zΔΣΠΦα-ω])_\{([^}]+)\}", r"\1<sub>\2</sub>", out)
    out = re.sub(r"([A-Za-zΔΣΠΦα-ω])\^\{([^}]+)\}", r"\1<sup>\2</sup>", out)
    out = re.sub(r"([A-Za-zΔΣΠΦα-ω])_([0-9A-Za-z]+)", r"\1<sub>\2</sub>", out)
    out = re.sub(r"([A-Za-zΔΣΠΦα-ω])\^([0-9A-Za-z*+\-]+)", r"\1<sup>\2</sup>", out)
    out = out.replace("{", "").replace("}", "")
    return out


def md_inline(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\$\$([^$]+)\$\$", lambda m: latex_to_rl(m.group(1)), s)
    s = re.sub(r"\$([^$]+)\$", lambda m: latex_to_rl(m.group(1)), s)
    s = re.sub(r"\\\((.+?)\\\)", lambda m: latex_to_rl(m.group(1)), s)
    s = re.sub(r"\\\[(.+?)\\\]", lambda m: latex_to_rl(m.group(1)), s)
    # Escape remaining XML outside math (math already escaped)
    # Protect tags temporarily
    placeholders = []

    def _park(m):
        placeholders.append(m.group(0))
        return f"@@TAG{len(placeholders)-1}@@"

    s = re.sub(r"</?(?:sub|sup|b|font)[^>]*>", _park, s)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for i, tag in enumerate(placeholders):
        s = s.replace(f"@@TAG{i}@@", tag)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<font face='Courier' size='8'>\1</font>", s)
    return s


def styles(font: str):
    return {
        "title": ParagraphStyle("t", fontName=font, fontSize=14, leading=20, alignment=TA_CENTER, spaceAfter=8),
        "author": ParagraphStyle("a", fontName=font, fontSize=11, alignment=TA_CENTER, spaceAfter=2),
        "note": ParagraphStyle("n", fontName=font, fontSize=8.5, leading=12, textColor=colors.HexColor("#444"), spaceAfter=8),
        "h1": ParagraphStyle("h1", fontName=font, fontSize=12.5, leading=17, spaceBefore=14, spaceAfter=7),
        "h2": ParagraphStyle("h2", fontName=font, fontSize=11, leading=15, spaceBefore=10, spaceAfter=5),
        "h3": ParagraphStyle("h3", fontName=font, fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle(
            "b", fontName=font, fontSize=9.5, leading=14, alignment=TA_JUSTIFY, firstLineIndent=16, spaceAfter=5
        ),
        "eq": ParagraphStyle("eq", fontName=font, fontSize=10, leading=14, alignment=TA_CENTER, spaceBefore=4, spaceAfter=4),
        "caption": ParagraphStyle("cap", fontName=font, fontSize=8.5, leading=11, alignment=TA_CENTER, spaceBefore=2, spaceAfter=10),
        "bullet": ParagraphStyle("bu", fontName=font, fontSize=9.5, leading=13, leftIndent=14, spaceAfter=3),
    }


def fig(name: str, width=6.2 * inch, ratio=0.48):
    path = FIG / name
    if not path.exists():
        return None
    return Image(str(path), width=width, height=width * ratio)


FIGURE_SLOTS = [
    # (after heading substring, image, caption)
    ("4.1 分层架构", "fig14_wm_pipeline.png", "图 14. World-Model-First 编译流水线：原始证据带 → 治理 → 编译世界 → AI 判断与弃权。"),
    ("6.1 数据", "fig11_band_readiness.png", "图 11. 真实 PIT 面板上的证据带 readiness：耐久带（exchange/macro/alternative）持续可用，稀缺带右删失。"),
    ("7.1 流水线与世界质量路径", "fig12_wmi_acwmi_paths.png", "图 12. PIT 面板上的 WMI / ACWMI 路径与 IS/OOS 切点。"),
    ("7.2 OOS 经济价值", "fig1_architecture.png", "图 1. OOS 累计财富路径（选择性策略 vs 基准）。"),
    ("7.2 OOS 经济价值", "fig2_coverage_compare.png", "图 2. OOS Sharpe 与确定性等价（CE）对比。"),
    ("7.3 厚 vs 薄世界", "fig15_thin_thick.png", "图 15. 薄世界 vs 厚世界：世界质量与 OOS 经济价值。"),
    ("7.4 LOBO", "fig9_lobo_decomposition.png", "图 9. LOBO 内容通道 vs 门控通道分解。"),
    ("7.5 长回测", "fig10_longspan_by_year.png", "图 10. 2017–2026 长回测分年年化收益（外部有效性锚）。"),
    ("7.6 成本", "fig13_cost_frontier.png", "图 13. 交易成本敏感性：编译世界策略 vs 动量 / 始终做多。"),
]


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("CoreCJK", 8)
    canvas.drawString(0.85 * inch, letter[1] - 0.5 * inch, "李国聪 — 世界模型优先与 AI 市场分析")
    canvas.drawCentredString(letter[0] / 2, 0.5 * inch, str(doc.page))
    canvas.restoreState()


def parse_md_table(lines: list[str], i: int) -> tuple[list[list[str]], int]:
    rows = []
    while i < len(lines) and lines[i].strip().startswith("|"):
        raw = lines[i].strip().strip("|")
        cells = [c.strip() for c in raw.split("|")]
        if all(re.fullmatch(r":?-+:?", c.replace(" ", "")) for c in cells):
            i += 1
            continue
        rows.append(cells)
        i += 1
    return rows, i


def make_table(rows: list[list[str]], font: str):
    if not rows:
        return Spacer(1, 1)
    n = max(len(r) for r in rows)
    rows = [r + [""] * (n - len(r)) for r in rows]
    width = 6.5 * inch
    col_w = [width / n] * n
    style_h = ParagraphStyle("th", fontName=font, fontSize=8, leading=10)
    style_b = ParagraphStyle("tb", fontName=font, fontSize=7.5, leading=9.5)
    data = []
    for ri, row in enumerate(rows):
        data.append([Paragraph(md_inline(c), style_h if ri == 0 else style_b) for c in row])
    t = Table(data, colWidths=col_w, hAlign="CENTER", repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#666")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return t


def build() -> Path:
    font = register_font()
    S = styles(font)
    text = MD.read_text(encoding="utf-8")
    lines = text.splitlines()
    story = []
    inserted: set[str] = set()
    i = 0
    in_code = False
    display_buf: list[str] = []
    in_display = False

    def maybe_insert_figures(heading: str):
        for key, img, cap in FIGURE_SLOTS:
            token = f"{key}::{img}"
            if token in inserted:
                continue
            if key in heading:
                im = fig(img)
                if im is not None:
                    story.append(KeepTogether([im, Paragraph(cap, S["caption"])]))
                    inserted.add(token)

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if in_code:
            # keep code as mono-ish paragraph
            story.append(Paragraph(line.replace("<", "&lt;").replace(">", "&gt;") or " ", S["bullet"]))
            i += 1
            continue

        # display math \[ ... \]
        if line.strip() == r"\[" or line.strip().startswith("$$"):
            in_display = True
            display_buf = []
            if line.strip().startswith("$$") and line.strip().endswith("$$") and len(line.strip()) > 4:
                story.append(Paragraph(latex_to_rl(line.strip().strip("$")), S["eq"]))
                in_display = False
            i += 1
            continue
        if in_display:
            if line.strip() == r"\]" or line.strip() == "$$":
                story.append(Paragraph(latex_to_rl(" ".join(display_buf)), S["eq"]))
                in_display = False
                display_buf = []
            else:
                display_buf.append(line.strip())
            i += 1
            continue

        if not line.strip():
            story.append(Spacer(1, 3))
            i += 1
            continue
        if line.startswith("# "):
            story.append(Paragraph(md_inline(line[2:]), S["title"]))
            i += 1
            continue
        if line.startswith("## "):
            h = line[3:].strip()
            story.append(Paragraph(md_inline(h), S["h1"]))
            maybe_insert_figures(h)
            i += 1
            continue
        if line.startswith("### "):
            h = line[4:].strip()
            story.append(Paragraph(md_inline(h), S["h2"]))
            maybe_insert_figures(h)
            i += 1
            continue
        if line.strip().startswith("|"):
            rows, i = parse_md_table(lines, i)
            story.append(make_table(rows, font))
            story.append(Spacer(1, 6))
            continue
        if line.strip() == "---":
            i += 1
            continue
        if line.startswith("> "):
            story.append(Paragraph(md_inline(line[2:]), S["note"]))
            i += 1
            continue
        if line.startswith("- ") or line.startswith("* "):
            story.append(Paragraph("• " + md_inline(line[2:]), S["bullet"]))
            i += 1
            continue
        # author lines without indent markers
        if line.startswith("**李") or line.startswith("独立研究者"):
            story.append(Paragraph(md_inline(line), S["author"]))
            i += 1
            continue
        story.append(Paragraph(md_inline(line), S["body"]))
        i += 1

    # ensure key figures appear even if heading match failed
    for key, img, cap in FIGURE_SLOTS:
        token = f"{key}::{img}"
        if token not in inserted:
            im = fig(img)
            if im is not None:
                story.append(KeepTogether([im, Paragraph(cap, S["caption"])]))
                inserted.add(token)

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="从模型优先到世界模型优先",
        author="李国聪",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    OUT_MIRROR.write_bytes(OUT.read_bytes())
    OUT_ORIG.parent.mkdir(parents=True, exist_ok=True)
    OUT_ORIG.write_bytes(OUT.read_bytes())
    print("Wrote", OUT, OUT.stat().st_size)
    return OUT


if __name__ == "__main__":
    build()
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    print("pages:", len(PdfReader(str(OUT)).pages))
