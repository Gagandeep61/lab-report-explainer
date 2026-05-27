# extractor.py — PDF → structured JSON via OpenRouter (gemini-2.0-flash-exp:free)

import base64
import io
import os
import re
import time
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from pdf2image import convert_from_bytes
from PIL import Image
from pydantic import BaseModel, field_validator

from units import normalize_unit_alias

_client: Optional[OpenAI] = None
EXTRACTION_MODEL = "google/gemini-2.0-flash-exp:free"


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set. Add to .env and HF secrets.")
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    return _client


class PatientInfo(BaseModel):
    age: Optional[int] = None
    gender: Optional[str] = None


class TestResult(BaseModel):
    test_name: str
    value: Optional[float] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None

    @field_validator("value", mode="before")
    @classmethod
    def value_cannot_be_negative(cls, v) -> Optional[float]:
        """
        FIX: return None instead of raising ValueError.
        Previously a single negative value caused the ENTIRE page to fail validation,
        silently dropping all tests from that page.
        Now only the bad value is discarded; other tests on the page survive.
        """
        if v is None:
            return None
        try:
            fv = float(v)
            if fv < 0:
                print(f"[extractor] Negative value {fv} discarded (likely misread dash).")
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
    tests: list[TestResult]


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


def pdf_to_images(pdf_bytes: bytes) -> list[Image.Image]:
    try:
        return convert_from_bytes(pdf_bytes, dpi=150, fmt="png")
    except Exception as e:
        raise RuntimeError(f"PDF conversion failed. Is poppler installed? Error: {e}")


def _pil_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


EXTRACTION_PROMPT = """You are a medical data extractor. Read this lab report image carefully.

First, extract patient info from the report header:
- patient.age: age as integer (years only), null if not found
- patient.gender: "male" or "female" only (lowercase), null if not found

Then extract EVERY test result row. Skip section headers like "COMPLETE BLOOD COUNT".

For each test result:
- test_name: full name as printed (e.g. "HbA1c", "Serum Creatinine")
- value: numeric result as a number only — not a string
- unit: unit as printed (%, mg/dL, U/L etc.)
- reference_range: normal range AS PRINTED — null only if truly absent

Return ONLY a valid JSON object:
{"patient": {"age": <int|null>, "gender": <"male"|"female"|null>}, "tests": [...]}
No markdown. No code fences. No extra text."""


def _call_openrouter_safe(client: OpenAI, image: Image.Image) -> LabReport:
    img_b64 = _pil_to_base64(image)

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=EXTRACTION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                            },
                            {"type": "text", "text": EXTRACTION_PROMPT}
                        ]
                    }
                ],
                # NOTE: response_format json_object omitted — not reliably supported
                # by all models via OpenRouter. We strip markdown fences manually below.
            )
            raw = response.choices[0].message.content

            # FIX: strip markdown fences before validation — OpenRouter sometimes wraps
            # JSON in ```json ... ``` even when instructed not to.
            raw = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
            raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()

            return LabReport.model_validate_json(raw)

        except Exception as e:
            err = str(e).lower()
            is_rate_limit = "429" in str(e) or "quota" in err or "rate" in err or "exhausted" in err
            if is_rate_limit and attempt == 0:
                print("[extractor] Rate limit. Sleeping 62s…")
                time.sleep(62)
                continue
            raise


def extract_tests_from_report(pdf_bytes: bytes) -> dict:
    """
    Returns {"tests": [...], "patient": {"age": int|None, "gender": str|None}}
    """
    images = pdf_to_images(pdf_bytes)
    client = _get_client()

    all_tests: list[dict] = []
    seen: set[str] = set()
    patient_info = {"age": None, "gender": None}

    for page_num, image in enumerate(images, start=1):
        try:
            report = _call_openrouter_safe(client, image)
        except Exception as e:
            print(f"[extractor] Page {page_num} failed — skipping: {e}")
            continue

        if patient_info["age"] is None and report.patient.age:
            patient_info["age"] = report.patient.age
        if patient_info["gender"] is None and report.patient.gender:
            patient_info["gender"] = report.patient.gender.lower()

        for t in report.tests:
            if t.value is not None and not _is_plausible(t.test_name, t.value):
                continue

            normalised_unit = normalize_unit_alias(t.unit)
            key = t.test_name.strip().lower()

            if key not in seen:
                seen.add(key)
                all_tests.append({
                    "test_name":       t.test_name,
                    "value":           t.value,
                    "unit":            normalised_unit,
                    "reference_range": t.reference_range,
                })

    if not all_tests:
        raise ValueError(
            "No test results could be extracted from this PDF. "
            "Ensure the report is a clear, non-rotated, unencrypted scan and try again."
        )

    return {"tests": all_tests, "patient": patient_info}
