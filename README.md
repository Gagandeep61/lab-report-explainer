<div align="center">
# 🩺 Lab Report Explainer
 
### Plain-language blood test summaries for Indian patients
#### English · Hindi (हिंदी) · Punjabi (ਪੰਜਾਬੀ)
 
<br>
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Visit%20Site-000000?style=for-the-badge&logo=vercel)](https://lab-report-explainer-phi.vercel.app/)
[![Backend](https://img.shields.io/badge/Backend-HF%20Spaces-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black)](https://gagan61-lab-report-explainer.hf.space)
[![CI/CD](https://img.shields.io/github/actions/workflow/status/Gagandeep61/lab-report-explainer/deploy.yml?style=for-the-badge&label=CI%2FCD&logo=githubactions&logoColor=white)](https://github.com/Gagandeep61/lab-report-explainer/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)
 
<br>
> India runs **500M+ diagnostic tests per year.**
> Most reports return as a wall of numbers — no explanation, no context.
> This tool fixes that.
 
<br>
</div>
---
 
## What it does
 
Upload any blood test PDF from any major Indian lab. Get back:
 
- ✅ Every test flagged — **Normal / Caution / See Doctor** — by a deterministic Python rules engine (no LLM guessing)
- 📝 Plain-language explanation per test in **English, Hindi, or Punjabi**
- 💬 A bounded chat to ask follow-up questions about your results
- 📊 Side-by-side comparison of two reports over time
- 📄 Downloadable PDF summary
**No diagnosis. No medication advice. No data stored.**
 
---
 
## Quick Stats
 
| | |
|---|---|
| **Supported labs** | SRL · Thyrocare · Dr. Lal · Apollo · Metropolis · any structured PDF |
| **Languages** | English · Hindi · Punjabi |
| **API cost** | ₹0 — free-tier models only |
| **Extraction** | pymupdf first (instant) → Gemini Vision fallback for scanned PDFs |
| **LLM calls** | 2 per report minimum — vision adds 1 per scanned page |
| **Response time** | 10–40 seconds depending on PDF type |
| **Chat cap** | 8 turns per session, enforced server-side |
| **PDF export** | English only — Indic text replaced with a clear notice |
 
---
 
## How it works
 
```
PDF upload
    │
    ├─ pymupdf reads embedded text (0.1s, zero API calls)
    │       └─ text ≥ 200 chars? → Groq 8b structures JSON   ← 80% of reports
    │
    └─ text < 200 chars? → Gemini Vision reads page image     ← scanned PDFs only
    
    Both paths → Pydantic 3-layer validation
                 (schema → type coercion → plausibility bounds)
    
    → rules.py flags every test in pure Python (no LLM arithmetic)
    
    → Groq 70b generates plain-language explanations (1 batch call)
    
    → Sarvam AI translates to Hindi/Punjabi if selected
    
    → Frontend renders cards · gauge bars · chat · compare · export
```
 
<details>
<summary><b>📋 See the complete file-by-file flow</b></summary>
<br>
**1. `main.py` — request entry**
- Validates file type (`.pdf` only) and size (20 MB hard limit)
- Routes to `extract_tests_from_report(pdf_bytes)`
**2. `extractor.py` — two-pass extraction**
 
*Pass 1 — pymupdf (digital PDFs):*
- `fitz.open()` reads embedded text directly — no API call
- If text ≥ 200 chars → sends to `llama-3.1-8b-instant` (Groq) for JSON structuring
- Saves Gemini Vision quota for reports that actually need it (~5× capacity gain)
*Pass 2 — Gemini Vision (scanned PDFs only):*
- `pdf2image` converts each page to a PIL image at 150 DPI
- Image base64-encoded → sent to `gemini-2.0-flash-exp:free` via OpenRouter
- One API call per page
*Both paths run through 3-layer Pydantic validation:*
- Layer 1 — schema: required fields present, correct structure
- Layer 2 — type: values coerced to float, non-numeric strings rejected
- Layer 3 — plausibility: negative Hb → `None`, HbA1c = 450 → `None`
**3. `rules.py` — deterministic flagging (zero LLM)**
- `parse_reference_range()` strips comma-formatting, zone labels, unit suffixes
- Falls back to `ranges_fallback.py` (30 gender-aware ranges) if PDF omits the range column
- `units.py` normalises unit aliases (`gm%` → `g/dL`, `cells/cumm` → `cells/μL`)
- `determine_flag()`: pure Python comparison → Normal / Caution / See Doctor
- `compute_gauge_pct()`: value position in range, clamped 0–100
**4. `explainer.py` — batch explanation**
- All tests sent in one prompt to `llama-3.3-70b-versatile` (Groq, 14,400 RPD)
- Patient mode: 2 plain sentences + doctor questions for flagged tests
- Doctor mode: 3 clinical bullet points (value + aetiology + next step)
- Explanations always generated in English first
- Medical disclaimer appended in Python — cannot be removed by prompt injection
**5. `translator.py` — Hindi/Punjabi (optional)**
- Groq English output → Sarvam AI `mayura:v1` for translation
- One API call per text string (explanation + each doctor question)
- If `SARVAM_API_KEY` missing or Sarvam times out → silently returns English, no crash
**6. `exporter.py` — PDF export**
- `reportlab` generates downloadable summary
- Detects Devanagari/Gurmukhi Unicode ranges
- Replaces Indic text with English notice (reportlab has no OpenType shaping engine)
</details>
---
 
## Tech Stack
 
<details>
<summary><b>🛠 Models, libraries, and infrastructure</b></summary>
<br>
**Models**
 
| Role | Model | Provider | Quota |
|---|---|---|---|
| Text extraction (digital PDFs) | `llama-3.1-8b-instant` | Groq | 14,400 RPD |
| Vision extraction (scanned PDFs) | `gemini-2.0-flash-exp:free` | OpenRouter | 50 RPD |
| Explanation + Chat | `llama-3.3-70b-versatile` | Groq | 14,400 RPD |
| Translation | `mayura:v1` | Sarvam AI | Free tier |
 
**Libraries & Infrastructure**
 
| Layer | Choice |
|---|---|
| Backend | FastAPI + Python 3.11 |
| PDF text extraction | pymupdf (fitz) |
| PDF → image | pdf2image + poppler |
| Validation | Pydantic v2 |
| PDF export | reportlab |
| Frontend | Vanilla HTML / CSS / JS |
| Design system | Sage & Ink (WCAG AA) |
| Backend host | Hugging Face Spaces (Docker) |
| Frontend host | Vercel |
| CI/CD | GitHub Actions |
 
</details>
---
 
## Setup
 
<details>
<summary><b>🚀 Local development — prerequisites, API keys, commands</b></summary>
<br>
**Prerequisites**
 
- Python 3.11+
- `sudo apt install poppler-utils fonts-noto fonts-noto-extra` (Linux) or `brew install poppler` (Mac)
**API Keys**
 
| Key | Get it at | Required? |
|---|---|---|
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) — free, no card | Yes |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) — free | Yes |
| `SARVAM_API_KEY` | [app.sarvam.ai](https://app.sarvam.ai) — free | No — falls back to English |
 
**Run locally**
 
```bash
git clone https://github.com/Gagandeep61/lab-report-explainer.git
cd lab-report-explainer/backend
 
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
 
# Create .env with your keys
cp ../.env.example .env
# Add: OPENROUTER_API_KEY, GROQ_API_KEY, SARVAM_API_KEY
 
uvicorn main:app --reload --port 8000
```
 
Open `frontend/index.html` with VS Code Live Server — not `file://` (CORS blocks API calls).
 
Check setup: `GET http://localhost:8000/health`
 
</details>
---
 
## API Reference
 
<details>
<summary><b>🔌 Endpoints, request shapes, response format</b></summary>
<br>
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze` | Full pipeline — extract → flag → explain |
| `POST` | `/explain` | Re-explain with new language/mode (no re-extraction) |
| `POST` | `/compare` | Diff two PDFs — improved / worsened / stable per test |
| `POST` | `/chat` | RAG chat against report context (8-turn cap) |
| `POST` | `/export` | Download English PDF report card |
| `GET` | `/health` | Backend status + key presence + active models |
 
All endpoints accept `multipart/form-data`. Interactive docs at `/docs`.
 
**`/analyze` request**
```
file      PDF upload (required)
language  "english" | "hindi" | "punjabi"   default: english
mode      "patient" | "doctor"              default: patient
```
 
**`/analyze` response**
```json
{
  "tests": [
    {
      "test_name": "HbA1c",
      "value": 8.1,
      "unit": "%",
      "reference_range": "4.0 - 5.6",
      "ref_min": 4.0,
      "ref_max": 5.6,
      "flag": "See Doctor",
      "gauge_pct": 100,
      "explanation": "...",
      "doctor_questions": ["...", "..."]
    }
  ],
  "patient": { "age": 52, "gender": "male" },
  "total": 15,
  "flagged_count": 6
}
```
 
</details>
---
 
## Demo Presets
 
<details>
<summary><b>🎮 Test the app without uploading a real report</b></summary>
<br>
**JSON Presets — instant, zero API cost**
 
| Profile | Key findings |
|---|---|
| Healthy Adult (Priya, 25F) | All 10 tests normal |
| Diabetic Pattern (Rajesh, 52M) | HbA1c 8.1% · Glucose 162 · LDL 142 · TG 285 |
| Lipid Issues (Amit, 45M) | LDL 188 · HDL 32 · TG 320 · VLDL 64 |
| Anaemia + Deficiencies (Sunita, 34F) | Hb 8.9 · Ferritin 6 · B12 142 · Vit D 11 |
 
**Sample PDFs** — download from the demo bar → upload normally → tests the full pipeline end-to-end.
 
**Compare Presets**
- Diabetes: Before & After Treatment — all 5 tests improved
- Lipid Panel: Gradual Worsening — all 5 tests worsened
</details>
---
 
## Key Design Decisions
 
<details>
<summary><b>🧠 Why things are built the way they are</b></summary>
<br>
**LLM never does arithmetic**
`value > ref_max` is always Python. LLMs hallucinate numerical comparisons under pressure. In a medical context, that's not acceptable.
 
**Two-pass extraction, not always Vision**
Gemini Vision free tier is 50 RPD. 80% of Indian lab PDFs are digital — pymupdf reads them in 0.1 seconds with zero API calls. Vision is reserved for the 20% that are actually scanned. Result: ~5× more capacity on the same quota.
 
**Groq for explanation, not OpenRouter**
OpenRouter free tier is 50 RPD. Groq gives 14,400 RPD on `llama-3.3-70b-versatile` — 288× more headroom, same OpenAI-compatible SDK, 2-line change. Explanation and extraction quotas are on separate providers and can't starve each other.
 
**Sarvam for translation, not asking Groq to respond in Hindi**
A general 70B model is excellent at medical reasoning in English. Its Hindi/Punjabi medical vocabulary is inconsistent. Sarvam AI is trained specifically on Indian language pairs for medical text. Better output, separate concern.
 
**Batch all explanations in one call**
20 tests × 1 call each = 20 API hits. All 20 in one batch = 1 API hit, same quality. The constraint shaped a better design.
 
</details>
---
 
## Notable Bugs Fixed
 
<details>
<summary><b>🐛 Real failures caught in production testing</b></summary>
<br>
| Bug | Impact | Fix |
|---|---|---|
| `"4,000 - 10,000"` parsed as range 4–10 | WBC 7200 flagged See Doctor on every SRL report | Strip digit-comma-digit before range parse |
| Unit stripper hit `N` in "Normal" | HbA1c 6.8% silently Normal | Strip label words before unit suffixes |
| LLM wraps JSON in markdown fences | Pydantic crashes on ` ```json ` | Regex strip on every raw LLM response |
| Generic `"glucose"` key in fallback | Post-prandial 120 flagged Caution | Split into fasting / PP / random with correct ranges |
| `ref_min = 0` caused div-by-zero | `/analyze` crashed on bilirubin fractions | Guard: `if ref_min == 0: return "Normal"` |
| Chat in single user message | Guardrails partially ignored | Proper system / user / assistant message roles |
| Validator raised on negative values | One bad row crashed entire page | Return `None` instead of raising |
| `exporter.py` age/gender undefined | Every PDF export returned 500 | Unpack patient dict at top of function |
| `gauge_pct` unclamped | Bar overflowed on extreme values | `Math.min(100, Math.max(0, gauge_pct))` |
| `aria-pressed` never updated | Screen readers announced stale state | Sync attribute on every toggle click |
| `outline: none` on focus | Zero keyboard focus visibility | 2px solid accent ring |
| Button contrast 2.8:1 | Failed WCAG AA | Adjusted to 4.6:1 |
| CORS trailing slash | All browser requests blocked | Removed — exact string match required |
 
</details>
---
 
## Safety & Ethics
 
- No diagnosis — the word never appears in any prompt or response
- Medical disclaimer appended in Python, not prompt — injection-proof
- `value > ref_max` is always Python, never LLM
- 8-turn chat cap enforced server-side before any API call
- No patient data stored — PDFs processed in memory, discarded after response
- Free-tier models may use inputs for training — do not upload real patient data
---
 
## Roadmap
 
| What | How |
|---|---|
| Batch Sarvam calls | Currently 45 sequential calls for a 15-test Hindi report — needs batching |
| Long report chunking | pymupdf text capped at 6,000 chars — tests beyond that silently dropped |
| mmol/L ↔ mg/dL conversion | `pint` library + molecular weight per analyte |
| Paediatric ranges | Age-band tiers in `ranges_fallback.py` (0–12, 13–17, 18+) |
| WhatsApp delivery | Twilio → PDF summary to patient's phone |
 
---
 
## Project Structure
 
```
lab-report-explainer/
├── backend/
│   ├── main.py              # FastAPI — 6 endpoints, CORS, lifespan
│   ├── extractor.py         # Two-pass: pymupdf → Groq / pdf2image → Gemini Vision
│   ├── rules.py             # Deterministic flagging — zero LLM
│   ├── explainer.py         # Batch explanations + chat (Groq)
│   ├── translator.py        # Hindi/Punjabi via Sarvam AI
│   ├── exporter.py          # PDF export — English only
│   ├── ranges_fallback.py   # 30 gender-aware fallback ranges
│   ├── units.py             # Unit alias normalisation
│   └── generate_samples.py  # 4 demo PDFs generated at startup
├── frontend/
│   ├── index.html
│   ├── style.css            # Sage & Ink — WCAG AA
│   └── app.js
├── Dockerfile               # python:3.11-slim + poppler + fonts-noto
├── .env.example             # OPENROUTER_API_KEY + GROQ_API_KEY + SARVAM_API_KEY
└── .github/workflows/
    └── deploy.yml           # Push to main → HF Spaces Docker rebuild
```
 
---
 
<div align="center">
Built with Groq · OpenRouter · Sarvam AI · FastAPI · Hugging Face Spaces · Vercel
 
**[Live Demo](https://lab-report-explainer-phi.vercel.app/) · [API Docs](https://gagan61-lab-report-explainer.hf.space/docs) · [Backend Health](https://gagan61-lab-report-explainer.hf.space/health)**
 
<sub>⚠️ Not a substitute for medical advice. Always consult a qualified physician before making health decisions.</sub>
 
</div>
 