#!/usr/bin/env python3
"""Render World-Model-First core Chinese manuscript with readable math + layout.

Source: pdf/cn/main_cn_core.md
Outputs: pdf/cn/main_cn_core.pdf (+ mirrors)

Design choices (no system TeX available):
- Body text is LEFT-aligned (ReportLab JUSTIFY creates huge CJK/Latin gaps).
- Display math is rendered via Matplotlib mathtext → PNG, then embedded.
- Inline math is converted with a brace-aware LaTeX subset → ReportLab markup.
- Figures are placed only where Markdown images appear (no heading-auto insert).
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
CN = ROOT / "cn"
FIG = ROOT / "figures"
MD = CN / "main_cn_core.md"
OUT = CN / "main_cn_core.pdf"
OUT_MIRROR = ROOT / "main_cn_core.pdf"
OUT_ORIG = ROOT / "original" / "main_cn_core.pdf"
EQ_CACHE = ROOT / "figures" / "_eq_cache"
EQ_CACHE.mkdir(parents=True, exist_ok=True)

CONTENT_W = 6.3 * inch


def register_font() -> str:
    # Latin/math face for inline formulas (CJK fonts lack many math glyphs / subscripts)
    try:
        pdfmetrics.registerFont(TTFont("MathLatin", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"))
    except Exception:
        pdfmetrics.registerFont(TTFont("MathLatin", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    for path, kwargs in (
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", {"subfontIndex": 0}),
        ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", {}),
    ):
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("CoreCJK", path, **kwargs))
                return "CoreCJK"
            except Exception:
                continue
    raise SystemExit("No CJK font available")


# ---------------------------------------------------------------------------
# Brace-aware LaTeX helpers
# ---------------------------------------------------------------------------

def _take_brace(s: str, i: int) -> tuple[str, int]:
    """If s[i]=='{', return (inner, index_after_closing); else ('', i)."""
    if i >= len(s) or s[i] != "{":
        return "", i
    depth = 0
    j = i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1 : j], j + 1
        j += 1
    return s[i + 1 :], len(s)


def _take_group(s: str, i: int) -> tuple[str, int]:
    """Take {group} or a single token after command."""
    while i < len(s) and s[i].isspace():
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        return _take_brace(s, i)
    # single char / command token
    if s[i] == "\\":
        m = re.match(r"\\[A-Za-z]+", s[i:])
        if m:
            return m.group(0), i + len(m.group(0))
        return s[i : i + 2], i + 2
    return s[i], i + 1


_GREEK = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "eta": "η",
    "theta": "θ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "pi": "π",
    "rho": "ρ",
    "sigma": "σ",
    "tau": "τ",
    "phi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Theta": "Θ",
    "Lambda": "Λ",
    "Xi": "Ξ",
    "Pi": "Π",
    "Sigma": "Σ",
    "Phi": "Φ",
    "Psi": "Ψ",
    "Omega": "Ω",
    "ell": "ℓ",
    "infty": "∞",
}

_SUB = str.maketrans(
    {
        "0": "₀",
        "1": "₁",
        "2": "₂",
        "3": "₃",
        "4": "₄",
        "5": "₅",
        "6": "₆",
        "7": "₇",
        "8": "₈",
        "9": "₉",
        "+": "₊",
        "-": "₋",
        "=": "₌",
        "(": "₍",
        ")": "₎",
        "a": "ₐ",
        "e": "ₑ",
        "h": "ₕ",
        "i": "ᵢ",
        "j": "ⱼ",
        "k": "ₖ",
        "l": "ₗ",
        "m": "ₘ",
        "n": "ₙ",
        "o": "ₒ",
        "p": "ₚ",
        "r": "ᵣ",
        "s": "ₛ",
        "t": "ₜ",
        "u": "ᵤ",
        "v": "ᵥ",
        "x": "ₓ",
    }
)
_SUP = str.maketrans(
    {
        "0": "⁰",
        "1": "¹",
        "2": "²",
        "3": "³",
        "4": "⁴",
        "5": "⁵",
        "6": "⁶",
        "7": "⁷",
        "8": "⁸",
        "9": "⁹",
        "+": "⁺",
        "-": "⁻",
        "=": "⁼",
        "(": "⁽",
        ")": "⁾",
        "n": "ⁿ",
        "i": "ⁱ",
        "*": "⁎",
    }
)


def _to_sub(s: str) -> str:
    # Prefer unicode subscripts (ReportLab <sub> overlaps badly with CJK fonts)
    out = []
    for ch in s:
        mapped = ch.translate(_SUB)
        if mapped != ch:
            out.append(mapped)
            continue
        low = ch.lower()
        mapped2 = low.translate(_SUB)
        if ch.isalpha() and mapped2 != low:
            out.append(mapped2)
        else:
            out.append(ch)
    return "".join(out)


def _to_sup(s: str) -> str:
    out = []
    for ch in s:
        mapped = ch.translate(_SUP)
        if mapped != ch:
            out.append(mapped)
        else:
            out.append(ch)
    return "".join(out)


_OPS = {
    "times": "×",
    "cdot": "·",
    "circ": "∘",
    "ast": "*",
    "star": "⋆",
    "pm": "±",
    "mp": "∓",
    "leq": "≤",
    "le": "≤",
    "geq": "≥",
    "ge": "≥",
    "neq": "≠",
    "approx": "≈",
    "sim": "∼",
    "propto": "∝",
    "rightarrow": "→",
    "to": "→",
    "leftarrow": "←",
    "Rightarrow": "⇒",
    "mapsto": "↦",
    "ldots": "…",
    "cdots": "⋯",
    "mid": "|",
    "vert": "|",
    "Vert": "‖",
    "setminus": "∖",
    "in": "∈",
    "notin": "∉",
    "subset": "⊂",
    "subseteq": "⊆",
    "cup": "∪",
    "cap": "∩",
    "forall": "∀",
    "exists": "∃",
    "partial": "∂",
    "nabla": "∇",
    "sum": "Σ",
    "prod": "Π",
    "int": "∫",
    "exp": "exp",
    "log": "log",
    "ln": "ln",
    "max": "max",
    "min": "min",
    "arg": "arg",
    "sin": "sin",
    "cos": "cos",
    "tan": "tan",
    "det": "det",
    "dim": "dim",
    "Pr": "Pr",
    "quad": "  ",
    "qquad": "    ",
    ",": " ",
    ";": " ",
    "!": "",
    "%": "%",
}


def latex_to_rl(tex: str) -> str:
    """Convert a LaTeX math fragment to ReportLab-friendly markup (Unicode + sub/sup)."""
    s = tex.strip()
    # normalize common wrappers
    for junk in (
        r"\bigl",
        r"\bigr",
        r"\Bigl",
        r"\Bigr",
        r"\biggl",
        r"\biggr",
        r"\left",
        r"\right",
        r"\big",
        r"\Big",
        r"\bigg",
        r"\Bigg",
        r"\!",
    ):
        s = s.replace(junk, "")
    s = s.replace(r"\,", " ").replace(r"\;", " ").replace(r"\:", " ")

    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\":
            # \|
            if i + 1 < n and s[i + 1] == "|":
                out.append("‖")
                i += 2
                continue
            # \{ \}
            if i + 1 < n and s[i + 1] in "{}":
                out.append(s[i + 1])
                i += 2
                continue
            m = re.match(r"\\([A-Za-z]+)", s[i:])
            if not m:
                out.append(s[i + 1] if i + 1 < n else "")
                i += 2
                continue
            cmd = m.group(1)
            i += m.end()
            # skip star variants
            if i < n and s[i] == "*":
                i += 1

            if cmd in ("mathrm", "operatorname", "text", "textbf", "mathit", "mathbf", "mathbb", "mathcal", "mathsf"):
                arg, i = _take_group(s, i)
                # recurse inner
                inner = latex_to_rl(arg)
                if cmd in ("mathbf", "textbf"):
                    out.append(f"<b>{inner}</b>")
                else:
                    out.append(inner)
                continue
            if cmd == "frac":
                num, i = _take_group(s, i)
                den, i = _take_group(s, i)
                out.append(f"({latex_to_rl(num)})/({latex_to_rl(den)})")
                continue
            if cmd in ("sqrt",):
                arg, i = _take_group(s, i)
                out.append(f"√({latex_to_rl(arg)})")
                continue
            if cmd in ("hat", "tilde", "bar", "widetilde", "widehat", "dot", "ddot"):
                arg, i = _take_group(s, i)
                marks = {
                    "hat": "̂",
                    "widehat": "̂",
                    "tilde": "̃",
                    "widetilde": "̃",
                    "bar": "̄",
                    "dot": "̇",
                    "ddot": "̈",
                }
                out.append(latex_to_rl(arg) + marks.get(cmd, ""))
                continue
            if cmd == "overline":
                arg, i = _take_group(s, i)
                out.append(latex_to_rl(arg) + "̄")
                continue
            if cmd in ("mathbb",):
                arg, i = _take_group(s, i)
                out.append(latex_to_rl(arg))
                continue
            if cmd in _GREEK:
                out.append(_GREEK[cmd])
                continue
            if cmd in _OPS:
                out.append(_OPS[cmd])
                continue
            # unknown command: drop slash, keep name if short else ignore
            if cmd in ("hspace", "vspace", "label", "tag"):
                _arg, i = _take_group(s, i)
                continue
            out.append(cmd)
            continue

        if ch == "^":
            arg, i = _take_group(s, i + 1)
            inner = latex_to_rl(arg)
            out.append(f"<super>{inner}</super>")
            continue
        if ch == "_":
            arg, i = _take_group(s, i + 1)
            inner = latex_to_rl(arg)
            out.append(f"<sub>{inner}</sub>")
            continue
        if ch in "{}":
            i += 1
            continue
        if ch == "&":
            out.append("&amp;")
            i += 1
            continue
        if ch == "<":
            out.append("&lt;")
            i += 1
            continue
        if ch == ">":
            out.append("&gt;")
            i += 1
            continue
        if ch == "~":
            out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1

    text = "".join(out)
    # collapse excess spaces
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def latex_for_mathtext(tex: str) -> str:
    """Simplify LaTeX enough for Matplotlib mathtext (no \\displaystyle)."""
    s = tex.strip()
    # norms / bars before stripping \left\right
    s = s.replace(r"\left\|", r"\|").replace(r"\right\|", r"\|")
    s = s.replace(r"\Vert", r"\|").replace(r"\vert", "|")
    for junk in (
        r"\bigl",
        r"\bigr",
        r"\Bigl",
        r"\Bigr",
        r"\biggl",
        r"\biggr",
        r"\left",
        r"\right",
        r"\big",
        r"\Big",
        r"\bigg",
        r"\Bigg",
        r"\!",
        r"\,",
        r"\;",
        r"\:",
        r"\quad",
        r"\qquad",
    ):
        s = s.replace(junk, " ")
    s = re.sub(r"\\mathbb\{([^}]+)\}", lambda m: m.group(1), s)
    s = re.sub(r"\\mathcal\{([^}]+)\}", lambda m: m.group(1), s)
    s = re.sub(r"\\text\{([^}]+)\}", lambda m: r"\mathrm{" + m.group(1) + "}", s)
    s = s.replace(r"\mid", "|").replace(r"\setminus", r"\backslash")
    s = s.replace(r"\star", "*").replace(r"\le", r"\leq").replace(r"\ge", r"\geq")
    s = re.sub(r"\\widehat\{([^}]+)\}", lambda m: r"\hat{" + m.group(1) + "}", s)
    s = re.sub(r"\\widetilde\{([^}]+)\}", lambda m: r"\tilde{" + m.group(1) + "}", s)
    # mathtext often chokes on \|...\|; use |...|
    s = re.sub(r"\\\|(.+?)\\\|", r"|{\1}|", s)
    s = s.replace(r"\#", "#").replace("#", r"\#")
    s = re.sub(r"\s+", " ", s).strip()
    # trailing punctuation outside math looks better kept
    return s


def render_display_eq(tex: str, eqno: int | None = None) -> Path | None:
    """Render display equation with matplotlib; return PNG path or None on failure."""
    clean = latex_for_mathtext(tex)
    key = hashlib.md5(clean.encode("utf-8")).hexdigest()[:16]
    path = EQ_CACHE / f"eq_{key}.png"
    if path.exists() and path.stat().st_size > 2000:
        # tiny files are usually failed Unicode fallbacks — regenerate
        return path
    # Matplotlib mathtext in this environment does not support \displaystyle
    label = f"${clean}$"
    try:
        fig = plt.figure(figsize=(7.0, 0.58))
        fig.patch.set_facecolor("white")
        fig.text(0.5, 0.50, label, ha="center", va="center", fontsize=12.5)
        if eqno is not None:
            fig.text(0.985, 0.50, f"({eqno})", ha="right", va="center", fontsize=9.5, color="#333333")
        fig.savefig(path, dpi=240, bbox_inches="tight", pad_inches=0.06, facecolor="white")
        plt.close(fig)
        return path
    except Exception as e:
        plt.close("all")
        print("mathtext fail, unicode fallback:", e, "|", clean[:100])
        try:
            uni = latex_to_rl(tex)
            plain = re.sub(r"<[^>]+>", "", uni)
            plain = plain.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            fig = plt.figure(figsize=(7.2, 0.55))
            fig.text(0.5, 0.5, plain, ha="center", va="center", fontsize=12, family="DejaVu Sans")
            if eqno is not None:
                fig.text(0.99, 0.5, f"({eqno})", ha="right", va="center", fontsize=10, color="#333")
            fig.savefig(path, dpi=220, bbox_inches="tight", pad_inches=0.1, facecolor="white")
            plt.close(fig)
            return path
        except Exception as e2:
            print("eq render failed:", e2, "tex=", tex[:80])
            return None


def md_inline(s: str) -> str:
    """Markdown inline → ReportLab XML (math, bold, code)."""
    chunks: list[str] = []

    def park_math(m):
        chunks.append(m.group(1))
        return f"@@M{len(chunks)-1}@@"

    s = re.sub(r"\$\$([^$]+)\$\$", park_math, s)
    s = re.sub(r"(?<!\$)\$([^$\n]+?)\$(?!\$)", park_math, s)

    # escape XML outside math
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<font face='Courier' size='8'>\1</font>", s)
    # restore math inside Latin face so <sub>/<super> layout correctly
    for i, tex in enumerate(chunks):
        math = latex_to_rl(tex)
        s = s.replace(
            f"@@M{i}@@",
            f"<font name='MathLatin' size='9'><i>{math}</i></font>",
        )
    return s


def styles(font: str) -> dict:
    return {
        "title": ParagraphStyle(
            "t",
            fontName=font,
            fontSize=15,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "author": ParagraphStyle(
            "a", fontName=font, fontSize=11, alignment=TA_CENTER, spaceAfter=2, wordWrap="CJK"
        ),
        "affil": ParagraphStyle(
            "af",
            fontName=font,
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#444444"),
            spaceAfter=8,
            wordWrap="CJK",
        ),
        "note": ParagraphStyle(
            "n",
            fontName=font,
            fontSize=8,
            leading=11,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#555555"),
            spaceAfter=4,
            wordWrap="CJK",
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName=font,
            fontSize=12.5,
            leading=17,
            spaceBefore=12,
            spaceAfter=6,
            textColor=colors.HexColor("#1a1a1a"),
            wordWrap="CJK",
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName=font,
            fontSize=11,
            leading=15,
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.HexColor("#222222"),
            wordWrap="CJK",
        ),
        "body": ParagraphStyle(
            "b",
            fontName=font,
            fontSize=10,
            leading=16,
            alignment=TA_LEFT,  # critical: avoid CJK justify gaps
            firstLineIndent=22,
            spaceAfter=7,
            wordWrap="CJK",
        ),
        "body0": ParagraphStyle(
            "b0",
            fontName=font,
            fontSize=10,
            leading=16,
            alignment=TA_LEFT,
            firstLineIndent=22,
            spaceAfter=7,
            wordWrap="CJK",
        ),
        "abs": ParagraphStyle(
            "abs",
            fontName=font,
            fontSize=9.5,
            leading=15,
            alignment=TA_LEFT,
            firstLineIndent=22,
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "caption": ParagraphStyle(
            "cap",
            fontName=font,
            fontSize=8.5,
            leading=11,
            alignment=TA_CENTER,
            spaceBefore=3,
            spaceAfter=12,
            textColor=colors.HexColor("#333333"),
            wordWrap="CJK",
        ),
        "bullet": ParagraphStyle(
            "bu",
            fontName=font,
            fontSize=9.8,
            leading=14.5,
            leftIndent=14,
            firstLineIndent=0,
            spaceAfter=3,
            wordWrap="CJK",
            alignment=TA_LEFT,
        ),
        "eqfb": ParagraphStyle(
            "eqfb",
            fontName=font,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            spaceBefore=6,
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "kw": ParagraphStyle(
            "kw",
            fontName=font,
            fontSize=9,
            leading=13,
            alignment=TA_LEFT,
            spaceAfter=3,
            wordWrap="CJK",
        ),
    }


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cccccc"))
    canvas.setLineWidth(0.4)
    y = letter[1] - 0.48 * inch
    canvas.line(0.9 * inch, y, letter[0] - 0.9 * inch, y)
    canvas.setFont("CoreCJK", 8)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawString(0.9 * inch, y + 5, "李国聪 — 世界模型优先与 AI 市场分析")
    canvas.drawCentredString(letter[0] / 2, 0.45 * inch, str(doc.page))
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
    col_w = [CONTENT_W / n] * n
    style_h = ParagraphStyle("th", fontName=font, fontSize=8, leading=10.5, wordWrap="CJK", alignment=TA_LEFT)
    style_b = ParagraphStyle("tb", fontName=font, fontSize=7.8, leading=10, wordWrap="CJK", alignment=TA_LEFT)
    data = []
    for ri, row in enumerate(rows):
        data.append([Paragraph(md_inline(c), style_h if ri == 0 else style_b) for c in row])
    t = Table(data, colWidths=col_w, hAlign="CENTER", repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F3F3")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#888888")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def resolve_fig(path_str: str) -> Path | None:
    p = Path(path_str)
    candidates = [
        p,
        ROOT / path_str,
        FIG / p.name,
        (MD.parent / path_str).resolve(),
        (ROOT / path_str.lstrip("./")).resolve(),
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def fig_flow(path: Path, caption: str, S: dict, width: float = CONTENT_W):
    # preserve aspect
    try:
        from PIL import Image as PILImage

        with PILImage.open(path) as im:
            w, h = im.size
            ratio = h / max(w, 1)
    except Exception:
        ratio = 0.48
    height = min(width * ratio, 3.8 * inch)
    img = Image(str(path), width=width, height=height)
    return KeepTogether([img, Paragraph(caption, S["caption"])])


def build() -> Path:
    font = register_font()
    S = styles(font)
    lines = MD.read_text(encoding="utf-8").splitlines()
    story = []
    i = 0
    in_code = False
    in_display = False
    display_buf: list[str] = []
    eqno = 0
    in_abstract = False
    first_body_in_section = True

    def flush_display():
        nonlocal eqno, display_buf, in_display
        tex = " ".join(display_buf).strip()
        display_buf = []
        in_display = False
        if not tex:
            return
        eqno += 1
        png = render_display_eq(tex, eqno=eqno)
        if png and png.exists():
            try:
                from PIL import Image as PILImage

                with PILImage.open(png) as im:
                    w, h = im.size
                width = min(CONTENT_W, 6.2 * inch)
                height = width * (h / max(w, 1))
                height = min(height, 1.2 * inch)
                story.append(Spacer(1, 2))
                story.append(Image(str(png), width=width, height=min(height, 0.85 * inch)))
                story.append(Spacer(1, 2))
                return
            except Exception:
                pass
        # textual fallback
        story.append(Paragraph(latex_to_rl(tex), S["eqfb"]))

    while i < len(lines):
        line = lines[i]
        raw = line.rstrip("\n")
        stripped = raw.strip()

        # fenced code
        if stripped.startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if in_code:
            story.append(
                Paragraph(
                    raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") or " ",
                    S["note"],
                )
            )
            i += 1
            continue

        # display math start/end
        if stripped in (r"\[", "$$") or (stripped.startswith("$$") and not stripped.endswith("$$") and len(stripped) > 2):
            in_display = True
            display_buf = []
            if stripped.startswith("$$") and stripped != "$$":
                display_buf.append(stripped.strip("$"))
            i += 1
            continue
        if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
            display_buf = [stripped.strip("$")]
            flush_display()
            i += 1
            continue
        if in_display:
            if stripped in (r"\]", "$$"):
                flush_display()
            else:
                display_buf.append(stripped)
            i += 1
            continue

        if not stripped:
            i += 1
            continue
        if stripped == "---":
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#cccccc")))
            story.append(Spacer(1, 6))
            i += 1
            continue

        # Markdown image: ![caption](path)
        m_img = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if m_img:
            cap, rel = m_img.group(1), m_img.group(2)
            fp = resolve_fig(rel)
            if fp:
                story.append(fig_flow(fp, md_inline(cap) if cap else fp.name, S))
            else:
                story.append(Paragraph(f"[缺图: {rel}]", S["note"]))
            i += 1
            continue

        if raw.startswith("# "):
            story.append(Paragraph(md_inline(raw[2:]), S["title"]))
            first_body_in_section = True
            i += 1
            continue
        if raw.startswith("## "):
            h = raw[3:].strip()
            in_abstract = h.startswith("摘要")
            story.append(Paragraph(md_inline(h), S["h1"]))
            first_body_in_section = True
            i += 1
            continue
        if raw.startswith("### "):
            story.append(Paragraph(md_inline(raw[4:].strip()), S["h2"]))
            first_body_in_section = True
            i += 1
            continue

        if stripped.startswith("|"):
            rows, i = parse_md_table(lines, i)
            story.append(Spacer(1, 2))
            story.append(make_table(rows, font))
            story.append(Spacer(1, 8))
            first_body_in_section = True
            continue

        if raw.startswith("> "):
            story.append(Paragraph(md_inline(raw[2:]), S["note"]))
            i += 1
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            story.append(Paragraph("• " + md_inline(stripped[2:]), S["bullet"]))
            i += 1
            continue

        # numbered list "1. "
        if re.match(r"^\d+\.\s+", stripped):
            story.append(Paragraph(md_inline(stripped), S["bullet"]))
            i += 1
            continue

        if raw.startswith("**李") or raw.startswith("独立研究者"):
            style = S["author"] if raw.startswith("**") else S["affil"]
            story.append(Paragraph(md_inline(raw), style))
            i += 1
            continue

        if stripped.startswith("**关键词") or stripped.startswith("**JEL"):
            story.append(Paragraph(md_inline(stripped), S["kw"]))
            i += 1
            continue

        # body
        style = S["abs"] if in_abstract else (S["body0"] if first_body_in_section else S["body"])
        story.append(Paragraph(md_inline(raw), style))
        first_body_in_section = False
        i += 1

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        leftMargin=0.95 * inch,
        rightMargin=0.95 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.75 * inch,
        title="从模型优先到世界模型优先",
        author="李国聪",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    OUT_MIRROR.write_bytes(OUT.read_bytes())
    OUT_ORIG.parent.mkdir(parents=True, exist_ok=True)
    OUT_ORIG.write_bytes(OUT.read_bytes())
    print("Wrote", OUT, OUT.stat().st_size, "eqs≈", eqno)
    return OUT


if __name__ == "__main__":
    # quick self-check of converter
    samples = [
        r"B_t=\frac{1}{K}\sum_{k=1}^{K}a_{k,t}",
        r"\hat y_{t+1}=f(X_{1,t},\ldots,X_{J,t})",
        r"W_t=G\bigl(\{X_{j,\tau}\}_{j\le J,\tau\le t},\,Q_t,\,R_t,\,A_t\bigr)",
        r"\mathrm{WMI}_t=B_t\times U_t\times H_t",
        r"\|\widetilde S_t-S_t\|\le C_1\sum_j\omega_j\ell_{j,t}",
        r"B^{\mathrm{hier}}_t=0.25\,B^{\mathrm{dom}}_t",
        r"\widehat{\mathrm{MIG}}_k=V(I)-V(I\setminus E_k)",
    ]
    print("converter samples:")
    for s in samples:
        print(" ", latex_to_rl(s))
    build()
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader

    print("pages:", len(PdfReader(str(OUT)).pages))
