# extractor.py — PDF → structured JSON via Gemini Vision + instructor
#
# Three-layer defence against bad data:
#   Layer 1 — instructor forces Gemini to return schema-valid JSON.
#              No more manual regex JSON-cleaning. Pydantic validates the shape.
#   Layer 2 — field_validator rejects negative values before they reach the UI.
#   Layer 3 — physiological plausibility bounds catch hallucinated values
#              (e.g. haemoglobin = 1400 from misreading the platelet column).
#
# INTERVIEW TALKING POINT:
#   "I isolated three failure modes: malformed JSON (instructor), impossible types
#    (Pydantic validators), and physiologically impossible values (bounds check).
#    Each layer catches a different class of LLM error."
 
import os
import time
from typing import Optional
 
import google.generativeai as genai
import instructor
from google.api_core.exceptions import ResourceExhausted
from pdf2image import convert_from_bytes
from PIL import Image
from pydantic import BaseModel, field_validator
 
from units import normalize_unit_alias
 
# ── Gemini + instructor setup ────────────────────────────────────────────────
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "gemini-1.5-flash")
 
def _get_instructor_client():
    """
    Wrap the Gemini model with instructor.
    instructor.Mode.GEMINI_JSON tells instructor to use Gemini's native
    response_schema feature — the most reliable structured-output path.
    """
    gemini_model = genai.GenerativeModel(model_name=EXTRACTION_MODEL)
    return instructor.from_gemini(
        client=gemini_model,
        mode=instructor.Mode.GEMINI_JSON,
    )
 
 
# ── Pydantic models ───────────────────────────────────────────────────────────
 
class TestResult(BaseModel):
    """
    Schema for a single lab test row.
    instructor forces Gemini to return JSON that matches this schema exactly.
    Optional fields allow null when the PDF doesn't show that column.
    """
    test_name: str
    value: Optional[float] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None   # as printed — "70-100", "<200", ">40"
 
    @field_validator("value")
    @classmethod
    def value_cannot_be_negative(cls, v: Optional[float]) -> Optional[float]:
        """
        Layer 2 defence: lab values are never negative.
        A negative value means Gemini misread a dash/hyphen as a minus sign.
        Reject it so the rules engine never flags a ghost number.
        """
        if v is not None and v < 0:
            raise ValueError(f"Lab value {v} is negative — likely a misread dash. Discarding.")
        return v
 
    @field_validator("test_name")
    @classmethod
    def test_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) < 2:
            raise ValueError("test_name is too short to be a real test.")
        return v
 
 
class LabReport(BaseModel):
    """Wrapper so instructor extracts all tests in one shot."""
    tests: list[TestResult]
 
 
# ── Physiological plausibility bounds ────────────────────────────────────────
# Layer 3 defence: if a value is outside the range any living human could have,
# it's a hallucination. We drop it silently and log it.
# Only the 20 most common tests — enough to catch the worst hallucinations.
# More tests → future scope.
#
# Units match what Indian labs typically report in.
# Format: "keyword_in_test_name_lowercase": (absolute_min, absolute_max)
 
PLAUSIBILITY_BOUNDS: dict[str, tuple[float, float]] = {
    "glucose":       (0,   2000),    # mg/dL  — DKA ceiling ~1000; 2000 is impossible
    "hba1c":         (0,   25),      # %
    "hemoglobin":    (0,   25),      # g/dL
    "haemoglobin":   (0,   25),
    "hb":            (0,   25),
    "wbc":           (0,   200_000), # cells/μL
    "platelet":      (0,   2_000_000),
    "sodium":        (100, 200),     # mEq/L  — outside this = incompatible with life
    "potassium":     (1,   10),      # mEq/L
    "cholesterol":   (0,   1500),    # mg/dL
    "triglyceride":  (0,   5000),    # mg/dL
    "creatinine":    (0,   50),      # mg/dL
    "uric acid":     (0,   50),      # mg/dL
    "tsh":           (0,   1000),    # mIU/L
    "bilirubin":     (0,   100),     # mg/dL
    "alt":           (0,   10_000),  # U/L
    "sgpt":          (0,   10_000),
    "ast":           (0,   10_000),
    "sgot":          (0,   10_000),
    "albumin":       (0,   10),      # g/dL
    "calcium":       (0,   20),      # mg/dL
    "vitamin d":     (0,   500),     # ng/mL
    "vitamin b12":   (0,   50_000),  # pg/mL
    "ferritin":      (0,   100_000), # ng/mL
    "iron":          (0,   1000),    # μg/dL
}
 
 
def _is_plausible(test_name: str, value: float) -> bool:
    """
    Return False if the value is physiologically impossible.
    Iterates bounds by keyword match (same pattern as ranges.py).
    Unknown tests return True — we never discard data we can't verify.
    """
    test_lower = test_name.strip().lower()
    for keyword, (lo, hi) in PLAUSIBILITY_BOUNDS.items():
        if keyword in test_lower:
            return lo <= value <= hi
    return True  # Unknown test — pass through
 
 
