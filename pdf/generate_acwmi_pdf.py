#!/usr/bin/env python3
"""Generate a Chinese academic PDF for the RCA-WM theory paper."""

from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "main_cn_acwmi.md"
PDF_PATH = ROOT / "main_cn_acwmi.pdf"
TXT_PATH = ROOT / "main_cn_acwmi.txt"

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]


def register_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("CN", path))
            return "CN"
    raise RuntimeError("No Chinese font found")


def md_inline_to_reportlab(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', text)
    text = re.sub(r"\[\^(\d+)\]", r"<super>\1</super>", text)
    # Keep LaTeX-ish math readable in PDF
    text = text.replace("\\(", "").replace("\\)", "")
    text = text.replace("\\[", "").replace("\\]", "")
    text = text.replace("\\mathrm", "").replace("\\big", "")
    text = text.replace("\\le", "≤").replace("\\ge", "≥")
    text = text.replace("\\times", "×").replace("\\cdot", "·")
    text = text.replace("\\to", "→").replace("\\circ", " ∘ ")
    text = text.replace("\\in", "∈").replace("\\subseteq", "⊆")
    text = text.replace("\\dots", "...").replace("\\ldots", "...")
    text = text.replace("\\,", " ").replace("\\;", " ").replace("\\!", "")
    text = text.replace("\\quad", " ").replace("\\qquad", " ")
    text = text.replace("\\alpha", "α").replace("\\beta", "β")
    text = text.replace("\\gamma", "γ").replace("\\theta", "θ")
    text = text.replace("\\lambda", "λ").replace("\\eta", "η")
    text = text.replace("\\rho", "ρ").replace("\\kappa", "κ")
    text = text.replace("\\Psi", "Ψ").replace("\\Gamma", "Γ")
    text = text.replace("\\Pi", "Π").replace("\\Phi", "Φ")
    text = text.replace("\\mathcal{L}", "L").replace("\\mathcal{A}", "A")
    text = text.replace("\\mathcal{E}", "E").replace("\\mathcal{M}", "M")
    text = text.replace("\\mathcal{I}", "I").replace("\\mathcal{S}", "S")
    text = text.replace("\\mathcal{G}", "G").replace("\\widehat", "")
    text = text.replace("\\tilde{S}", "S̃").replace("\\tilde{u}", "ũ")
    text = text.replace("\\tilde", "~").replace("\\bar{c}", "c̄").replace("\\bar", "")
    text = text.replace("\\exp", "exp").replace("\\max", "max")
    text = text.replace("\\min", "min").replace("\\arg", "arg")
    text = text.replace("\\mathbb{E}", "E")
    text = re.sub(r"\\mathrm\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\\text\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\\mathbf\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\^\{([^}]+)\}", r"^(\1)", text)
    text = re.sub(r"_\{([^}]+)\}", r"_\1", text)
    text = text.replace("{", "").replace("}", "")
    return text


def build_styles(font: str) -> dict:
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "CNTitle",
            parent=styles["Title"],
            fontName=font,
            fontSize=16,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "CNSubtitle",
            parent=styles["Normal"],
            fontName=font,
            fontSize=12,
            leading=18,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "CNMeta",
            parent=styles["Normal"],
            fontName=font,
            fontSize=9,
            leading=14,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "CNH1",
            parent=styles["Heading1"],
            fontName=font,
            fontSize=13,
            leading=20,
            spaceBefore=14,
            spaceAfter=8,
            alignment=TA_LEFT,
        ),
        "h2": ParagraphStyle(
            "CNH2",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=11.5,
            leading=18,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "CNH3",
            parent=styles["Heading3"],
            fontName=font,
            fontSize=10.5,
            leading=16,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "CNBody",
            parent=styles["Normal"],
            fontName=font,
            fontSize=10,
            leading=16,
            alignment=TA_JUSTIFY,
            firstLineIndent=18,
            spaceAfter=6,
        ),
        "abstract": ParagraphStyle(
            "CNAbstract",
            parent=styles["Normal"],
            fontName=font,
            fontSize=9.5,
            leading=15,
            alignment=TA_JUSTIFY,
            firstLineIndent=0,
            spaceAfter=6,
        ),
        "quote": ParagraphStyle(
            "CNQuote",
            parent=styles["Normal"],
            fontName=font,
            fontSize=9.5,
            leading=15,
            leftIndent=16,
            rightIndent=16,
            textColor="#222222",
            spaceBefore=4,
            spaceAfter=8,
        ),
        "bullet": ParagraphStyle(
            "CNBullet",
            parent=styles["Normal"],
            fontName=font,
            fontSize=10,
            leading=15,
            leftIndent=18,
            spaceAfter=3,
        ),
        "formula": ParagraphStyle(
            "CNFormula",
            parent=styles["Normal"],
            fontName=font,
            fontSize=9.5,
            leading=14,
            alignment=TA_CENTER,
            spaceBefore=4,
            spaceAfter=4,
        ),
        "table": ParagraphStyle(
            "CNTable",
            parent=styles["Normal"],
            fontName=font,
            fontSize=8.5,
            leading=12,
            spaceAfter=2,
        ),
        "footer": ParagraphStyle(
            "CNFooter",
            parent=styles["Normal"],
            fontName=font,
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
        ),
    }


