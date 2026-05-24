# main.py — FastAPI application
# All endpoints defined here. Business logic stays in the modules.
# Run with: uvicorn main:app --reload --port 8000
 
import json
import os
from typing import Optional
 
from dotenv import load_dotenv
load_dotenv()  # Must be first — loads GEMINI_API_KEY before any module import uses it
 
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
 
from extractor import extract_tests_from_report
from explainer import generate_chat_response, generate_explanations_batch
from exporter import generate_pdf
from rules import apply_rules, compare_two_reports
 
# ── App setup ─────────────────────────────────────────────────────────────────
 
app = FastAPI(
    title="Lab Report Explainer",
    description="AI-powered plain-language interpretation of blood test reports.",
    version="1.0.0",
)
 
# CORS: allow all origins so index.html opened directly in browser can call this API.
# In production, replace "*" with your actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lab-report-explainer-phi.vercel.app/"],
    allow_methods=["*"],
    allow_headers=["*"],
)
 
 
# ── Helper ────────────────────────────────────────────────────────────────────
 
def _validate_gender(gender: str) -> str:
    g = gender.strip().lower()
    if g not in ("male", "female"):
        raise HTTPException(status_code=422, detail="gender must be 'male' or 'female'")
    return g
 
def _validate_language(language: str) -> str:
    valid = ("english", "hindi", "punjabi")
    lang = language.strip().lower()
    if lang not in valid:
        lang = "english"
    return lang
 
def _validate_mode(mode: str) -> str:
    m = mode.strip().lower()
    return "doctor" if m == "doctor" else "patient"
 
 
# ── Endpoints ─────────────────────────────────────────────────────────────────
 
@app.post("/analyze")
async def analyze_report(
    file: UploadFile = File(..., description="PDF lab report"),
    age: int = Form(..., ge=1, le=120),
    gender: str = Form(...),
    language: str = Form("english"),
    mode: str = Form("patient"),
):
    """
    Main pipeline endpoint.
    1. Extract tests from PDF via Gemini Vision
    2. Normalize units
    3. Apply rules engine (flag each test)
    4. Generate batch explanations via Gemini Flash
    5. Return enriched test list
    """
    gender = _validate_gender(gender)
    language = _validate_language(language)
    mode = _validate_mode(mode)
 
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are accepted.")
 
    try:
        pdf_bytes = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read uploaded file.")
 
    # Step 1 + 2: Extract and normalize
    try:
        raw_tests = extract_tests_from_report(pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
    # Step 3: Rules engine — deterministic, no LLM
    flagged_tests = [apply_rules(t, age, gender) for t in raw_tests]
 
    # Step 4: Batch explanation — one Gemini call for all tests
    try:
        explained_tests = generate_explanations_batch(
            flagged_tests, age, gender, language, mode
        )
    except Exception as e:
        # Explanation failure shouldn't kill the whole response.
        # Return flagged tests without explanations.
        explained_tests = [
            {**t, "explanation": "Explanation temporarily unavailable.", "doctor_questions": []}
            for t in flagged_tests
        ]
 
    n_flagged = sum(1 for t in explained_tests if t.get("flag") != "Normal")
 
    return {
        "tests": explained_tests,
        "patient": {"age": age, "gender": gender},
        "total": len(explained_tests),
        "flagged_count": n_flagged,
    }
 
 
@app.post("/explain")
async def explain_report(
    tests: str = Form(..., description="JSON string of flagged tests (no explanations)"),
    age: int = Form(..., ge=1, le=120),
    gender: str = Form(...),
    language: str = Form("english"),
    mode: str = Form("patient"),
):
    """
    Re-explain endpoint — called when user toggles language or view mode.
    Takes the already-flagged tests (no re-extraction) and returns new explanations.
    This is much faster than /analyze since extraction is skipped.
    """
    gender = _validate_gender(gender)
    language = _validate_language(language)
    mode = _validate_mode(mode)
 
    try:
        flagged_tests = json.loads(tests)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="'tests' must be valid JSON.")
 
    try:
        explained_tests = generate_explanations_batch(
            flagged_tests, age, gender, language, mode
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explanation failed: {e}")
 
    return {"tests": explained_tests}
 
 
@app.post("/compare")
async def compare_reports(
    file1: UploadFile = File(..., description="Older PDF report"),
    file2: UploadFile = File(..., description="Newer PDF report"),
    age: int = Form(..., ge=1, le=120),
    gender: str = Form(...),
):
    """
    Compare two lab reports and return a diff.
    Extracts both, runs rules on both, then diffs flag + value changes.
    No explanation generation — diff table is self-explanatory.
    """
    gender = _validate_gender(gender)
 
    try:
        bytes1 = await file1.read()
        bytes2 = await file2.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read uploaded files.")
 
    try:
        raw1 = extract_tests_from_report(bytes1)
        raw2 = extract_tests_from_report(bytes2)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))
 
    flagged1 = [apply_rules(t, age, gender) for t in raw1]
    flagged2 = [apply_rules(t, age, gender) for t in raw2]
 
    diff = compare_two_reports(flagged1, flagged2)
 
    improved = sum(1 for d in diff if d["change"] == "improved")
    worsened = sum(1 for d in diff if d["change"] == "worsened")
 
    return {
        "diff": diff,
        "summary": {
            "improved": improved,
            "worsened": worsened,
            "stable": sum(1 for d in diff if d["change"] == "stable"),
            "total_compared": len(diff),
        }
    }
 
 
@app.post("/chat")
async def chat(
    message: str = Form(...),
    report_context: str = Form(..., description="JSON string of test summaries"),
    history: str = Form("[]"),
    age: int = Form(..., ge=1, le=120),
    gender: str = Form(...),
    language: str = Form("english"),
):
    """
    Bounded RAG chat endpoint.
    History is maintained client-side (sent with each request).
    Turn counting is also client-side (8-turn cap enforced in JS).
    Server enforces: last 6 turns only (3 user/assistant pairs) to stay within context.
    """
    gender = _validate_gender(gender)
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
    tests: str = Form(..., description="JSON string of explained tests"),
    age: int = Form(..., ge=1, le=120),
    gender: str = Form(...),
):
    """
    Generate and stream a PDF report card.
    Returns the PDF as a file download.
    """
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
    """Simple health check. Hit this to wake up the server before demo."""
    return {
        "status": "ok",
        "api_key_set": bool(os.getenv("GEMINI_API_KEY")),
        "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "sdk": "google-genai",
    }
 