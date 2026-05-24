# exporter.py — PDF export using reportlab
# Generates a downloadable PDF report card the user can hand to their doctor.
# Colors approximate the Sage & Ink palette in RGB for print.
 
import io
from datetime import datetime
 
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
 
# ── Color palette (Sage & Ink → RGB for reportlab) ───────────────────────────
C_PAGE_BG    = colors.HexColor("#F4F7F4")
C_PRIMARY    = colors.HexColor("#1C2B1A")
C_SECONDARY  = colors.HexColor("#3B6D11")
C_MUTED      = colors.HexColor("#5F7A5C")
C_CARD_BG    = colors.HexColor("#EAF3DE")
C_CARD_BDR   = colors.HexColor("#C0DD97")
C_CAUTION_BG = colors.HexColor("#FFF8EF")
C_CAUTION_BD = colors.HexColor("#FAC775")
C_DANGER_BG  = colors.HexColor("#FFF0F0")
C_DANGER_BD  = colors.HexColor("#F7C1C1")
C_WHITE      = colors.HexColor("#FFFFFF")
 
FLAG_COLORS = {
    "Normal":     (C_CARD_BG, C_CARD_BDR, colors.HexColor("#27500A")),
    "Caution":    (C_CAUTION_BG, C_CAUTION_BD, colors.HexColor("#633806")),
    "See Doctor": (C_DANGER_BG, C_DANGER_BD, colors.HexColor("#791F1F")),
}
 
 
def _styles():
    """Build custom paragraph styles matching Sage & Ink typography."""
    base = getSampleStyleSheet()
 
    return {
        "title": ParagraphStyle(
            "title", fontName="Helvetica", fontSize=16, textColor=C_PRIMARY,
            leading=20, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName="Helvetica", fontSize=11, textColor=C_MUTED,
            leading=15, spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "section", fontName="Helvetica-Bold", fontSize=12, textColor=C_PRIMARY,
            leading=16, spaceBefore=12, spaceAfter=6,
        ),
        "test_name": ParagraphStyle(
            "test_name", fontName="Helvetica-Bold", fontSize=10, textColor=C_PRIMARY,
            leading=14,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=9, textColor=C_PRIMARY,
            leading=14,
        ),
        "muted": ParagraphStyle(
            "muted", fontName="Helvetica", fontSize=8, textColor=C_MUTED,
            leading=12,
        ),
        "q_item": ParagraphStyle(
            "q_item", fontName="Helvetica", fontSize=9, textColor=C_PRIMARY,
            leading=14, leftIndent=10,
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer", fontName="Helvetica-Oblique", fontSize=8, textColor=C_MUTED,
            leading=12, alignment=TA_CENTER,
        ),
    }
 
 
def _flag_badge_text(flag: str) -> str:
    symbols = {"Normal": "✓", "Caution": "⚠", "See Doctor": "⚑"}
    return f"{symbols.get(flag, '')} {flag}"
 
 
