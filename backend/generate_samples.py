# generate_samples.py — generates sample lab report PDFs for demo/testing
#
# Creates 4 PDFs in static/ folder at startup (skips if already exist).
# Each PDF looks like a real Indian lab report (SRL / Thyrocare / Dr.Lal style).
# Users download these, then upload via the normal file input to test full pipeline.
#
# Run manually: python generate_samples.py
# Or called automatically from main.py lifespan on startup.

import io
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# ── Sample data ───────────────────────────────────────────────────────────────
# Each entry: (test_name, value_or_None, unit_or_None, reference_range_or_None)
# value=None means it's a section header row (printed differently).

SAMPLES = {
    "healthy": {
        "filename": "sample_healthy.pdf",
        "patient":  {"name": "Priya Sharma", "age": "25 Years", "gender": "Female",
                     "ref_no": "SRL-2026-00142", "date": "24 May 2026"},
        "lab":      {"name": "SRL Diagnostics",
                     "address": "B-117, Industrial Area Phase-I, Chandigarh – 160002",
                     "phone": "0172-4672000"},
        "tests": [
            ("COMPLETE BLOOD COUNT",                None,   None,      None),
            ("Haemoglobin",                         13.2,   "g/dL",    "12.0 - 15.5"),
            ("Total WBC Count",                     7200,   "cells/cumm","4000 - 11000"),
            ("Platelet Count",                      2.80,   "Lacs/cumm","1.50 - 4.50"),
            ("BLOOD SUGAR",                         None,   None,      None),
            ("Fasting Blood Glucose",               88,     "mg/dL",   "70 - 100"),
            ("HbA1c (Glycosylated Haemoglobin)",    5.1,    "%",       "4.0 - 5.6"),
            ("LIPID PROFILE",                       None,   None,      None),
            ("Total Cholesterol",                   175,    "mg/dL",   "< 200"),
            ("LDL Cholesterol",                     95,     "mg/dL",   "< 100"),
            ("HDL Cholesterol",                     62,     "mg/dL",   "> 50"),
            ("THYROID FUNCTION",                    None,   None,      None),
            ("TSH (Thyroid Stimulating Hormone)",   2.1,    "mIU/mL",  "0.4 - 4.0"),
            ("KIDNEY FUNCTION",                     None,   None,      None),
            ("Serum Creatinine",                    0.8,    "mg/dL",   "0.6 - 1.1"),
        ],
    },

    "diabetic": {
        "filename": "sample_diabetic.pdf",
        "patient":  {"name": "Rajesh Kumar", "age": "52 Years", "gender": "Male",
                     "ref_no": "THY-2026-08831", "date": "24 May 2026"},
        "lab":      {"name": "Thyrocare Technologies",
                     "address": "D-37/1, TTC Industrial Area, Turbhe, Navi Mumbai – 400703",
                     "phone": "022-3090-2000"},
        "tests": [
            ("DIABETES PANEL",                      None,   None,      None),
            ("HbA1c (Glycosylated Haemoglobin)",    8.1,    "%",       "4.0 - 5.6"),
            ("Fasting Blood Glucose",               162,    "mg/dL",   "70 - 100"),
            ("LIPID PROFILE",                       None,   None,      None),
            ("Total Cholesterol",                   218,    "mg/dL",   "< 200"),
            ("LDL Cholesterol",                     142,    "mg/dL",   "< 100"),
            ("HDL Cholesterol",                     38,     "mg/dL",   "> 40"),
            ("Triglycerides",                       285,    "mg/dL",   "< 150"),
            ("KIDNEY FUNCTION",                     None,   None,      None),
            ("Serum Creatinine",                    1.4,    "mg/dL",   "0.7 - 1.3"),
            ("Serum Uric Acid",                     7.8,    "mg/dL",   "3.4 - 7.0"),
            ("COMPLETE BLOOD COUNT",                None,   None,      None),
            ("Haemoglobin",                         13.8,   "g/dL",    "13.5 - 17.5"),
            ("THYROID",                             None,   None,      None),
            ("TSH (Thyroid Stimulating Hormone)",   3.2,    "mIU/mL",  "0.4 - 4.0"),
        ],
    },

    "lipids": {
        "filename": "sample_lipids.pdf",
        "patient":  {"name": "Amit Singh", "age": "45 Years", "gender": "Male",
                     "ref_no": "DLL-2026-21904", "date": "24 May 2026"},
        "lab":      {"name": "Dr. Lal PathLabs",
                     "address": "12, Ring Road, Lajpat Nagar-IV, New Delhi – 110024",
                     "phone": "011-3988-3988"},
        "tests": [
            ("LIPID PROFILE",                       None,   None,      None),
            ("Total Cholesterol",                   268,    "mg/dL",   "< 200"),
            ("LDL Cholesterol",                     188,    "mg/dL",   "< 100"),
            ("HDL Cholesterol",                     32,     "mg/dL",   "> 40"),
            ("Triglycerides",                       320,    "mg/dL",   "< 150"),
            ("VLDL Cholesterol",                    64,     "mg/dL",   "< 30"),
            ("BLOOD SUGAR",                         None,   None,      None),
            ("Fasting Blood Glucose",               96,     "mg/dL",   "70 - 100"),
            ("COMPLETE BLOOD COUNT",                None,   None,      None),
            ("Haemoglobin",                         15.2,   "g/dL",    "13.5 - 17.5"),
            ("THYROID",                             None,   None,      None),
            ("TSH (Thyroid Stimulating Hormone)",   1.8,    "mIU/mL",  "0.4 - 4.0"),
            ("LIVER FUNCTION",                      None,   None,      None),
            ("Serum ALT / SGPT",                    48,     "U/L",     "< 56"),
            ("Serum AST / SGOT",                    42,     "U/L",     "< 40"),
        ],
    },

    "anemia": {
        "filename": "sample_anemia.pdf",
        "patient":  {"name": "Sunita Devi", "age": "34 Years", "gender": "Female",
                     "ref_no": "APL-2026-33710", "date": "24 May 2026"},
        "lab":      {"name": "Apollo Diagnostics",
                     "address": "Apollo Health City, Jubilee Hills, Hyderabad – 500033",
                     "phone": "040-2360-7777"},
        "tests": [
            ("COMPLETE BLOOD COUNT",                None,   None,      None),
            ("Haemoglobin",                         8.9,    "g/dL",    "12.0 - 15.5"),
            ("RBC Count",                           3.2,    "mill/cumm","3.8 - 5.2"),
            ("MCV (Mean Corpuscular Volume)",        68,     "fL",      "80 - 100"),
            ("Total WBC Count",                     5800,   "cells/cumm","4000 - 11000"),
            ("Platelet Count",                      3.20,   "Lacs/cumm","1.50 - 4.50"),
            ("IRON STUDIES",                        None,   None,      None),
            ("Serum Ferritin",                      6,      "ng/mL",   "10 - 120"),
            ("Serum Iron",                          38,     "mcg/dL",  "50 - 170"),
            ("VITAMINS",                            None,   None,      None),
            ("Vitamin B12 (Cyanocobalamin)",         142,    "pg/mL",   "200 - 900"),
            ("Vitamin D Total (25-OH)",              11,     "ng/mL",   "30 - 100"),
            ("THYROID",                             None,   None,      None),
            ("TSH (Thyroid Stimulating Hormone)",   2.8,    "mIU/mL",  "0.4 - 4.0"),
        ],
    },
}


