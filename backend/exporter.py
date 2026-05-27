# exporter.py — PDF export using reportlab
# FIX 1: generate_pdf() now correctly unpacks patient dict (was NameError crash)
# FIX 2: colWidths use mm units instead of percentage strings (unreliable in reportlab)
# FIX 3: removed dead non_latin_exists variable

import io
import os
import glob
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

# ── Unicode font setup ────────────────────────────────────────────────────────

def _register_noto() -> tuple[str, str]:
    search_patterns = [
        "/usr/share/fonts/**/NotoSans-Regular.ttf",
        "/usr/share/fonts/**/NotoSans_Regular.ttf",
        "/usr/share/fonts/**/*Noto*Sans*Regular*.ttf",
    ]
    bold_patterns = [
        "/usr/share/fonts/**/NotoSans-Bold.ttf",
        "/usr/share/fonts/**/NotoSans_Bold.ttf",
        "/usr/share/fonts/**/*Noto*Sans*Bold*.ttf",
    ]

    regular_path, bold_path = None, None
    for p in search_patterns:
        matches = glob.glob(p, recursive=True)
        if matches:
            regular_path = matches[0]
            break
    for p in bold_patterns:
        matches = glob.glob(p, recursive=True)
        if matches:
            bold_path = matches[0]
            break

    if regular_path:
        try:
            pdfmetrics.registerFont(TTFont("NotoSans", regular_path))
            if bold_path:
                pdfmetrics.registerFont(TTFont("NotoSans-Bold", bold_path))
            else:
                pdfmetrics.registerFont(TTFont("NotoSans-Bold", regular_path))
            return "NotoSans", "NotoSans-Bold"
        except Exception as e:
            print(f"[exporter] NotoSans registration failed: {e}. Using Helvetica.")

    return "Helvetica", "Helvetica-Bold"


BODY_FONT, BOLD_FONT = _register_noto()
UNICODE_AVAILABLE = BODY_FONT == "NotoSans"

# A4 printable width: 210mm - 20mm left - 20mm right = 170mm
_PW = 170 * mm


def _safe_text(text: str) -> str:
    if UNICODE_AVAILABLE:
        return text
    try:
        text.encode("latin-1")
        return text
    except (UnicodeEncodeError, UnicodeDecodeError):
        return "[Switch to English view for PDF export — Hindi/Punjabi not supported in this PDF.]"


# ── Colour palette ────────────────────────────────────────────────────────────
C_PRIMARY    = colors.HexColor("#1C2B1A")
C_MUTED      = colors.HexColor("#5F7A5C")
C_CARD_BG    = colors.HexColor("#EAF3DE")
C_CARD_BDR   = colors.HexColor("#C0DD97")
C_CAUTION_BG = colors.HexColor("#FFF8EF")
C_CAUTION_BD = colors.HexColor("#FAC775")
C_DANGER_BG  = colors.HexColor("#FFF0F0")
C_DANGER_BD  = colors.HexColor("#F7C1C1")
C_PAGE_BG    = colors.HexColor("#F4F7F4")
C_WHITE      = colors.HexColor("#FFFFFF")

FLAG_COLORS = {
    "Normal":     (C_CARD_BG,    C_CARD_BDR,   colors.HexColor("#27500A")),
    "Caution":    (C_CAUTION_BG, C_CAUTION_BD, colors.HexColor("#633806")),
    "See Doctor": (C_DANGER_BG,  C_DANGER_BD,  colors.HexColor("#791F1F")),
}


def _styles() -> dict:
    return {
        "title":      ParagraphStyle("title",      fontName=BOLD_FONT,  fontSize=16, textColor=C_PRIMARY, leading=20, spaceAfter=2),
        "subtitle":   ParagraphStyle("subtitle",   fontName=BODY_FONT,  fontSize=11, textColor=C_MUTED,   leading=15, spaceAfter=8),
        "section":    ParagraphStyle("section",    fontName=BOLD_FONT,  fontSize=12, textColor=C_PRIMARY, leading=16, spaceBefore=12, spaceAfter=6),
        "test_name":  ParagraphStyle("test_name",  fontName=BOLD_FONT,  fontSize=10, textColor=C_PRIMARY, leading=14),
        "body":       ParagraphStyle("body",       fontName=BODY_FONT,  fontSize=9,  textColor=C_PRIMARY, leading=14),
        "muted":      ParagraphStyle("muted",      fontName=BODY_FONT,  fontSize=8,  textColor=C_MUTED,   leading=12),
        "q_item":     ParagraphStyle("q_item",     fontName=BODY_FONT,  fontSize=9,  textColor=C_PRIMARY, leading=14, leftIndent=10),
        "disclaimer": ParagraphStyle("disclaimer", fontName=BODY_FONT,  fontSize=8,  textColor=C_MUTED,   leading=12, alignment=TA_CENTER),
        "notice":     ParagraphStyle("notice",     fontName=BOLD_FONT,  fontSize=9,  textColor=colors.HexColor("#633806"), leading=13,
                                     backColor=C_CAUTION_BG),
    }


