---
title: Lab Report Explainer
emoji: 🩺
colorFrom: green
colorTo: green
sdk: docker
pinned: false
---

<div align="center">
# 🩺 Lab Report Explainer
 
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Vercel-000000?style=for-the-badge&logo=vercel)](https://lab-report-explainer-phi.vercel.app/)
[![Backend](https://img.shields.io/badge/Backend-HuggingFace%20Spaces-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black)](https://gagan61-lab-report-explainer.hf.space)
[![Deploy to HF](https://img.shields.io/github/actions/workflow/status/gagan61/lab-report-explainer/deploy.yml?style=for-the-badge&label=CI%2FCD&logo=githubactions&logoColor=white)](https://github.com/gagan61/lab-report-explainer/actions)
 
</div>
---
 
## 30-Second Pitch
 
India conducts over **500 million diagnostic tests annually**, yet most patients receive reports in formats they cannot interpret — dense tables, medical abbreviations, no context. This tool takes any blood test PDF from any Indian lab (SRL, Thyrocare, Dr. Lal, Apollo, Metropolis) and runs it through a complete IDP pipeline: Gemini Vision extracts every test row, a deterministic rules engine flags each value against its printed reference range, and a batch LLM call generates 2-sentence plain-language explanations — in English, Hindi, or Punjabi. The result is a structured report card, a chat interface, and a downloadable PDF summary the patient can hand to their doctor.
 
---
 
## ⚡ Quick Stats
 
| | |
|---|---|
| **Labs supported** | SRL · Thyrocare · Dr. Lal PathLabs · Apollo · Metropolis · any structured PDF |
| **Languages** | English · Hindi (Devanagari) · Punjabi (Gurmukhi) |
| **Avg. analysis time** | ~20 seconds end-to-end |
| **Gemini calls per report** | 2 — one Vision extraction, one batch explanation |
| **Plausibility bounds** | 25 common tests (catches hallucinated values) |
| **Fallback reference ranges** | 30 common tests (gender-aware) |
| **Chat limit** | 8 turns per session with medical guardrails |
| **PDF export** | Unicode-safe — renders Hindi and Punjabi correctly |
 
---
 
## 🔴 The Problem
 
India conducts over 500 million diagnostic tests per year, yet studies show that **fewer than 40% of patients understand their lab results** without physician guidance.<sup>[1]</sup> With average doctor consultations lasting under 5 minutes in public healthcare,<sup>[2]</sup> patients leave clinics holding reports they cannot interpret — often turning to unverified sources that cause unnecessary anxiety or, worse, missed warnings.
 
The gap is widest for non-English speakers: with **560 million Hindi speakers** and 33 million Punjabi speakers in India, health literacy tools that operate only in English exclude the majority of the population.
 
<sup>[1] National Health Literacy Survey, India 2022 | [2] Lancet, Primary care consultation length in India</sup>
 
---
 
## ✅ What This Builds
 
A complete Intelligent Document Processing (IDP) pipeline — not a chatbot, not a prediction model. A data pipeline that transforms unstructured medical PDFs into structured, actionable, human-readable summaries.
 
```
PDF (any Indian lab format)
    ↓ Gemini Vision   →  Structured JSON extraction (schema-enforced via Pydantic)
    ↓ Rules engine    →  Deterministic flag: Normal / Caution / See Doctor
    ↓ Gemini Flash    →  Plain-language explanation (English / Hindi / Punjabi)
    ↓ UI              →  Report card + chat + comparison + PDF export
```
 
---
 
## ✨ Features
 
| Feature | Description |
|---|---|
| **Universal PDF extraction** | Works on any Indian lab table layout — no format-specific regex |
| **3-layer validation** | Schema enforcement → negative value rejection → physiological plausibility bounds |
| **Deterministic flagging** | Rules engine (not LLM) compares every value to its own printed reference range |
| **Plain-language explanations** | 2-sentence patient view or 3-bullet clinical brief for doctors |
| **Patient vs Doctor view** | Toggle between plain English and clinical terminology mid-session |
| **Hindi / Punjabi output** | Full multilingual support via Gemini's native language capability |
| **Bounded RAG chat** | Ask questions about results — 8-turn cap, medical guardrails enforced in Python |
| **Two-report comparison** | Upload two reports → see what improved, worsened, or stayed the same |
| **PDF export** | Downloadable report card with Unicode font support for all three languages |
 
---
 
## 🏗️ Architecture
 
```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Vercel)                     │
│          HTML · CSS (Sage & Ink) · Vanilla JS           │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS REST
┌──────────────────────▼──────────────────────────────────┐
│                 Backend (HF Spaces · Docker)             │
│                      FastAPI + Python                    │
│                                                         │
│  ┌─────────────┐   ┌────────────┐   ┌────────────────┐  │
│  │ extractor   │   │   rules    │   │   explainer    │  │
│  │             │   │   engine   │   │                │  │
│  │ pdf2image   │   │            │   │ Gemini Flash   │  │
│  │ Gemini VLM  │──▶│ No LLM     │──▶│ Batch prompts  │  │
│  │ Pydantic    │   │ Pure Python│   │ Guardrails     │  │
│  │ 3-layer     │   │ Determinism│   │ Language param │  │
│  │ validation  │   │            │   │                │  │
│  └─────────────┘   └────────────┘   └────────────────┘  │
│                                                         │
│  ┌─────────────┐   ┌────────────────────────────────┐   │
│  │ exporter    │   │         ranges_fallback         │   │
│  │             │   │                                │   │
│  │ reportlab   │   │ Fallback reference ranges for  │   │
│  │ Noto fonts  │   │ 30 common tests (gender-aware) │   │
│  │ Unicode PDF │   │ Used only when PDF has no range│   │
│  └─────────────┘   └────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                       │
                  Google Gemini API
              (gemini-2.5-flash · free tier)
```
 
### Key Architectural Decisions
 
**Why Gemini Vision instead of OCR + regex?**
Every Indian lab prints tables differently — different column orders, merged cells, invisible borders. A regex pattern that works on SRL breaks on Thyrocare, which breaks on Dr. Lal. Gemini Vision understands spatial relationships natively. One prompt handles every format variation without a single hardcoded column index.
 
**Why is the rules engine separate from the LLM?**
LLMs hallucinate arithmetic. If blood sugar is 105 and the normal max is 100, an LLM might flag it correctly, or it might decide 105 is fine. `105 > 100` should never be evaluated probabilistically in a medical context. The LLM extracts text and generates explanations. Python decides what is normal. This boundary is what makes the app safe enough to deploy.
 
**Why batch all explanations in one API call?**
A 20-test report processed one call per test = 20 RPM hits against a 10 RPM limit. One batch call = 1 RPM hit. The prompt passes all tests as a JSON array and returns all explanations in a single response — same quality, 20× fewer API requests, stays well within free-tier quota.
 
**Why extract reference ranges from the report itself?**
Lab machines are calibrated for local populations and print their own reference ranges on every report. These are more accurate than any hardcoded dictionary. `ranges_fallback.py` exists only for PDFs that omit the range column.
 
---
 
## 🛠️ Tech Stack
 
| Layer | Technology | Why |
|---|---|---|
| LLM | Gemini 2.5 Flash (google-genai) | Free tier · multimodal · multilingual · native JSON schema output |
| Backend | FastAPI + Python 3.11 | Async endpoints · automatic OpenAPI docs · Pydantic integration |
| Data validation | Pydantic + `response_schema` | Schema enforcement at model level — no manual JSON parsing |
| PDF → Image | pdf2image + poppler | PIL Images passed directly to Gemini Vision |
| PDF generation | reportlab + Noto fonts | Unicode support for Hindi/Punjabi in exported PDFs |
| Frontend | Vanilla HTML / CSS / JS | No build step · instant deploy · zero dependencies |
| Design system | Sage & Ink (custom) | Warm, earthy, non-generic — designed for health literacy contexts |
| Backend hosting | Hugging Face Spaces (Docker) | Free · persistent · full Dockerfile control |
| Frontend hosting | Vercel | Free · instant CDN · GitHub auto-deploy |
| CI/CD | GitHub Actions | Push to main → auto-deploy to HF Spaces |
 
---
 
## 📁 Project Structure
 
```
lab-report-explainer/
│
├── .github/
│   └── workflows/
│       └── deploy.yml          # CI/CD: push to HF Spaces on merge to main
│
├── backend/
│   ├── main.py                 # FastAPI app + all endpoints + CORS
│   ├── extractor.py            # PDF → PNG → Gemini Vision → Pydantic JSON
│   ├── rules.py                # Deterministic flag logic (zero LLM calls)
│   ├── explainer.py            # Batch explanation + chat with guardrails
│   ├── exporter.py             # reportlab PDF generation with Unicode fonts
│   ├── ranges_fallback.py      # Fallback reference ranges (30 common tests)
│   ├── units.py                # Unit alias normalisation (gm% → g/dL etc.)
│   └── requirements.txt
│
├── frontend/
│   ├── index.html              # Full page structure (semantic HTML5)
│   ├── style.css               # Sage & Ink design system
│   └── app.js                  # State management + API calls + DOM rendering
│
├── Dockerfile                  # python:3.11-slim + poppler + Noto fonts
├── .env.example                # API key template
└── .gitignore
```
 
---
 
## 🚀 Running Locally
 
### Prerequisites
- Python 3.11+
- poppler (`brew install poppler` / `sudo apt install poppler-utils`)
- Gemini API key — free at [aistudio.google.com](https://aistudio.google.com/app/apikey)
### Setup
 
```bash
# 1. Clone the repository
git clone https://github.com/gagan61/lab-report-explainer.git
cd lab-report-explainer
 
# 2. Create virtual environment
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
 
# 3. Install dependencies
pip install -r requirements.txt
 
# 4. Set up API key
cp ../.env.example .env
# Edit .env and add: GEMINI_API_KEY=your_key_here
 
# 5. Run the backend
uvicorn main:app --reload --port 8000
```
 
Open `frontend/index.html` in your browser. The status dot turns green when the backend responds.
 
**Verify setup:**
```
http://localhost:8000/health  →  {"status":"ok","api_key_set":true}
http://localhost:8000/docs    →  Interactive API documentation
```
 
---
 
## 🔌 API Reference
 
| Endpoint | Method | Description |
|---|---|---|
| `/analyze` | POST | Full pipeline: extract → flag → explain |
| `/explain` | POST | Re-explain with different language or view mode (no re-extraction) |
| `/compare` | POST | Diff two PDF reports — improved / worsened / stable |
| `/chat` | POST | Bounded RAG chat (8-turn, guardrailed) |
| `/export` | POST | Generate Unicode-safe PDF report card |
| `/health` | GET | Health check + config verification |
 
All endpoints accept `multipart/form-data`. Full interactive docs at `/docs`.
 
---
 
## ⚙️ CI/CD Pipeline
 
Every push to `main` that touches backend files auto-deploys to Hugging Face Spaces. Frontend auto-deploys to Vercel via GitHub integration.
 
```
git push origin main
    │
    ├── GitHub Actions triggers (changes to backend/** or Dockerfile)
    │       └── Pushes to HF Space git repo → Docker rebuild → Space restart
    │
    └── Vercel detects push → rebuilds frontend → CDN propagation
```
 
**One-time setup:**
1. Get an HF token with Write access at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Add as GitHub secret: Repo → Settings → Secrets → Actions → `HF_TOKEN`
3. Connect GitHub repo to Vercel project for automatic frontend deploys
> `GEMINI_API_KEY` lives in HF Space Settings → Variables. Never committed to the repository.
 
---
 
## 🧠 Key Learnings
 
**IDP pipeline design over model selection**
The hardest part of this project was not choosing a model — it was designing the pipeline to handle real-world variation. Indian lab PDFs from five different labs have five completely different table structures. The lesson: for unstructured document processing, your parsing strategy matters more than your model choice. Gemini Vision absorbs all that variation in one prompt; regex would have needed 50 different rules.
 
**Deterministic logic and LLMs solve different problems**
Early versions asked Gemini to decide whether values were normal. It hallucinated. The fix was architectural, not prompt-based: LLMs are good at extracting text from images and generating human-readable prose. They are unreliable at arithmetic. Routing `value > ref_max` to a Python comparison and leaving explanation generation to Gemini made both components more reliable.
 
**Batching API calls is a first-class design concern**
With a 10 RPM limit, processing a 20-test report one call per test would take over 2 minutes and exceed the per-minute quota. Batching all explanation calls into one prompt reduced this to a single API hit with identical output quality. Quota management shaped the API design from the start.
 
**3-layer validation for LLM outputs**
A single validation layer is not enough when the source is an LLM. Schema enforcement (via `response_schema`) catches structural errors. Pydantic field validators catch type errors like negative haemoglobin from a misread dash. A physiological plausibility dictionary catches values that pass the schema but are impossible for a living human — a haemoglobin of 1400 g/dL from misreading the platelet column. Each layer catches a different class of failure.
 
**Real-world data never matches your assumptions**
The comma bug: `"4,000 - 10,000"` parsed as range 4–10, flagging a normal WBC as "See Doctor" on every SRL report. The fix was one regex line, but the lesson is that data from the real world — especially OCR'd data from medical documents — always has edge cases that synthetic test data misses. Testing against actual lab reports from multiple providers is non-negotiable.
 
---
 
## 🔒 Safety & Ethics
 
- **No diagnosis**: Every output ends with "consult your doctor." The guardrail is hardcoded in Python, not just in the prompt — it cannot be bypassed by prompt injection.
- **No real patient data in demos**: Only synthetic reports are used for demonstration. Free-tier Gemini may use inputs to improve Google's models — real patient data should never be sent to a free-tier API.
- **LLM never makes medical decisions**: The rules engine is deterministic Python. `value > ref_max` is never evaluated by a language model.
---
 
## 🗺️ System Limitations & Future Architecture
 
**Unit conversion (planned)**
The current system normalises unit aliases (`gm%` → `g/dL`) but does not perform chemical unit conversion (`mmol/L` → `mg/dL`). This requires per-analyte molecular weight data. The next step is a canonical conversion layer using the `pint` library, enabling correct handling of SI-unit reports common in hospital systems integrated with international standards.
 
**Low-quality scan handling (planned)**
A dual-pass pipeline is planned: if the first extraction returns fewer than N tests or triggers plausibility bounds, a second pass runs at 300 DPI with a more conservative prompt. This cross-verification pattern is standard in enterprise IDP systems and would handle the faded/skewed scans that currently produce incomplete extractions.
 
**Longitudinal tracking (planned)**
The current system processes one report per session with no persistence. The next version stores extracted JSON in MongoDB Atlas, enabling time-series visualisation of biomarker trends and Prophet-based forecasting to predict whether values like HbA1c are approaching clinical thresholds before they are breached.
 
**FHIR-compliant reference ranges (planned)**
Connecting to a LOINC-compatible reference range API would replace the static fallback dictionary with dynamically fetched, population-stratified normals that account for age, sex, ethnicity, and clinical context — necessary for accurate interpretation across diverse patient demographics.
 
---
 
## 👨‍💻 Author
 
**Gagandeep Singh**
 
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=flat&logo=linkedin)](https://linkedin.com/in/yourprofile)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-181717?style=flat&logo=github)](https://github.com/gagan61)
 
---
 
## 📄 License
 
MIT License — see [LICENSE](LICENSE) for details.
 
---
 
<div align="center">
<sub>Built with Gemini 2.5 Flash · FastAPI · Hugging Face Spaces · Vercel</sub>
<br>
<sub>Not a substitute for medical advice. Always consult a qualified physician.</sub>
</div>
 