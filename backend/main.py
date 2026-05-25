# main.py — FastAPI application
# Run with: uvicorn main:app --reload --port 8000

import json
import os
from typing import Optional

from dotenv import load_dotenv
load_dotenv()  # Must be first — loads GEMINI_API_KEY before any module imports use it

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from extractor import extract_tests_from_report
from explainer import generate_chat_response, generate_explanations_batch
from exporter import generate_pdf
from rules import apply_rules, compare_two_reports

app = FastAPI(
    title="Lab Report Explainer",
    description="AI-powered plain-language interpretation of blood test reports.",
    version="1.0.0",
)

# CORS — no trailing slash. Browsers send Origin without one.
# FastAPI CORS does exact string match — trailing slash = CORS block for every request.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lab-report-explainer-phi.vercel.app",  # production
        "http://localhost:5500",                         # local dev (Live Server)
        "http://127.0.0.1:5500",
        "null",                                          # file:// opened directly in browser
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Validators ────────────────────────────────────────────────────────────────

def _validate_gender(gender: str) -> str:
    g = gender.strip().lower()
    if g not in ("male", "female"):
        raise HTTPException(status_code=422, detail="gender must be 'male' or 'female'")
    return g

def _validate_language(language: str) -> str:
    lang = language.strip().lower()
    return lang if lang in ("english", "hindi", "punjabi") else "english"

def _validate_mode(mode: str) -> str:
    return "doctor" if mode.strip().lower() == "doctor" else "patient"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/analyze")
async def analyze_report(
    file:     UploadFile = File(...),
    age:      int        = Form(..., ge=1, le=120),
    gender:   str        = Form(...),
    language: str        = Form("english"),
    mode:     str        = Form("patient"),
):
    """Full pipeline: extract → flag → explain."""
    gender   = _validate_gender(gender)
    language = _validate_language(language)
    mode     = _validate_mode(mode)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()

    try:
        raw_tests = extract_tests_from_report(pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    flagged_tests = [apply_rules(t, age, gender) for t in raw_tests]

    try:
        explained_tests = generate_explanations_batch(flagged_tests, age, gender, language, mode)
    except Exception:
        explained_tests = [
            {**t, "explanation": "Explanation temporarily unavailable.", "doctor_questions": []}
            for t in flagged_tests
        ]

    return {
        "tests":         explained_tests,
        "patient":       {"age": age, "gender": gender},
        "total":         len(explained_tests),
        "flagged_count": sum(1 for t in explained_tests if t.get("flag") != "Normal"),
    }


@app.post("/explain")
async def explain_report(
    tests:    str = Form(...),
    age:      int = Form(..., ge=1, le=120),
    gender:   str = Form(...),
    language: str = Form("english"),
    mode:     str = Form("patient"),
):
    """Re-explain already-flagged tests with a different language or view mode."""
    gender   = _validate_gender(gender)
    language = _validate_language(language)
    mode     = _validate_mode(mode)

    try:
        flagged_tests = json.loads(tests)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="'tests' must be valid JSON.")

    try:
        explained = generate_explanations_batch(flagged_tests, age, gender, language, mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explanation failed: {e}")

    return {"tests": explained}


@app.post("/compare")
async def compare_reports(
    file1:  UploadFile = File(...),
    file2:  UploadFile = File(...),
    age:    int        = Form(..., ge=1, le=120),
    gender: str        = Form(...),
):
    """Extract both PDFs, flag both, return a diff."""
    gender = _validate_gender(gender)

    bytes1 = await file1.read()
    bytes2 = await file2.read()

    try:
        raw1 = extract_tests_from_report(bytes1)
        raw2 = extract_tests_from_report(bytes2)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    flagged1 = [apply_rules(t, age, gender) for t in raw1]
    flagged2 = [apply_rules(t, age, gender) for t in raw2]
    diff     = compare_two_reports(flagged1, flagged2)

    return {
        "diff": diff,
        "summary": {
            "improved":      sum(1 for d in diff if d["change"] == "improved"),
            "worsened":      sum(1 for d in diff if d["change"] == "worsened"),
            "stable":        sum(1 for d in diff if d["change"] == "stable"),
            "total_compared": len(diff),
        }
    }


@app.post("/chat")
async def chat(
    message:        str = Form(...),
    report_context: str = Form(...),
    history:        str = Form("[]"),
    age:            int = Form(..., ge=1, le=120),
    gender:         str = Form(...),
    language:       str = Form("english"),
):
    """Bounded RAG chat — 8-turn cap enforced client-side, history trimmed server-side."""
    gender   = _validate_gender(gender)
    language = _validate_language(language)

    try:
        history_list = json.loads(history)
    except json.JSONDecodeError:
        history_list = []

    try:
        reply = generate_chat_response(
            message=message,
            report_context=report_context,
            history=history_list,
            age=age,
            gender=gender,
            language=language,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {e}")

    return {"reply": reply}


@app.post("/export")
async def export_pdf(
    tests:  str = Form(...),
    age:    int = Form(..., ge=1, le=120),
    gender: str = Form(...),
):
    """Generate and stream a PDF report card."""
    gender = _validate_gender(gender)

    try:
        tests_list = json.loads(tests)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="'tests' must be valid JSON.")

    try:
        pdf_bytes = generate_pdf(tests_list, {"age": age, "gender": gender})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=lab-report-summary.pdf"},
    )


@app.get("/health")
async def health():
    return {
        "status":      "ok",
        "api_key_set": bool(os.getenv("GEMINI_API_KEY")),
        "model":       os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "sdk":         "google-genai",
    }
