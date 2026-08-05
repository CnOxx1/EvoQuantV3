#!/usr/bin/env python3
"""Generate bilingual EN/ZH PDF from TRANSLATION_BILINGUAL.md (internal reading aid)."""

from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
MD = ROOT / "TRANSLATION_BILINGUAL.md"
OUT = ROOT / "main_bilingual.pdf"
FONT = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"

pdfmetrics.registerFont(TTFont("WQY", FONT, subfontIndex=0))
CJK = "WQY"

EN_BG = HexColor("#F4F7FB")
ZH_BG = HexColor("#F7F8F4")
EN_LABEL = HexColor("#1F4E79")
ZH_LABEL = HexColor("#2E5A3C")
HEAD = HexColor("#111827")
MUTED = HexColor("#6B7280")
RULE = HexColor("#D1D5DB")

_LATEX_MAP = {
    r"\approx": "≈",
    r"\lesssim": "≲",
    r"\ge": "≥",
    r"\le": "≤",
    r"\times": "×",
    r"\circ": "∘",
    r"\mid": "|",
    r"\in": "∈",
    r"\equiv": "≡",
    r"\Delta": "Δ",
    r"\Pi": "Π",
    r"\sigma": "σ",
    r"\tau": "τ",
    r"\varepsilon": "ε",
    r"\bar": "",
    r"\widetilde": "",
    r"\mathcal": "",
    r"\mathrm": "",
    r"\mathbf": "",
    r"\emph": "",
    r"\textbf": "",
    r"\texttt": "",
    r"\cite": "",
    r"\ref": "",
    r"\label": "",
    r"\small": "",
    r"\scriptsize": "",
    r"\%": "%",
    r"\,": " ",
    r"\;": " ",
    r"\!": "",
    r"\ ": " ",
}


def esc(s: str) -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"`([^`]+)`", r'<font face="Courier" size="8">\1</font>', s)
    s = s.replace(r"\(", "").replace(r"\)", "").replace(r"\[", "").replace(r"\]", "")
    for k, v in _LATEX_MAP.items():
        s = s.replace(k, v)
    # \mathcal{F}^{\mathrm{AI}}_t etc. after command strip
    s = re.sub(r"\\[a-zA-Z]+\*?\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("---", "—").replace("--", "–")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="DocTitle",
            fontName=CJK,
            fontSize=14,
            leading=20,
            textColor=HEAD,
            alignment=TA_CENTER,
            spaceAfter=4 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DocSub",
            fontName=CJK,
            fontSize=9,
            leading=13,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=6 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H1",
            fontName=CJK,
            fontSize=12,
            leading=16,
            textColor=HEAD,
            spaceBefore=6 * mm,
            spaceAfter=3 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2",
            fontName=CJK,
            fontSize=10,
            leading=14,
            textColor=HexColor("#374151"),
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyEN",
            fontName=CJK,
            fontSize=8.5,
            leading=12,
            textColor=HEAD,
            alignment=TA_JUSTIFY,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyZH",
            fontName=CJK,
            fontSize=8.5,
            leading=13,
            textColor=HEAD,
            alignment=TA_JUSTIFY,
        )
    )
    styles.add(
        ParagraphStyle(
            name="LabelEN",
            fontName=CJK,
            fontSize=7.5,
            leading=10,
            textColor=EN_LABEL,
            spaceAfter=1 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="LabelZH",
            fontName=CJK,
            fontSize=7.5,
            leading=10,
            textColor=ZH_LABEL,
            spaceAfter=1 * mm,
        )
    )
    styles.add(
        ParagraphStyle(name="Term", fontName=CJK, fontSize=8, leading=11, textColor=HEAD)
    )
    return styles


def pair_block(en: str, zh: str, styles):
    en_cell = [Paragraph("<b>EN</b>", styles["LabelEN"]), Paragraph(esc(en), styles["BodyEN"])]
    zh_cell = [Paragraph("<b>中文</b>", styles["LabelZH"]), Paragraph(esc(zh), styles["BodyZH"])]
    left = Table([[en_cell]], colWidths=[85 * mm])
    left.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), EN_BG),
                ("BOX", (0, 0), (-1, -1), 0.3, HexColor("#C5D4E8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    right = Table([[zh_cell]], colWidths=[85 * mm])
    right.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ZH_BG),
                ("BOX", (0, 0), (-1, -1), 0.3, HexColor("#C9D5C4")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    row = Table([[left, right]], colWidths=[88 * mm, 88 * mm])
    row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ]
        )
    )
    return row