def _badge(flag: str) -> str:
    return {"Normal": "✓ Normal", "Caution": "⚠ Caution", "See Doctor": "⚑ See Doctor"}.get(flag, flag)


def generate_pdf(tests: list[dict], patient: dict) -> bytes:
    """
    Generate a downloadable PDF summary.
    FIX: unpack patient dict at the top — previously used undefined age/gender variables.
    FIX: colWidths use mm values — percentage strings are unreliable across reportlab versions.
    """
    # FIX: extract age and gender from patient dict
    age    = patient.get("age") or "—"
    gender = patient.get("gender") or "—"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm,   bottomMargin=20*mm)
    s       = _styles()
    story   = []
    now_str = datetime.now().strftime("%d %B %Y, %I:%M %p")

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Lab Report — Plain Language Summary", s["title"]))
    story.append(Paragraph(
        f"Patient: {age} years old, {gender} &nbsp;|&nbsp; Generated: {now_str}",
        s["subtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_CARD_BDR, spaceAfter=12))

    # ── Unicode notice ────────────────────────────────────────────────────────
    if not UNICODE_AVAILABLE:
        def _has_non_latin(t):
            try:
                (t.get("explanation", "") + " ".join(t.get("doctor_questions", []))).encode("latin-1")
                return False
            except (UnicodeEncodeError, UnicodeDecodeError):
                return True

        if any(_has_non_latin(t) for t in tests):
            story.append(Paragraph(
                "⚠ This report was generated with Hindi or Punjabi explanations. "
                "PDF export supports English only — switch to English view and re-export for full content.",
                s["notice"]
            ))
            story.append(Spacer(1, 8))

    # ── Summary ───────────────────────────────────────────────────────────────
    total     = len(tests)
    n_caution = sum(1 for t in tests if t.get("flag") == "Caution")
    n_danger  = sum(1 for t in tests if t.get("flag") == "See Doctor")
    n_normal  = total - n_caution - n_danger

    # FIX: colWidths use mm values instead of percentage strings
    summary_table = Table(
        [["Total Tests", "Normal", "Caution", "Needs Attention"],
         [str(total), str(n_normal), str(n_caution), str(n_danger)]],
        colWidths=[_PW * 0.25, _PW * 0.25, _PW * 0.25, _PW * 0.25]
    )
    summary_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), C_CARD_BG),
        ("TEXTCOLOR",     (0,0), (-1,0), C_MUTED),
        ("FONTNAME",      (0,0), (-1,0), BODY_FONT),
        ("FONTSIZE",      (0,0), (-1,0), 8),
        ("BACKGROUND",    (0,1), (-1,1), C_WHITE),
        ("TEXTCOLOR",     (0,1), (-1,1), C_PRIMARY),
        ("FONTNAME",      (0,1), (-1,1), BOLD_FONT),
        ("FONTSIZE",      (0,1), (-1,1), 14),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("BOX",           (0,0), (-1,-1), 0.5, C_CARD_BDR),
        ("INNERGRID",     (0,0), (-1,-1), 0.3, C_CARD_BDR),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 14))

    # ── All results table ─────────────────────────────────────────────────────
    story.append(Paragraph("All results", s["section"]))
    sorted_tests = sorted(tests, key=lambda t: (
        0 if t.get("flag") == "See Doctor" else 1 if t.get("flag") == "Caution" else 2
    ))

    rows = [["Test", "Value", "Reference Range", "Status"]]
    for t in sorted_tests:
        ref = (t.get("reference_range")
               or (f"{t.get('ref_min','')}–{t.get('ref_max','')}"
                   if (t.get("ref_min") or t.get("ref_max")) else "—"))
        rows.append([
            t.get("test_name", ""),
            f"{t.get('value', '—')} {t.get('unit', '')}".strip(),
            ref,
            _badge(t.get("flag", "Normal")),
        ])

    # FIX: colWidths use mm values — 40% / 20% / 25% / 15% of 170mm
    tbl = Table(rows, colWidths=[_PW * 0.40, _PW * 0.20, _PW * 0.25, _PW * 0.15])
    row_styles = [
        ("FONTNAME",      (0,0), (-1,0),  BOLD_FONT), ("FONTSIZE",  (0,0), (-1,0),  8),
        ("BACKGROUND",    (0,0), (-1,0),  C_CARD_BG), ("TEXTCOLOR", (0,0), (-1,0),  C_MUTED),
        ("FONTNAME",      (0,1), (-1,-1), BODY_FONT), ("FONTSIZE",  (0,1), (-1,-1), 8),
        ("TEXTCOLOR",     (0,1), (-1,-1), C_PRIMARY),
        ("ALIGN",         (1,0), (-1,-1), "CENTER"),  ("ALIGN",     (0,0), (0,-1),  "LEFT"),
        ("BOX",           (0,0), (-1,-1), 0.5, C_CARD_BDR),
        ("INNERGRID",     (0,0), (-1,-1), 0.3, C_CARD_BDR),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [C_WHITE, C_PAGE_BG]),
    ]
    for i, t in enumerate(sorted_tests, start=1):
        _, _, txt_clr = FLAG_COLORS.get(t.get("flag","Normal"), FLAG_COLORS["Normal"])
        row_styles += [("TEXTCOLOR",(3,i),(3,i),txt_clr), ("FONTNAME",(3,i),(3,i),BOLD_FONT)]
    tbl.setStyle(TableStyle(row_styles))
    story.append(tbl)
    story.append(Spacer(1, 14))

    # ── Explanations (flagged only) ───────────────────────────────────────────
    flagged = [t for t in tests if t.get("flag") != "Normal"]
    if flagged:
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_CARD_BDR))
        story.append(Spacer(1, 6))
        story.append(Paragraph("What do these results mean?", s["section"]))

        for t in flagged:
            flag = t.get("flag", "Normal")
            bg, border, txt_clr = FLAG_COLORS.get(flag, FLAG_COLORS["Normal"])
            exp = _safe_text(t.get("explanation", ""))

            header_tbl = Table([[
                Paragraph(f"<b>{t.get('test_name','')}</b>", s["test_name"]),
                Paragraph(_badge(flag), ParagraphStyle("bp", fontName=BOLD_FONT, fontSize=8, textColor=txt_clr)),
            ]], colWidths=[_PW * 0.75, _PW * 0.25])
            header_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), bg),
                ("BOX",           (0,0), (-1,-1), 0.5, border),
                ("ALIGN",         (1,0), (1,0),   "RIGHT"),
                ("VALIGN",        (0,0), (-1,-1),  "MIDDLE"),
                ("TOPPADDING",    (0,0), (-1,-1),  6),
                ("BOTTOMPADDING", (0,0), (-1,-1),  6),
                ("LEFTPADDING",   (0,0), (-1,-1),  8),
                ("RIGHTPADDING",  (0,0), (-1,-1),  8),
            ]))
            story.append(header_tbl)

            if exp:
                exp_tbl = Table([[Paragraph(exp, s["body"])]])
                exp_tbl.setStyle(TableStyle([
                    ("BACKGROUND",    (0,0), (-1,-1), bg),
                    ("BOX",           (0,0), (-1,-1), 0.5, border),
                    ("LEFTPADDING",   (0,0), (-1,-1), 8),
                    ("RIGHTPADDING",  (0,0), (-1,-1), 8),
                    ("TOPPADDING",    (0,0), (-1,-1), 4),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 8),
                ]))
                story.append(exp_tbl)
            story.append(Spacer(1, 6))

    # ── Doctor questions ──────────────────────────────────────────────────────
    all_qs = []
    for t in tests:
        for q in (t.get("doctor_questions") or []):
            if q:
                all_qs.append((t.get("test_name",""), _safe_text(q)))

    if all_qs:
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_CARD_BDR))
        story.append(Spacer(1, 6))
        story.append(Paragraph("Questions to ask your doctor", s["section"]))
        for tname, q in all_qs:
            story.append(Paragraph(f"• [{tname}] {q}", s["q_item"]))
            story.append(Spacer(1, 3))

    # ── Disclaimer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_CARD_BDR))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This report is for educational purposes only. It is not a medical diagnosis. "
        "Always consult a qualified physician before making any health decisions.",
        s["disclaimer"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
