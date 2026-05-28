# extractor.py — PDF → structured JSON
#
# EXTRACTION STRATEGY (two-pass):
#
# Pass 1 — pymupdf (zero API calls, instant ~0.1s):
#   Try to extract embedded text directly from PDF.
#   Works for: Thyrocare, SRL online, Dr. Lal, Apollo digital PDFs.
#   Fails for:  scanned physical copies, image-only PDFs.
#   If extracted text > 200 chars → send to Groq text model for JSON structuring.
#   Groq quota: 14,400 RPD (vs 50 RPD for vision). Saves vision calls.
#
# Pass 2 — OpenRouter Gemini Vision (fallback only):
#   Used when pymupdf finds no meaningful text (scanned PDF).
#   Converts PDF pages to images → Gemini Vision reads and extracts JSON.
#   Vision quota (50 RPD) conserved for truly scanned reports only.
#
# RESULT: ~80% of real Indian lab PDFs are digital → handled by Pass 1.
# Vision quota effectively multiplied ~5x in practice.

import base64
import io
import json
import os
import re
import time
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import fitz                          # pymupdf — fast text extraction
from openai import OpenAI
from pdf2image import convert_from_bytes
from PIL import Image
from pydantic import BaseModel, field_validator

from units import normalize_unit_alias

# ── Clients ───────────────────────────────────────────────────────────────────

_vision_client: Optional[OpenAI] = None   # OpenRouter — vision fallback
_text_client:   Optional[OpenAI] = None   # Groq — text structuring (Pass 1)

VISION_MODEL = "google/gemini-2.0-flash-exp:free"   # OpenRouter
TEXT_MODEL   = "llama-3.1-8b-instant"               # Groq — fast, high quota, fine for JSON extraction

MIN_TEXT_LENGTH = 200   # chars — below this, treat PDF as image-based


def _get_vision_client() -> OpenAI:
    global _vision_client
    if _vision_client is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set.")
        _vision_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    return _vision_client


def _get_text_client() -> OpenAI:
    global _text_client
    if _text_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set.")
        _text_client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
    return _text_client


# ── Pydantic models ───────────────────────────────────────────────────────────

class PatientInfo(BaseModel):
    age:    Optional[int] = None
    gender: Optional[str] = None


class TestResult(BaseModel):
    test_name:       str
    value:           Optional[float] = None
    unit:            Optional[str]   = None
    reference_range: Optional[str]   = None

    @field_validator("value", mode="before")
    @classmethod
    def value_cannot_be_negative(cls, v) -> Optional[float]:
        """Return None instead of raising — one bad value won't crash the page."""
        if v is None:
            return None
        try:
            fv = float(v)
            if fv < 0:
                print(f"[extractor] Negative value {fv} discarded.")
                return None
            return fv
        except (TypeError, ValueError):
            return None

    @field_validator("test_name")
    @classmethod
    def name_must_be_meaningful(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) < 2 or v.isdigit():
            raise ValueError("test_name too short or numeric.")
        return v


class LabReport(BaseModel):
    patient: PatientInfo
    tests:   list[TestResult]


# ── Plausibility bounds ───────────────────────────────────────────────────────

PLAUSIBILITY_BOUNDS: dict[str, tuple[float, float]] = {
    "glucose":      (0,   2000),
    "hba1c":        (0,   25),
    "hemoglobin":   (0,   25),
    "haemoglobin":  (0,   25),
    "hb":           (0,   25),
    "wbc":          (0,   200_000),
    "platelet":     (0,   2_000_000),
    "sodium":       (100, 200),
    "potassium":    (1,   10),
    "cholesterol":  (0,   1500),
    "triglyceride": (0,   5000),
    "creatinine":   (0,   50),
    "uric acid":    (0,   50),
    "tsh":          (0,   1000),
    "bilirubin":    (0,   100),
    "alt":          (0,   10_000),
    "sgpt":         (0,   10_000),
    "ast":          (0,   10_000),
    "sgot":         (0,   10_000),
    "albumin":      (0,   10),
    "calcium":      (0,   20),
    "vitamin d":    (0,   500),
    "vitamin b12":  (0,   50_000),
    "ferritin":     (0,   100_000),
    "iron":         (0,   1000),
}


def _is_plausible(test_name: str, value: float) -> bool:
    test_lower = test_name.strip().lower()
    for keyword, (lo, hi) in PLAUSIBILITY_BOUNDS.items():
        if keyword in test_lower:
            in_bounds = lo <= value <= hi
            if not in_bounds:
                print(f"[plausibility] DROPPED: {test_name} = {value} (expected {lo}–{hi})")
            return in_bounds
    return True


# ── Pass 1: pymupdf text extraction ──────────────────────────────────────────

def _extract_pdf_text(pdf_bytes: bytes) -> Optional[str]:
    """
    Try to extract embedded text from PDF using pymupdf.
    Returns the full text if meaningful, None if PDF is image-based.
    Fast: ~0.1s, zero API calls.
    """
    try:
        doc   = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()

        full_text = "\n".join(pages).strip()

        if len(full_text) >= MIN_TEXT_LENGTH:
            print(f"[extractor] pymupdf: {len(full_text)} chars — using text path (saves vision quota)")
            return full_text

        print(f"[extractor] pymupdf: only {len(full_text)} chars — likely scanned, falling back to vision")
        return None

    except Exception as e:
        print(f"[extractor] pymupdf failed: {e} — falling back to vision")
        return None


