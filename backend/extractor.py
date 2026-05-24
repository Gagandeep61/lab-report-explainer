# extractor.py — PDF → structured JSON via Gemini Vision
#
# SDK change: google-generativeai is deprecated. New SDK is google-genai.
# Import changed: from google import genai (not import google.generativeai as genai)
# Client changed: genai.Client(api_key=...) instead of genai.configure(api_key=...)
#
# instructor dropped — not needed. The new SDK supports response_schema natively.
# Passing a Pydantic model as response_schema enforces JSON schema at the model level.
# This is exactly what instructor did, just without the extra dependency.
#
# 3-layer defence against bad data — unchanged from original design:
#   Layer 1: response_schema enforces JSON shape at model level
#   Layer 2: Pydantic field_validator rejects impossible types (negative values)
#   Layer 3: PLAUSIBILITY_BOUNDS catches hallucinated impossible numbers
#
# INTERVIEW TALKING POINT:
#   "I use Gemini's native response_schema parameter with a Pydantic model.
#    This is what libraries like instructor do under the hood — they translate
#    Pydantic models into JSON schemas and pass them to the model.
#    I chose the native approach because it is directly supported by Google's SDK
#    and removes a dependency that could break on SDK version changes.
#    The Pydantic validators then catch domain-specific errors like negative lab
#    values. On top of that, a physiological plausibility dict catches hallucinated
#    values that pass the schema check but are impossible for a living human —
#    for example, a haemoglobin of 1400 g/dL from misreading the platelet column."
 
import io
import os
import time
from typing import Optional
 
from dotenv import load_dotenv
load_dotenv()
 
from google import genai
from google.genai import types
from pdf2image import convert_from_bytes
from PIL import Image
from pydantic import BaseModel, field_validator
 
from units import normalize_unit_alias
 
# ── Client (lazy init) ────────────────────────────────────────────────────────
# Created on first use, not at import time.
# This ensures load_dotenv() in main.py has already run before we read the key.
 
_client: genai.Client | None = None
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
 
 
def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Copy .env.example to .env and add your key from aistudio.google.com."
            )
        _client = genai.Client(api_key=api_key)
    return _client
 
 
# ── Pydantic models ───────────────────────────────────────────────────────────
 
class TestResult(BaseModel):
    """
    Schema for one lab test row.
    Passed as response_schema to Gemini — the model must return JSON
    that matches this shape. Optional fields cover missing columns.
    """
    test_name: str
    value: Optional[float] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None  # as printed: "70-100", "<200", ">40"
 
    @field_validator("value")
    @classmethod
    def value_cannot_be_negative(cls, v: Optional[float]) -> Optional[float]:
        """
        Layer 2: Lab values are never negative.
        A negative number means Gemini read a dash or hyphen as a minus sign.
        Reject it — a ghost negative is worse than a null.
        """
        if v is not None and v < 0:
            raise ValueError(
                f"Value {v} is negative — likely a misread dash. Discarding."
            )
        return v
 
    @field_validator("test_name")
    @classmethod
    def name_must_be_meaningful(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) < 2 or v.isdigit():
            raise ValueError("test_name is too short or numeric — not a real test name.")
        return v
 
 
class LabReport(BaseModel):
    """Wrapper so Gemini extracts all tests in one shot."""
    tests: list[TestResult]
 
 
# ── Physiological plausibility bounds ────────────────────────────────────────
# Layer 3: values outside these ranges are impossible for a living human.
# Catches hallucinations that pass the Pydantic schema check.
# Only top ~20 tests — enough coverage without over-engineering.
# Units match what Indian labs report in (mg/dL, g/dL, cells/μL, etc.)
 
PLAUSIBILITY_BOUNDS: dict[str, tuple[float, float]] = {
    "glucose":      (0,   2000),      # mg/dL
    "hba1c":        (0,   25),        # %
    "hemoglobin":   (0,   25),        # g/dL
    "haemoglobin":  (0,   25),
    "hb":           (0,   25),
    "wbc":          (0,   200_000),   # cells/μL
    "platelet":     (0,   2_000_000), # cells/μL
    "sodium":       (100, 200),       # mEq/L — outside = incompatible with life
    "potassium":    (1,   10),        # mEq/L
    "cholesterol":  (0,   1500),      # mg/dL
    "triglyceride": (0,   5000),      # mg/dL
    "creatinine":   (0,   50),        # mg/dL
    "uric acid":    (0,   50),        # mg/dL
    "tsh":          (0,   1000),      # mIU/L
    "bilirubin":    (0,   100),       # mg/dL
    "alt":          (0,   10_000),    # U/L
    "sgpt":         (0,   10_000),
    "ast":          (0,   10_000),
    "sgot":         (0,   10_000),
    "albumin":      (0,   10),        # g/dL
    "calcium":      (0,   20),        # mg/dL
    "vitamin d":    (0,   500),       # ng/mL
    "vitamin b12":  (0,   50_000),    # pg/mL
    "ferritin":     (0,   100_000),   # ng/mL
    "iron":         (0,   1000),      # μg/dL
}
 
 
def _is_plausible(test_name: str, value: float) -> bool:
    """
    Return False if value is outside physiological limits.
    Unknown tests pass through — never discard data we can't verify.
    """
    test_lower = test_name.strip().lower()
    for keyword, (lo, hi) in PLAUSIBILITY_BOUNDS.items():
        if keyword in test_lower:
            in_bounds = lo <= value <= hi
            if not in_bounds:
                print(
                    f"[plausibility] DROPPED: {test_name} = {value} "
                    f"(expected {lo}–{hi}). Likely hallucination."
                )
            return in_bounds
    return True
 
 