# ── PDF utilities ────────────────────────────────────────────────────────────
 
def pdf_to_images(pdf_bytes: bytes) -> list[Image.Image]:
    """
    Convert PDF pages to PIL Images using pdf2image.
 
    DPI 150: readable by Gemini Vision, keeps image size manageable.
    Higher DPI = better OCR accuracy but higher token cost per call.
    150 is the sweet spot for standard A4 lab report pages.
 
    Requires poppler-utils installed at OS level (see GUIDE.md Step 3).
    """
    try:
        return convert_from_bytes(pdf_bytes, dpi=150, fmt="png")
    except Exception as e:
        raise RuntimeError(
            f"PDF to image conversion failed. Is poppler installed? "
            f"Run: brew install poppler (Mac) or apt install poppler-utils (Linux). "
            f"Original error: {e}"
        )
 
 
EXTRACTION_PROMPT = """You are a medical data extractor. Read this lab report image carefully.
 
Extract EVERY test result row you can see. Skip section headers like "COMPLETE BLOOD COUNT."
 
For each test result, extract:
- test_name: full name as printed (e.g. "HbA1c", "Serum Creatinine")
- value: the numeric result only — a number, NOT a string with units
- unit: unit of measurement as printed (e.g. "%", "mg/dL", "U/L")
- reference_range: the normal/reference range AS PRINTED in the report — 
  look in columns labelled "Normal Range", "Ref. Range", "Biological Reference Interval"
  even if that column is far from the value column.
  Use null if no range is shown for this test.
 
Important: value must be a number (e.g. 7.2), not a string (e.g. "7.2 H").
If a value cannot be read clearly, use null."""
 
 
# ── Main extraction function ─────────────────────────────────────────────────
 
def _extract_page(client, image: Image.Image, page_num: int) -> list[dict]:
    """
    Extract test results from a single PDF page.
    instructor handles: JSON schema enforcement, Pydantic validation, and
    auto-retry on schema violation (max_retries=2).
    We handle: 429 rate-limit retry, plausibility filtering.
    """
    try:
        report: LabReport = client.chat.completions.create(
            response_model=LabReport,
            messages=[
                {
                    "role": "user",
                    "content": [image, EXTRACTION_PROMPT],
                }
            ],
            max_retries=2,  # instructor retries on Pydantic validation failure
        )
    except ResourceExhausted:
        # 429 — hit rate limit. Sleep 62s and retry once.
        print(f"[extractor] Page {page_num}: rate limit hit, sleeping 62s…")
        time.sleep(62)
        report: LabReport = client.chat.completions.create(
            response_model=LabReport,
            messages=[{"role": "user", "content": [image, EXTRACTION_PROMPT]}],
            max_retries=2,
        )
    except Exception as e:
        print(f"[extractor] Page {page_num} failed: {e}")
        return []
 
    valid = []
    for t in report.tests:
        # Layer 3: plausibility check
        if t.value is not None and not _is_plausible(t.test_name, t.value):
            print(f"[extractor] IMPLAUSIBLE — dropping: {t.test_name} = {t.value}. "
                  f"Likely hallucination.")
            continue
 
        # Normalise unit alias (gm% → g/dL etc.)
        normalised_unit = normalize_unit_alias(t.unit)
 
        valid.append({
            "test_name": t.test_name,
            "value": t.value,
            "unit": normalised_unit,
            "reference_range": t.reference_range,
        })
 
    return valid
 
 
def extract_tests_from_report(pdf_bytes: bytes) -> list[dict]:
    """
    Full extraction pipeline. Returns a clean list of test dicts
    ready for the rules engine.
 
    Steps:
      1. PDF → list of PIL Images (pdf2image)
      2. Per page: Gemini Vision + instructor → LabReport (Pydantic validated)
      3. Per test: plausibility bounds check
      4. Deduplicate by test name (take first occurrence)
      5. Return clean list
    """
    images = pdf_to_images(pdf_bytes)
    client = _get_instructor_client()
 
    all_tests: list[dict] = []
    seen: set[str] = set()
 
    for page_num, image in enumerate(images, start=1):
        page_results = _extract_page(client, image, page_num)
 
        for test in page_results:
            key = test["test_name"].strip().lower()
            if key not in seen:
                seen.add(key)
                all_tests.append(test)
 
    if not all_tests:
        raise ValueError(
            "No test results could be extracted from this PDF. "
            "Please ensure the report is a clear scan (not blurry or rotated) and try again."
        )
 
    return all_tests
 