TEXT_STRUCTURING_PROMPT = """You are a medical data extractor. Read this lab report text.

Extract patient info from the report header:
- patient.age: age as integer (years only), null if not found
- patient.gender: "male" or "female" only, null if not found

Extract EVERY test result row. Skip section headers like "COMPLETE BLOOD COUNT".

For each test:
- test_name: full name as printed
- value: numeric result as a number only (not a string)
- unit: unit as printed
- reference_range: range as printed, null only if truly absent

Lab report text:
{text}

Return ONLY valid JSON:
{{"patient": {{"age": <int|null>, "gender": <"male"|"female"|null>}}, "tests": [...]}}
No markdown. No code fences. No extra text."""


def _structure_text_with_groq(text: str) -> LabReport:
    """Send extracted PDF text to Groq text model for JSON structuring."""
    client = _get_text_client()

    prompt = TEXT_STRUCTURING_PROMPT.format(text=text[:6000])  # cap at 6k chars (safety)

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            raw = response.choices[0].message.content

            # Strip markdown fences if present
            raw = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
            raw = re.sub(r'\s*```$',          '', raw,         flags=re.MULTILINE).strip()

            return LabReport.model_validate_json(raw)

        except Exception as e:
            err = str(e).lower()
            is_rate = "429" in str(e) or "rate" in err or "quota" in err
            if is_rate and attempt == 0:
                print("[extractor] Groq rate limit on text model — sleeping 5s")
                time.sleep(5)
                continue
            raise

    raise RuntimeError("Groq text structuring failed after retry.")


# ── Pass 2: vision extraction (fallback) ──────────────────────────────────────

def pdf_to_images(pdf_bytes: bytes) -> list[Image.Image]:
    try:
        return convert_from_bytes(pdf_bytes, dpi=150, fmt="png")
    except Exception as e:
        raise RuntimeError(f"PDF conversion failed. Is poppler installed? Error: {e}")


def _pil_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


VISION_PROMPT = """You are a medical data extractor. Read this lab report image carefully.

First, extract patient info from the report header:
- patient.age: age as integer (years only), null if not found
- patient.gender: "male" or "female" only (lowercase), null if not found

Then extract EVERY test result row. Skip section headers like "COMPLETE BLOOD COUNT".

For each test:
- test_name: full name as printed
- value: numeric result as a number only — not a string
- unit: unit as printed
- reference_range: range AS PRINTED — null only if truly absent

Return ONLY valid JSON:
{"patient": {"age": <int|null>, "gender": <"male"|"female"|null>}, "tests": [...]}
No markdown. No code fences. No extra text."""


def _extract_page_with_vision(client: OpenAI, image: Image.Image) -> LabReport:
    img_b64 = _pil_to_base64(image)

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=VISION_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                        {"type": "text",      "text": VISION_PROMPT}
                    ]
                }],
            )
            raw = response.choices[0].message.content
            raw = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
            raw = re.sub(r'\s*```$',          '', raw,         flags=re.MULTILINE).strip()
            return LabReport.model_validate_json(raw)

        except Exception as e:
            err = str(e).lower()
            is_rate = "429" in str(e) or "quota" in err or "rate" in err or "exhausted" in err
            if is_rate and attempt == 0:
                print("[extractor] Vision rate limit — sleeping 62s")
                time.sleep(62)
                continue
            raise


def _collect_tests(report: LabReport, patient_info: dict, all_tests: list, seen: set) -> None:
    """Merge report results into running lists (shared by both paths)."""
    if patient_info["age"] is None and report.patient.age:
        patient_info["age"] = report.patient.age
    if patient_info["gender"] is None and report.patient.gender:
        patient_info["gender"] = report.patient.gender.lower()

    for t in report.tests:
        if t.value is not None and not _is_plausible(t.test_name, t.value):
            continue
        key = t.test_name.strip().lower()
        if key not in seen:
            seen.add(key)
            all_tests.append({
                "test_name":       t.test_name,
                "value":           t.value,
                "unit":            normalize_unit_alias(t.unit),
                "reference_range": t.reference_range,
            })


# ── Public entry point ────────────────────────────────────────────────────────

def extract_tests_from_report(pdf_bytes: bytes) -> dict:
    """
    Two-pass extraction:
      Pass 1: pymupdf text → Groq text model (saves vision quota)
      Pass 2: pdf2image → Gemini Vision (fallback for scanned PDFs)

    Returns {"tests": [...], "patient": {"age": int|None, "gender": str|None}}
    """
    all_tests:   list[dict] = []
    seen:        set[str]   = set()
    patient_info             = {"age": None, "gender": None}

    # ── Pass 1: try pymupdf ───────────────────────────────────────────────────
    pdf_text = _extract_pdf_text(pdf_bytes)
    if pdf_text:
        try:
            report = _structure_text_with_groq(pdf_text)
            _collect_tests(report, patient_info, all_tests, seen)
            print(f"[extractor] Text path success: {len(all_tests)} tests extracted")
        except Exception as e:
            print(f"[extractor] Groq text structuring failed: {e} — trying vision fallback")
            all_tests.clear()
            seen.clear()
            patient_info = {"age": None, "gender": None}
            # fall through to Pass 2

    # ── Pass 2: vision fallback ───────────────────────────────────────────────
    if not all_tests:
        print("[extractor] Using vision path (scanned PDF or text extraction failed)")
        images = pdf_to_images(pdf_bytes)
        client = _get_vision_client()

        for page_num, image in enumerate(images, start=1):
            try:
                report = _extract_page_with_vision(client, image)
                _collect_tests(report, patient_info, all_tests, seen)
            except Exception as e:
                print(f"[extractor] Vision page {page_num} failed: {e}")
                continue

    if not all_tests:
        raise ValueError(
            "No test results could be extracted. "
            "Ensure the report is a clear, non-rotated, unencrypted PDF and try again."
        )

    return {"tests": all_tests, "patient": patient_info}