def generate_pdf(tests: list[dict], patient: dict) -> bytes:
    """
    Generate a PDF report card from the analyzed test results.
    
    Structure:
      1. Header — app name, patient info, generation date
      2. Summary — total tests, how many flagged
      3. Results table — all tests with values, ranges, flags
      4. Detailed explanations — for flagged tests only
      5. Questions to ask your doctor — consolidated list
      6. Disclaimer footer
    
    Returns PDF as bytes (for streaming response in FastAPI).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
 
    s = _styles()
    story = []
    age = patient.get("age", "")
    gender = patient.get("gender", "").capitalize()
    generated = datetime.now().strftime("%d %B %Y, %I:%M %p")
 
    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Lab Report — Plain Language Summary", s["title"]))
    story.append(Paragraph(
        f"Patient: {age} years old, {gender} &nbsp;|&nbsp; Generated: {generated}",
        s["subtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_CARD_BDR, spaceAfter=12))
 
    # ── Summary banner ────────────────────────────────────────────────────────
    total = len(tests)
    flagged = [t for t in tests if t.get("flag") != "Normal"]
    n_caution = sum(1 for t in tests if t.get("flag") == "Caution")
    n_see_dr = sum(1 for t in tests if t.get("flag") == "See Doctor")
    n_normal = total - len(flagged)
 
    summary_data = [
        ["Total Tests", "Normal", "Caution", "Needs Attention"],
        [str(total), str(n_normal), str(n_caution), str(n_see_dr)],
    ]
    summary_table = Table(summary_data, colWidths=["25%", "25%", "25%", "25%"])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_CARD_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_MUTED),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 1), (-1, 1), C_WHITE),
        ("TEXTCOLOR", (0, 1), (-1, 1), C_PRIMARY),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 14),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_CARD_BG, C_WHITE]),
        ("BOX", (0, 0), (-1, -1), 0.5, C_CARD_BDR),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, C_CARD_BDR),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 14))
 
    # ── Results table ─────────────────────────────────────────────────────────
    story.append(Paragraph("All Results", s["section"]))
 
    table_header = ["Test", "Value", "Reference Range", "Status"]
    table_data = [table_header]
 
    sorted_tests = sorted(tests, key=lambda t: (
        0 if t.get("flag") == "See Doctor" else
        1 if t.get("flag") == "Caution" else 2
    ))
 
    for t in sorted_tests:
        flag = t.get("flag", "Normal")
        _, _, text_color = FLAG_COLORS.get(flag, FLAG_COLORS["Normal"])
        ref = t.get("reference_range") or (
            f"{t.get('ref_min', '')}–{t.get('ref_max', '')}" if (t.get("ref_min") or t.get("ref_max")) else "—"
        )
        value_str = f"{t.get('value', '—')} {t.get('unit', '')}".strip()
        table_data.append([
            t.get("test_name", ""),
            value_str,
            ref,
            _flag_badge_text(flag),
        ])
 
    col_widths = ["40%", "20%", "25%", "15%"]
    results_table = Table(table_data, colWidths=col_widths)
 
    row_styles = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 0), (-1, 0), C_CARD_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_MUTED),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), C_PRIMARY),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BOX", (0, 0), (-1, -1), 0.5, C_CARD_BDR),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, C_CARD_BDR),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_PAGE_BG]),
    ]
 
    # Color the status column per flag
    for i, t in enumerate(sorted_tests, start=1):
        flag = t.get("flag", "Normal")
        _, _, text_color = FLAG_COLORS.get(flag, FLAG_COLORS["Normal"])
        row_styles.append(("TEXTCOLOR", (3, i), (3, i), text_color))
        row_styles.append(("FONTNAME", (3, i), (3, i), "Helvetica-Bold"))
 
    results_table.setStyle(TableStyle(row_styles))
    story.append(results_table)
    story.append(Spacer(1, 14))
 
    # ── Detailed explanations (flagged only) ──────────────────────────────────
    if flagged:
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_CARD_BDR))
        story.append(Spacer(1, 6))
        story.append(Paragraph("What do these results mean?", s["section"]))
 
        for t in flagged:
            flag = t.get("flag", "Normal")
            bg, border, text_color = FLAG_COLORS.get(flag, FLAG_COLORS["Normal"])
            test_name = t.get("test_name", "")
            explanation = t.get("explanation", "")
 
            block_data = [[
                Paragraph(f"<b>{test_name}</b>", s["test_name"]),
                Paragraph(_flag_badge_text(flag), ParagraphStyle(
                    "badge_pdf", fontName="Helvetica-Bold", fontSize=8, textColor=text_color
                )),
            ]]
            block_table = Table(block_data, colWidths=["75%", "25%"])
            block_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.5, border),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(block_table)
 
            if explanation:
                exp_block = Table([[Paragraph(explanation, s["body"])]])
                exp_block.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), bg),
                    ("BOX", (0, 0), (-1, -1), 0.5, border),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]))
                story.append(exp_block)
 
            story.append(Spacer(1, 6))
 
    # ── Questions to ask your doctor ─────────────────────────────────────────
    all_questions = []
    for t in tests:
        qs = t.get("doctor_questions", [])
        for q in qs:
            if q and q not in all_questions:
                all_questions.append((t.get("test_name", ""), q))
 
    if all_questions:
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_CARD_BDR))
        story.append(Spacer(1, 6))
        story.append(Paragraph("Questions to ask your doctor", s["section"]))
 
        for test_name, q in all_questions:
            story.append(Paragraph(f"• [{test_name}] {q}", s["q_item"]))
            story.append(Spacer(1, 3))
 
    # ── Disclaimer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_CARD_BDR))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This report is generated for educational purposes only. It is not a medical diagnosis. "
        "Always consult a qualified physician before making any health decisions.",
        s["disclaimer"]
    ))
 
    doc.build(story)
    buffer.seek(0)
    return buffer.read()
 