# ── PDF builder ───────────────────────────────────────────────────────────────

C_DARK   = colors.HexColor("#1A2340")
C_MID    = colors.HexColor("#3A5270")
C_LIGHT  = colors.HexColor("#E8EEF5")
C_BORDER = colors.HexColor("#C5D0DC")
C_WHITE  = colors.white
C_HIGH   = colors.HexColor("#FFF3CD")   # highlight for abnormal marker
C_HEAD   = colors.HexColor("#D0DCE8")


def _make_styles():
    return {
        "lab":      ParagraphStyle("lab",  fontName="Helvetica-Bold", fontSize=14,
                                   textColor=C_DARK, leading=18),
        "addr":     ParagraphStyle("addr", fontName="Helvetica",      fontSize=8,
                                   textColor=C_MID,  leading=11),
        "title":    ParagraphStyle("title",fontName="Helvetica-Bold", fontSize=11,
                                   textColor=C_DARK, leading=14),
        "label":    ParagraphStyle("lbl",  fontName="Helvetica-Bold", fontSize=8,
                                   textColor=C_MID,  leading=11),
        "value":    ParagraphStyle("val",  fontName="Helvetica",      fontSize=9,
                                   textColor=C_DARK, leading=12),
        "sechead":  ParagraphStyle("sec",  fontName="Helvetica-Bold", fontSize=8,
                                   textColor=C_MID,  leading=10),
        "cell":     ParagraphStyle("cell", fontName="Helvetica",      fontSize=9,
                                   textColor=C_DARK, leading=12),
        "cellbold": ParagraphStyle("cb",   fontName="Helvetica-Bold", fontSize=9,
                                   textColor=C_DARK, leading=12),
        "footer":   ParagraphStyle("ft",   fontName="Helvetica",      fontSize=7,
                                   textColor=C_MID,  leading=10),
    }


