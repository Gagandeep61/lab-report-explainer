# main.py — FastAPI application
# Run: uvicorn main:app --reload --port 8000

import json
import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from extractor import extract_tests_from_report
from explainer import generate_chat_response, generate_explanations_batch
from exporter import generate_pdf
from rules import apply_rules, compare_two_reports
from generate_samples import generate_all_samples


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    generate_all_samples()
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Lab Report Explainer",
    description="AI-powered plain-language interpretation of blood test reports.",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lab-report-explainer-phi.vercel.app",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Validators ────────────────────────────────────────────────────────────────

def _validate_gender(gender: Optional[str]) -> str:
    if not gender:
        return "male"
    g = gender.strip().lower()
    return g if g in ("male", "female") else "male"

def _validate_language(language: str) -> str:
    lang = language.strip().lower()
    return lang if lang in ("english", "hindi", "punjabi") else "english"

def _validate_mode(mode: str) -> str:
    return "doctor" if mode.strip().lower() == "doctor" else "patient"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/analyze")
async def analyze_report(
    file:     UploadFile = File(...),
    language: str        = Form("english"),
    mode:     str        = Form("patient"),
):
    language = _validate_language(language)
    mode     = _validate_mode(mode)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()

    MAX_SIZE = 20 * 1024 * 1024
    if len(pdf_bytes) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 20 MB.")

    try:
        result = extract_tests_from_report(pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    raw_tests = result["tests"]
    age    = result["patient"]["age"] or 30
    gender = result["patient"]["gender"] or "male"

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
    age:      int = Form(30),
    gender:   str = Form("male"),
    language: str = Form("english"),
    mode:     str = Form("patient"),
):
    gender   = _validate_gender(gender)
    language = _validate_language(language)
    mode     = _validate_mode(mode)

    try:
        flagged_tests = json.loads(tests)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="'tests' must be valid JSON.")

    try:
        explained = generate_explanations_batch(flagged_tests, age, gender, language, mode)
    except Exception:
        explained = [
            {**t, "explanation": "Explanation temporarily unavailable.", "doctor_questions": []}
            for t in flagged_tests
        ]

    return {"tests": explained}


@app.post("/compare")
async def compare_reports(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
):
    bytes1 = await file1.read()
    bytes2 = await file2.read()

    try:
        res1 = extract_tests_from_report(bytes1)
        res2 = extract_tests_from_report(bytes2)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    age    = res1["patient"]["age"] or 30
    gender = res1["patient"]["gender"] or "male"

    flagged1 = [apply_rules(t, age, gender) for t in res1["tests"]]
    flagged2 = [apply_rules(t, age, gender) for t in res2["tests"]]
    diff     = compare_two_reports(flagged1, flagged2)

    return {
        "diff": diff,
        "summary": {
            "improved":       sum(1 for d in diff if d["change"] == "improved"),
            "worsened":       sum(1 for d in diff if d["change"] == "worsened"),
            "stable":         sum(1 for d in diff if d["change"] == "stable"),
            "total_compared": len(diff),
        }
    }


@app.post("/chat")
async def chat(
    message:        str = Form(...),
    report_context: str = Form(...),
    history:        str = Form("[]"),
    age:            int = Form(30),
    gender:         str = Form("male"),
    language:       str = Form("english"),
):
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
    age:    int = Form(30),
    gender: str = Form("male"),
):
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
        "status":             "ok",
        # Extraction
        "openrouter_set":     bool(os.getenv("OPENROUTER_API_KEY")),
        "vision_model":       "google/gemini-2.0-flash-exp:free (OpenRouter — scanned PDFs only)",
        "text_extract_model": "llama-3.1-8b-instant (Groq — digital PDFs)",
        # Explanation + Chat
        "groq_set":           bool(os.getenv("GROQ_API_KEY")),
        "explanation_model":  "llama-3.3-70b-versatile (Groq — 14,400 RPD)",
        # Translation
        "sarvam_set":         bool(os.getenv("SARVAM_API_KEY")),
        "translation":        "Sarvam AI mayura:v1 (Hindi/Punjabi)",
    }


@app.get("/")
async def root():
    return {
        "name":    "Lab Report Explainer API",
        "version": "1.2.0",
        "status":  "ok",
        "docs":    "/docs",
        "health":  "/health",
    }