def main() -> int:
    md = MD.read_text(encoding="utf-8")
    styles = build_styles()
    story = [
        Paragraph("ICAIF ’26 论文中英对照 / Bilingual Parallel Reading", styles["DocTitle"]),
        Paragraph(
            "源稿 main.tex（约 7 页）· 正式投稿以英文 PDF 为准 · 左 EN / 右 中文",
            styles["DocSub"],
        ),
        HRFlowable(width="100%", thickness=0.6, color=RULE, spaceAfter=4 * mm),
    ]

    lines = md.splitlines()
    i = 0
    en_buf = None
    zh_buf = None
    term_rows: list[list[str]] = []
    in_term_table = False

    def flush_pair():
        nonlocal en_buf, zh_buf
        if en_buf is not None and zh_buf is not None:
            story.append(pair_block(en_buf, zh_buf, styles))
        elif en_buf is not None:
            story.append(pair_block(en_buf, "（无对应中文）", styles))
        en_buf = None
        zh_buf = None

    def flush_terms():
        nonlocal term_rows, in_term_table
        if not term_rows:
            in_term_table = False
            return
        story.append(Paragraph("0. 关键术语表 / Terminology", styles["H1"]))
        data = [
            [
                Paragraph("<b>English</b>", styles["Term"]),
                Paragraph("<b>中文</b>", styles["Term"]),
                Paragraph("<b>说明</b>", styles["Term"]),
            ]
        ]
        for r in term_rows:
            data.append(
                [
                    Paragraph(esc(r[0]), styles["Term"]),
                    Paragraph(esc(r[1]), styles["Term"]),
                    Paragraph(esc(r[2]), styles["Term"]),
                ]
            )
        t = Table(data, colWidths=[55 * mm, 55 * mm, 66 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#E5E7EB")),
                    ("GRID", (0, 0), (-1, -1), 0.3, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, HexColor("#FAFAFA")]),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 3 * mm))
        term_rows = []
        in_term_table = False

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("| English") or (in_term_table and line.strip().startswith("|")):
            if "---" in line and in_term_table:
                i += 1
                continue
            if line.strip().startswith("| English"):
                in_term_table = True
                i += 1
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and not set(cells[0]) <= {"-", ":"}:
                term_rows.append(cells[:3])
            i += 1
            continue
        if in_term_table:
            flush_terms()

        if line.startswith("## "):
            flush_pair()
            title = line[3:].strip()
            if title.startswith("0."):
                i += 1
                continue
            story.append(Paragraph(esc(title), styles["H1"]))
            i += 1
            continue
        if line.startswith("### "):
            flush_pair()
            story.append(Paragraph(esc(line[4:].strip()), styles["H2"]))
            i += 1
            continue
        if line.startswith("**EN:**"):
            flush_pair()
            en_buf = line[len("**EN:**") :].strip()
            i += 1
            while (
                i < len(lines)
                and lines[i].strip()
                and not lines[i].startswith("**中文")
                and not lines[i].startswith("**EN")
                and not lines[i].startswith("#")
                and not lines[i].startswith("---")
            ):
                en_buf += " " + lines[i].strip()
                i += 1
            continue
        if line.startswith("**中文:**"):
            zh_buf = line[len("**中文:**") :].strip()
            i += 1
            while (
                i < len(lines)
                and lines[i].strip()
                and not lines[i].startswith("**EN")
                and not lines[i].startswith("**中文")
                and not lines[i].startswith("#")
                and not lines[i].startswith("---")
            ):
                zh_buf += " " + lines[i].strip()
                i += 1
            flush_pair()
            continue
        if line.startswith(">") or line.strip() == "---":
            flush_pair()
            i += 1
            continue
        i += 1

    flush_pair()
    flush_terms()

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(CJK, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 12 * mm, "ICAIF ’26 bilingual reading aid · not for submission")
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"{doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title="ICAIF26 Bilingual EN/ZH",
        author="EvoQuant (internal)",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes, last page marker {doc.page})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