def _create_pdf(sample: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=12*mm,  bottomMargin=12*mm)
    PW  = 180 * mm   # printable width
    s   = _make_styles()
    story = []

    lab = sample["lab"]
    pat = sample["patient"]

    # ── Lab header ────────────────────────────────────────────────────────────
    story.append(Paragraph(lab["name"], s["lab"]))
    story.append(Paragraph(lab["address"] + "  |  Tel: " + lab["phone"], s["addr"]))
    story.append(HRFlowable(width="100%", thickness=1, color=C_MID, spaceAfter=6))

    # Report title
    story.append(Paragraph("LABORATORY TEST REPORT", s["title"]))
    story.append(Spacer(1, 4))

    # ── Patient info box ──────────────────────────────────────────────────────
    info_data = [
        [
            Paragraph("Patient Name:", s["label"]),
            Paragraph(pat["name"], s["value"]),
            Paragraph("Report No:", s["label"]),
            Paragraph(pat["ref_no"], s["value"]),
        ],
        [
            Paragraph("Age / Sex:", s["label"]),
            Paragraph(f"{pat['age']} / {pat['gender']}", s["value"]),
            Paragraph("Report Date:", s["label"]),
            Paragraph(pat["date"], s["value"]),
        ],
    ]
    info_tbl = Table(info_data, colWidths=[PW*0.15, PW*0.35, PW*0.15, PW*0.35])
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_LIGHT),
        ("BOX",           (0,0), (-1,-1), 0.5, C_BORDER),
        ("INNERGRID",     (0,0), (-1,-1), 0.3, C_BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 8))

    # ── Results table ─────────────────────────────────────────────────────────
    hdr = [
        Paragraph("TEST NAME",           s["label"]),
        Paragraph("RESULT",              s["label"]),
        Paragraph("UNITS",               s["label"]),
        Paragraph("BIOLOGICAL REF. RANGE", s["label"]),
    ]
    rows = [hdr]
    row_styles = [
        ("BACKGROUND",    (0,0), (-1,0),  C_HEAD),
        ("BOX",           (0,0), (-1,-1), 0.5, C_BORDER),
        ("INNERGRID",     (0,0), (-1,-1), 0.3, C_BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("ALIGN",         (1,0), (3,-1),  "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]

    for i, (name, val, unit, ref) in enumerate(sample["tests"], start=1):
        is_section = val is None
        if is_section:
            row = [
                Paragraph(name, s["sechead"]),
                Paragraph("", s["cell"]),
                Paragraph("", s["cell"]),
                Paragraph("", s["cell"]),
            ]
            row_styles.append(("BACKGROUND", (0,i), (-1,i), C_LIGHT))
            row_styles.append(("SPAN",        (0,i), (-1,i)))
        else:
            val_str = str(int(val)) if isinstance(val, float) and val == int(val) else str(val)
            row = [
                Paragraph(name,    s["cell"]),
                Paragraph(val_str, s["cellbold"]),
                Paragraph(unit or "", s["cell"]),
                Paragraph(ref  or "", s["cell"]),
            ]
            # Alternate row shading
            if i % 2 == 0:
                row_styles.append(("BACKGROUND", (0,i), (-1,i), C_LIGHT))
        rows.append(row)

    tbl = Table(rows, colWidths=[PW*0.40, PW*0.15, PW*0.15, PW*0.30])
    tbl.setStyle(TableStyle(row_styles))
    story.append(tbl)
    story.append(Spacer(1, 12))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "This report is electronically verified and does not require a signature. "
        "Results should be interpreted in clinical context by a qualified physician. "
        "This is a SAMPLE report generated for demonstration purposes only.",
        s["footer"]
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Public entry point ────────────────────────────────────────────────────────

def generate_all_samples(force: bool = False) -> None:
    """
    Generate all sample PDFs into static/ folder.
    Skips files that already exist unless force=True.
    Called at app startup from main.py lifespan.
    """
    os.makedirs(STATIC_DIR, exist_ok=True)
    for key, sample in SAMPLES.items():
        path = os.path.join(STATIC_DIR, sample["filename"])
        if not force and os.path.exists(path):
            continue
        try:
            pdf_bytes = _create_pdf(sample)
            with open(path, "wb") as f:
                f.write(pdf_bytes)
            print(f"[samples] Generated: {path}")
        except Exception as e:
            print(f"[samples] Failed to generate {key}: {e}")


if __name__ == "__main__":
    generate_all_samples(force=True)
    print("[samples] Done.")
    