def parse_markdown(md: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    lines = md.splitlines()
    i = 0
    buf: list[str] = []
    mode = "body"

    def flush() -> None:
        nonlocal buf, mode
        if not buf:
            return
        text = "\n".join(buf).strip()
        if text:
            blocks.append((mode, text))
        buf = []
        mode = "body"

    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            flush()
            i += 1
            continue
        if line.startswith("# "):
            flush()
            blocks.append(("title", line[2:].strip()))
            i += 1
            continue
        if line.startswith("## "):
            flush()
            blocks.append(("h1", line[3:].strip()))
            i += 1
            continue
        if line.startswith("### "):
            flush()
            blocks.append(("h2", line[4:].strip()))
            i += 1
            continue
        if line.startswith("> "):
            flush()
            quote_lines = [line[2:]]
            i += 1
            while i < len(lines) and lines[i].startswith("> "):
                quote_lines.append(lines[i][2:])
                i += 1
            blocks.append(("quote", " ".join(quote_lines)))
            continue
        if line.startswith("$$") or line.strip() == "\\[":
            flush()
            formula = []
            if line.startswith("$$"):
                if line.strip() != "$$":
                    formula.append(line.replace("$$", "").strip())
                i += 1
                while i < len(lines) and not lines[i].startswith("$$"):
                    formula.append(lines[i])
                    i += 1
                i += 1
            else:
                i += 1
                while i < len(lines) and lines[i].strip() != "\\]":
                    formula.append(lines[i])
                    i += 1
                i += 1
            blocks.append(("formula", " ".join(x.strip() for x in formula)))
            continue
        if re.match(r"^\$\$.*\$\$$", line.strip()):
            flush()
            blocks.append(("formula", line.strip()[2:-2]))
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and set(lines[i + 1].replace("|", "").strip()) <= {"-", ":"}:
            flush()
            table_lines = [line]
            i += 1
            # skip separator
            i += 1
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            blocks.append(("table", "\n".join(table_lines)))
            continue
        if re.match(r"^\d+\.\s+", line) or line.startswith("- "):
            flush()
            item_lines = [line]
            i += 1
            while i < len(lines) and (re.match(r"^\d+\.\s+", lines[i]) or lines[i].startswith("- ") or lines[i].startswith("  ")):
                item_lines.append(lines[i])
                i += 1
            blocks.append(("list", "\n".join(item_lines)))
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        # display math on its own indented/centered line starting with \[ already handled
        if line.strip().startswith("\\[") is False and (
            line.strip().startswith("W_")
            or line.strip().startswith("mathrm")
            or "ACWMI" in line and "=" in line and len(line) < 20
        ):
            pass
        buf.append(line)
        i += 1
    flush()
    return blocks


def table_to_paragraphs(table_text: str, style) -> list:
    rows = []
    for line in table_text.splitlines():
        cols = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cols)
    out = []
    for idx, row in enumerate(rows):
        prefix = "表行: " if idx == 0 else "· "
        out.append(Paragraph(md_inline_to_reportlab(prefix + " | ".join(row)), style))
    out.append(Spacer(1, 6))
    return out


def md_to_flowables(md: str, styles: dict):
    story = []
    blocks = parse_markdown(md)
    seen_title = 0
    for kind, text in blocks:
        if kind == "title":
            seen_title += 1
            style = styles["title"] if seen_title == 1 else styles["subtitle"]
            story.append(Paragraph(md_inline_to_reportlab(text), style))
            continue
        if kind == "h1":
            if text.startswith("附录") or text == "参考文献":
                story.append(PageBreak())
            story.append(Paragraph(md_inline_to_reportlab(text), styles["h1"]))
            continue
        if kind == "h2":
            story.append(Paragraph(md_inline_to_reportlab(text), styles["h2"]))
            continue
        if kind == "quote":
            story.append(Paragraph("「" + md_inline_to_reportlab(text) + "」", styles["quote"]))
            continue
        if kind == "formula":
            story.append(Paragraph(md_inline_to_reportlab(text), styles["formula"]))
            continue
        if kind == "table":
            story.extend(table_to_paragraphs(text, styles["table"]))
            continue
        if kind == "list":
            for line in text.splitlines():
                if not line.strip():
                    continue
                story.append(Paragraph(md_inline_to_reportlab(line), styles["bullet"]))
            continue
        # meta lines without indent
        if text.startswith("**李") or text.startswith("（") or text.startswith("**英文") or text.startswith("**中图") or text.startswith("**文献") or text.startswith("**JEL") or text.startswith("**关键词") or text.startswith("**Abstract") or text.startswith("**Key words"):
            story.append(Paragraph(md_inline_to_reportlab(text), styles["meta"]))
            continue
        if text.startswith("**摘要") or text.startswith("既有研究") or text.startswith("Prior work"):
            story.append(Paragraph(md_inline_to_reportlab(text), styles["abstract"]))
            continue
        story.append(Paragraph(md_inline_to_reportlab(text), styles["body"]))
    return story


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("CN", 8)
    canvas.drawCentredString(A4[0] / 2, 1.2 * cm, f"— {doc.page} —")
    canvas.restoreState()


def write_txt(md: str) -> None:
    # plain-ish text for repo parity with earlier papers
    text = md
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = text.replace("\\(", "").replace("\\)", "").replace("\\[", "").replace("\\]", "")
    TXT_PATH.write_text(text, encoding="utf-8")


def main() -> None:
    font = register_font()
    styles = build_styles(font)
    md = MD_PATH.read_text(encoding="utf-8")
    write_txt(md)

    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2.0 * cm,
        bottomMargin=2.0 * cm,
        title="从三维乘积指数到条件化自适应世界模型",
        author="李国聪",
    )
    story = md_to_flowables(md, styles)
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"Wrote {PDF_PATH} ({PDF_PATH.stat().st_size} bytes)")
    print(f"Wrote {TXT_PATH} ({TXT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