# ── PDF utilities ────────────────────────────────────────────────────────────
 
def pdf_to_images(pdf_bytes: bytes) -> list[Image.Image]:
    """
    Convert PDF pages to PIL Images via pdf2image (wraps poppler).
    DPI 150: readable by Gemini, keeps token cost low.
    Requires poppler at OS level — see GUIDE.md Step 2.
    """
    try:
        return convert_from_bytes(pdf_bytes, dpi=150, fmt="png")
    except Exception as e:
        raise RuntimeError(
            f"PDF conversion failed. Is poppler installed? "
            f"Mac: brew install poppler | Ubuntu: sudo apt install poppler-utils. "
            f"Error: {e}"
        )
 
 
def _pil_to_bytes(img: Image.Image) -> bytes:
    """Convert PIL Image to PNG bytes for the Gemini API."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
 
 
EXTRACTION_PROMPT = """You are a medical data extractor. Read this lab report image carefully.
 
Extract EVERY test result row. Skip section headers like "COMPLETE BLOOD COUNT".
 
For each test result:
- test_name: full name as printed (e.g. "HbA1c", "Serum Creatinine")
- value: the numeric result as a number only — not a string, not a number with units
- unit: unit of measurement as printed (e.g. "%", "mg/dL", "U/L")
- reference_range: the normal range AS PRINTED — check columns labelled "Normal Range",
  "Ref. Range", or "Biological Reference Interval" even if far from the value column.
  Use null only if no range is shown for this test.
 
If a value cannot be read clearly, use null for that field only."""
 
 
def _call_gemini_safe(client: genai.Client, image: Image.Image) -> LabReport:
    """
    Send one PDF page to Gemini Vision with structured output.
 
    response_schema=LabReport tells Gemini to return JSON that matches
    the LabReport Pydantic model. The SDK enforces this at the model level.
    We then validate and parse with model_validate_json().
 
    Rate limit (gemini-2.5-flash free tier): 10 RPM.
    On 429: sleep 62 seconds (slightly more than 60 to clear the window) and retry once.
    """
    img_bytes = _pil_to_bytes(image)
 
    # Build multimodal content: image part + text prompt
    # New SDK: types.Part with inline_data for binary content
    img_part = types.Part(
        inline_data=types.Blob(
            mime_type="image/png",
            data=img_bytes,
        )
    )
 
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=LabReport,  # Pydantic model → JSON schema enforcement
    )
 
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[img_part, EXTRACTION_PROMPT],
                config=config,
            )
            # Parse and validate the response with Pydantic
            return LabReport.model_validate_json(response.text)
 
        except Exception as e:
            err = str(e).lower()
            is_rate_limit = "429" in str(e) or "quota" in err or "rate" in err or "exhausted" in err
 
            if is_rate_limit and attempt == 0:
                print(f"[extractor] Rate limit hit. Sleeping 62s before retry…")
                time.sleep(62)
                continue  # retry
 
            raise  # non-rate-limit error or second attempt failed
 
 
# ── Main extraction function ─────────────────────────────────────────────────
 
def extract_tests_from_report(pdf_bytes: bytes) -> list[dict]:
    """
    Full pipeline: PDF bytes → clean list of test dicts for the rules engine.
 
    1. pdf_bytes → list of PIL Images (pdf2image)
    2. Per page: Gemini Vision + response_schema → LabReport (Pydantic validated)
    3. Per test: plausibility bounds check (Layer 3)
    4. Unit alias normalisation (gm% → g/dL etc.)
    5. Deduplicate by test name (first occurrence wins)
    6. Return clean list
 
    Raises ValueError if nothing could be extracted (bad scan, encrypted PDF, etc.)
    """
    images = pdf_to_images(pdf_bytes)
    client = _get_client()
 
    all_tests: list[dict] = []
    seen: set[str] = set()
 
    for page_num, image in enumerate(images, start=1):
        try:
            report = _call_gemini_safe(client, image)
        except Exception as e:
            print(f"[extractor] Page {page_num} failed — skipping: {e}")
            continue
 
        for t in report.tests:
            # Layer 3: physiological plausibility
            if t.value is not None and not _is_plausible(t.test_name, t.value):
                continue  # drop hallucinated value
 
            # Normalise unit alias
            normalised_unit = normalize_unit_alias(t.unit)
 
            key = t.test_name.strip().lower()
            if key not in seen:
                seen.add(key)
                all_tests.append({
                    "test_name": t.test_name,
                    "value":     t.value,
                    "unit":      normalised_unit,
                    "reference_range": t.reference_range,
                })
 
    if not all_tests:
        raise ValueError(
            "No test results could be extracted from this PDF. "
            "Ensure the report is a clear, non-rotated, unencrypted scan and try again."
        )
 
    return all_tests
 