<div align="center">
# 🩺 Lab Report Explainer
 
**Plain-language blood test summaries for Indian patients — in English, Hindi & Punjabi**
 
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Vercel-000000?style=for-the-badge&logo=vercel)](https://lab-report-explainer-phi.vercel.app/)
[![Backend](https://img.shields.io/badge/Backend-HuggingFace%20Spaces-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black)](https://gagan61-lab-report-explainer.hf.space)
[![CI/CD](https://img.shields.io/github/actions/workflow/status/Gagandeep61/lab-report-explainer/deploy.yml?style=for-the-badge&label=CI%2FCD&logo=githubactions&logoColor=white)](https://github.com/Gagandeep61/lab-report-explainer/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
 
</div>
---
 
## What this is
 
India runs **500 million+ diagnostic tests per year**. Most reports come back as a wall of numbers. Fewer than 40% of patients have the health literacy to interpret them, and with doctor consultations averaging 8–12 minutes, there is no time to explain every value.
 
This tool takes any blood test PDF from any major Indian lab — SRL, Thyrocare, Dr. Lal, Apollo, Metropolis — and returns a structured, plain-language explanation of every test in the patient's preferred language. No diagnosis. No medication advice. Just: what this number means, and what to ask your doctor.
 
---
 
## ⚡ Quick Stats
 
| Metric | Value |
|---|---|
| **Labs supported** | SRL · Thyrocare · Dr. Lal · Apollo · Metropolis · any structured PDF |
| **Languages** | English · Hindi (Devanagari) · Punjabi (Gurmukhi) |
| **API cost** | ₹0 — free-tier models only |
| **Extraction strategy** | Two-pass: pymupdf text first, Gemini Vision fallback for scanned PDFs |
| **LLM calls per report** | 2 minimum (1 extraction + 1 explanation) — vision adds 1 per page if scanned |
| **Average response time** | 10–40 seconds depending on PDF type |
| **Fallback reference ranges** | 30 common tests, gender-aware |
| **Plausibility bounds** | 25 common tests — catches hallucinated values before they reach the rules engine |
| **Chat limit** | 8 turns per session, enforced server-side |
| **PDF export** | English only — Indic scripts detected and replaced with a clear notice |
 
---
 
## 🔴 The Problem
 
| Problem | Scale |
|---|---|
| Patients receive reports they cannot read | 500M+ tests/year in India |
| Hindi/Punjabi speakers excluded by English-only tools | 560M Hindi speakers · 33M Punjabi speakers |
| Doctors have no time to explain every value | 8–12 min avg. consultation |
| Patients miss early warning signs | Preventable complications · late diagnoses |
 
---
 
## 🔁 Complete Project Flow
 
This is the full request lifecycle from PDF upload to patient-readable output.
 
```
┌─────────────────────────────────────────────────────────────────┐
│  USER uploads PDF via frontend (Vercel)                         │
│  POST /analyze  →  language=hindi  →  mode=patient              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  main.py — FastAPI receives request                             │
│  • validates file extension (.pdf only)                         │
│  • checks file size (20 MB hard limit)                          │
│  • calls extract_tests_from_report(pdf_bytes)                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  extractor.py — Two-pass extraction                             │
│                                                                 │
│  PASS 1 — pymupdf (zero API calls, ~0.1s)                       │
│  • fitz.open() reads embedded text from PDF                     │
│  • if text ≥ 200 chars → digital PDF confirmed                  │
│    → send text to Groq llama-3.1-8b-instant for JSON structure  │
│    → LabReport Pydantic model validates response                 │
│    → done (vision quota untouched)                              │
│                                                                 │
│  PASS 2 — Gemini Vision fallback (scanned PDFs only)            │
│  • triggers if pymupdf returns < 200 chars                      │
│  • pdf2image converts each page to PIL image at 150 DPI         │
│  • image → base64 PNG → sent to Gemini Vision via OpenRouter    │
│  • one API call per page                                        │
│  • LabReport Pydantic model validates each response             │
│                                                                 │
│  BOTH PATHS → 3-layer Pydantic validation:                      │
│  Layer 1 — schema: required fields present, correct shape       │
│  Layer 2 — type: value coerced to float, string rejected        │
│  Layer 3 — plausibility: negative Hb → None, HbA1c=450 → None  │
│                                                                 │
│  Output: {"tests": [...], "patient": {"age": 52, "gender": ...}}│
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  rules.py — Deterministic flagging (ZERO LLM)                   │
│  For each test:                                                 │
│  • parse_reference_range() — strips comma-formatting, labels,   │
│    unit suffixes, normalises dashes → (ref_min, ref_max)        │
│  • if no range in PDF → get_fallback_range() from              │
│    ranges_fallback.py (gender-aware, 30 common tests)           │
│  • units.py normalises unit strings (gm% → g/dL)               │
│  • determine_flag(): pure Python comparison                     │
│    value in range        → "Normal"                             │
│    deviation ≤ 20%       → "Caution"                            │
│    deviation > 20%       → "See Doctor"                         │
│  • compute_gauge_pct(): value position in range, clamped 0–100  │
│                                                                 │
│  Output: same test list + flag + gauge_pct + ref_min + ref_max  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  explainer.py — Batch explanation via Groq                      │
│  • ALL tests batched into ONE prompt (1 API call total)         │
│  • Model: llama-3.3-70b-versatile via Groq (14,400 RPD)        │
│  • Patient mode: 2 plain sentences per test + doctor questions  │
│    for flagged tests only                                       │
│  • Doctor mode: 3 clinical bullet points (value + aetiology +   │
│    next step)                                                   │
│  • Explanations always generated in English first              │
│  • Disclaimer appended in Python — cannot be removed by prompt  │
│    injection                                                    │
│                                                                 │
│  If language = hindi or punjabi:                                │
│  • translator.py calls Sarvam AI mayura:v1                      │
│  • one POST /translate call per text string (explanation +      │
│    each doctor question separately)                             │
│  • if SARVAM_API_KEY missing → silently returns English         │
│  • if Sarvam times out → returns English for that string        │
│                                                                 │
│  Output: same test list + explanation + doctor_questions        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  main.py — builds final JSON response                           │
│  {"tests": [...], "patient": {...},                             │
│   "total": 15, "flagged_count": 6}                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Vercel) renders:                                     │
│  • Summary bar (total / normal / caution / see doctor)          │
│  • Per-test cards with gauge bar + flag badge + explanation     │
│  • Doctor questions section (flagged tests only)                │
│  • RAG chat (8-turn cap, enforced in JS before API call)        │
│  • Compare section (diff table across two reports)              │
│  • PDF export via POST /export → exporter.py → reportlab        │
│    (English only — Indic detected and replaced with notice)     │
└─────────────────────────────────────────────────────────────────┘
```
 
---
 
## 🏗️ Architecture
 
### System diagram
 
```
┌──────────────────────────────────────────────────────────┐
│                    Frontend (Vercel)                      │
│           HTML · CSS (Sage & Ink) · Vanilla JS           │
└─────────────────────┬────────────────────────────────────┘
                      │  HTTPS REST  (multipart/form-data)
┌─────────────────────▼────────────────────────────────────┐
│               Backend (HF Spaces · Docker)                │
│                  FastAPI + Python 3.11                    │
│                                                          │
│  ┌──────────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ extractor.py │  │ rules.py │  │   explainer.py    │  │
│  │              │  │          │  │                   │  │
│  │ Pass 1:      │  │ Pure     │  │ Groq              │  │
│  │ pymupdf →    │→ │ Python   │→ │ llama-3.3-70b     │  │
│  │ Groq 8b      │  │ No LLM   │  │ Batch prompt      │  │
│  │              │  │          │  │ 1 call/report     │  │
│  │ Pass 2:      │  │          │  └────────┬──────────┘  │
│  │ pdf2image →  │  │          │           │             │
│  │ Gemini Vision│  │          │  ┌────────▼──────────┐  │
│  │              │  │          │  │  translator.py    │  │
│  │ Pydantic     │  │          │  │  Sarvam mayura:v1 │  │
│  │ 3-layer val  │  │          │  │  Hindi / Punjabi  │  │
│  └──────────────┘  └──────────┘  └───────────────────┘  │
│                                                          │
│  ┌──────────────┐  ┌────────────────────────────────┐   │
│  │ exporter.py  │  │      ranges_fallback.py         │   │
│  │ reportlab    │  │  30 tests · gender-aware        │   │
│  │ English only │  │  used only when PDF omits range │   │
│  └──────────────┘  └────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
            │                           │
     OpenRouter API               Groq API
  (Gemini Vision — scanned   (llama-3.1-8b extraction
   PDFs only · 50 RPD)        llama-3.3-70b explanation
                               14,400 RPD)
                                    │
                              Sarvam AI API
                           (mayura:v1 translation
                            Hindi/Punjabi · optional)
```
 
### Key architectural decisions
 
**Why two-pass extraction instead of always using Vision?**
Gemini Vision via OpenRouter free tier is 50 RPD. At one call per page, a 3-page report costs 3 of those 50 — that's 16 users/day maximum. ~80% of Indian lab PDFs from major labs are digital and have embedded text. pymupdf reads that text in 0.1 seconds with zero API calls. Groq handles structuring at 14,400 RPD. Vision is now reserved for the 20% that are actually scanned — effective capacity ~5x higher.
 
**Why is the rules engine separate from the LLM?**
LLMs hallucinate arithmetic. `8.1 > 5.6` evaluated probabilistically in a medical context is unacceptable. The LLM extracts text and generates explanations. Python decides what is normal. This boundary is what makes the tool safe to deploy.
 
**Why Groq for explanation instead of OpenRouter?**
OpenRouter free tier is 50 RPD shared across all models. Groq gives 14,400 RPD on `llama-3.3-70b-versatile` — 288x more headroom. Same OpenAI-compatible SDK, 2-line change. Explanation and extraction quotas are now on separate providers and cannot starve each other.
 
**Why Sarvam for translation instead of asking Groq to respond in Hindi?**
A general 70B model is excellent at medical reasoning in English. Its Hindi/Punjabi medical vocabulary is inconsistent — it mixes English terms, uses formal Sanskrit-root words patients don't recognize, and produces grammatically odd Punjabi. Sarvam AI is trained specifically on Indian language pairs for medical text. Separating explanation quality (Groq) from translation quality (Sarvam) lets each specialist do what it's trained for. Translation is also best-effort — missing key falls back to English silently, no crash.
 
**Why batch all explanations in one API call?**
20 tests × 1 call each = 20 RPM. All 20 in one batch = 1 RPM, same quality, well within free-tier limits. Free-tier constraints shaped the API design from the start.
 
**Why extract reference ranges from the report itself?**
Lab machines are calibrated per instrument batch. Thyrocare's TSH range differs from SRL's. The rules engine reads the printed range first. `ranges_fallback.py` is used only when the PDF omits a range column entirely.
 
---
 
## 🛠️ Tech Stack
 
| Layer | Choice | Why |
|---|---|---|
| **Extraction — text path** | `llama-3.1-8b-instant` via Groq | Fast · high quota · sufficient for JSON structuring |
| **Extraction — vision path** | `gemini-2.0-flash-exp:free` via OpenRouter | Free vision support · fallback only |
| **Explanation + Chat** | `llama-3.3-70b-versatile` via Groq | 14,400 RPD free · best quality for medical text |
| **Translation** | Sarvam AI `mayura:v1` | Indian-language specialist · better Hindi/Punjabi than general LLMs |
| **LLM SDK** | `openai` (OpenAI-compatible) | Single SDK for Groq + OpenRouter · same interface |
| **Text extraction** | `pymupdf` (fitz) | Zero API calls · instant · works on all digital PDFs |
| **PDF → Image** | `pdf2image` + `poppler` | PIL images for Gemini Vision (scanned PDFs only) |
| **Backend** | FastAPI + Python 3.11 | Async endpoints · auto docs · Pydantic native |
| **Validation** | Pydantic v2 | 3-layer: schema → type → plausibility bounds |
| **PDF Export** | `reportlab` (English only) | Indic scripts detected and replaced with notice |
| **Frontend** | Vanilla HTML / CSS / JS | No build step · zero dependencies · instant deploy |
| **Design** | Sage & Ink system | Earthy greens · WCAG AA accessible |
| **Backend host** | Hugging Face Spaces (Docker) | Free · full Dockerfile control |
| **Frontend host** | Vercel | Free CDN · GitHub auto-deploy |
| **CI/CD** | GitHub Actions | Push to `main` → auto-deploy to HF Spaces |
 
---
 
## ✅ Features
 
| Feature | Detail |
|---|---|
| **Two-pass extraction** | pymupdf for digital PDFs (fast, zero API cost) · Gemini Vision for scanned (fallback only) |
| **3-layer Pydantic validation** | Schema → type coercion → physiological plausibility bounds |
| **Deterministic flagging** | Normal / Caution / See Doctor — pure Python, zero LLM arithmetic |
| **Visual gauge bars** | Per-test fill bar showing value relative to reference range |
| **Patient view** | 2 plain sentences per test — no jargon, no diagnosis |
| **Doctor view** | 3 clinical bullet points — value + deviation + aetiology + next step |
| **Language toggle** | English / Hindi / Punjabi — re-calls `/explain`, no re-extraction |
| **Hindi/Punjabi via Sarvam** | Specialist translation model · graceful English fallback if key missing |
| **Bounded RAG chat** | 8-turn cap enforced server-side · proper system/user/assistant roles |
| **Two-report comparison** | Diff table: improved / worsened / stable per test |
| **Doctor questions** | Specific questions for flagged tests only — not generated for Normal values |
| **PDF export** | English only · Indic text detected and replaced with clear notice |
| **Demo presets** | 4 JSON presets (no API cost) + 4 sample PDFs for full pipeline testing |
 
---
 
## 🚀 Running Locally
 
### Prerequisites
 
- Python 3.11+
- poppler — `brew install poppler` / `sudo apt install poppler-utils`
- Noto fonts — `sudo apt install fonts-noto fonts-noto-extra`
- Three API keys (see table below)
### API Keys
 
| Key | Where to get | Required? |
|---|---|---|
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) — free, no credit card | Yes — for scanned PDF extraction |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) — free | Yes — for text extraction + explanation + chat |
| `SARVAM_API_KEY` | [app.sarvam.ai](https://app.sarvam.ai) — free | No — Hindi/Punjabi falls back to English without it |
 
### Setup
 
```bash
# 1. Clone
git clone https://github.com/Gagandeep61/lab-report-explainer.git
cd lab-report-explainer
 
# 2. Create virtual environment
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
 
# 3. Install dependencies
pip install -r requirements.txt
 
# 4. Set API keys
cp ../.env.example .env
# Edit .env and add all three keys:
# OPENROUTER_API_KEY=sk-or-v1-...
# GROQ_API_KEY=gsk_...
# SARVAM_API_KEY=...   (optional)
 
# 5. Start backend
uvicorn main:app --reload --port 8000
```
 
**Verify:**
```
GET http://localhost:8000/health
→ {"status": "ok", "openrouter_set": true, "groq_set": true, "sarvam_set": false, ...}
```
 
Open `frontend/index.html` via VS Code Live Server (not `file://` — CORS blocks API calls from file protocol).
 
---
 
## 📁 Project Structure
 
```
lab-report-explainer/
│
├── .github/
│   ├── workflows/
│   │   └── deploy.yml          # CI/CD: push backend/** → HF Spaces Docker rebuild
│   └── hf-config.txt           # HF Space metadata injected at deploy time
│
├── backend/
│   ├── main.py                 # FastAPI — 6 endpoints, CORS, lifespan, validators
│   ├── extractor.py            # Two-pass extraction: pymupdf → Groq / pdf2image → Gemini Vision
│   ├── rules.py                # Deterministic flagging engine — zero LLM
│   ├── explainer.py            # Batch explanations via Groq + chat with guardrails
│   ├── translator.py           # Hindi/Punjabi translation via Sarvam AI
│   ├── exporter.py             # reportlab PDF export — English only
│   ├── ranges_fallback.py      # 30 common tests, gender-aware fallback ranges
│   ├── units.py                # Medical unit alias normalisation (gm% → g/dL)
│   ├── generate_samples.py     # Generates 4 demo PDFs at startup → static/
│   ├── requirements.txt
│   └── static/                 # Auto-generated on first startup
│       ├── sample_healthy.pdf
│       ├── sample_diabetic.pdf
│       ├── sample_lipids.pdf
│       └── sample_anemia.pdf
│
├── frontend/
│   ├── index.html
│   ├── style.css               # Sage & Ink design system — WCAG AA
│   └── app.js
│
├── Dockerfile                  # python:3.11-slim + poppler + fonts-noto
├── requirements.txt
├── .env.example                # Template — OPENROUTER_API_KEY + GROQ_API_KEY + SARVAM_API_KEY
└── README.md
```
 
---
 
## 🔌 API Reference
 
<details>
<summary><strong>Endpoints overview + request/response shapes</strong></summary>
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze` | Full pipeline: extract → flag → explain |
| `POST` | `/explain` | Re-explain flagged tests (language/mode change, no re-extraction) |
| `POST` | `/compare` | Extract + flag two PDFs, return diff table |
| `POST` | `/chat` | Bounded RAG chat against report context |
| `POST` | `/export` | Generate downloadable English PDF report card |
| `GET` | `/health` | Backend status + model config + key presence |
| `GET` | `/` | API info + links to docs |
 
All endpoints accept `multipart/form-data`. Interactive docs at `/docs`.
 
**`/analyze` — Request**
```
file:     PDF upload (required)
language: "english" | "hindi" | "punjabi"   (default: english)
mode:     "patient" | "doctor"              (default: patient)
```
 
**`/analyze` — Response**
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
 
**`/health` — Response**
```json
{
  "status": "ok",
  "openrouter_set": true,
  "vision_model": "google/gemini-2.0-flash-exp:free (OpenRouter — scanned PDFs only)",
  "text_extract_model": "llama-3.1-8b-instant (Groq — digital PDFs)",
  "groq_set": true,
  "explanation_model": "llama-3.3-70b-versatile (Groq — 14,400 RPD)",
  "sarvam_set": false,
  "translation": "Sarvam AI mayura:v1 (Hindi/Punjabi)"
}
```
 
</details>
---
 
## 🎮 Demo Preset System
 
<details>
<summary><strong>JSON presets, sample PDFs, compare presets</strong></summary>
Ships with a hybrid demo system — zero API calls required for basic testing.
 
**JSON Presets (instant — no API cost)**
 
| Profile | Patient | Key Findings |
|---|---|---|
| Healthy Adult | Priya, 25F | All 10 tests normal |
| Diabetic Pattern | Rajesh, 52M | HbA1c 8.1% · Glucose 162 · LDL 142 · TG 285 |
| Lipid Issues | Amit, 45M | LDL 188 · HDL 32 · TG 320 · VLDL 64 |
| Anaemia + Deficiencies | Sunita, 34F | Hb 8.9 · Ferritin 6 · B12 142 · Vit D 11 |
 
**Sample PDFs (full pipeline test)**
Download a sample PDF from the demo bar → upload via the normal file input → tests full extraction, flagging, and explanation end-to-end.
 
**Compare Presets (instant)**
- Diabetes: Before & After Treatment — all 5 tests improved
- Lipid Panel: Gradual Worsening — all 5 tests worsened
</details>
---
 
## ⚙️ CI/CD
 
```
git push origin main
    │
    ├── backend/** or Dockerfile changed
    │       └── GitHub Actions → injects HF metadata into README
    │                          → force-pushes to HF Space git repo
    │                          → Docker rebuild → Space restart
    │
    └── any push to main
              └── Vercel → frontend auto-deploy → CDN propagation
```
 
**One-time setup:**
1. HF token with Write access — [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Add as GitHub secret: `Settings → Secrets → Actions → HF_TOKEN`
3. Add `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `SARVAM_API_KEY` to HF Space Secrets (never committed to repo)
4. Connect GitHub repo to Vercel for automatic frontend deploys
---
 
## 🧠 Key Learnings
 
<details>
<summary><strong>Six things built into this project that aren't obvious from the outside</strong></summary>
**1. LLMs and arithmetic are incompatible in medical contexts.**
Even frontier models hallucinate numerical comparisons under pressure. `value > ref_max` is Python. Never LLM. This isn't a performance choice — it's the only architecture that is safe to deploy.
 
**2. Free-tier quota is a first-class design constraint, not an afterthought.**
50 RPD forces you to batch. Batching 20 tests into one call instead of 20 individual calls is faster, cheaper, and scales better on paid tiers too. The constraint produced a better design.
 
**3. Provider diversity matters more than model quality at free tier.**
OpenRouter and Groq have separate quota pools. Extraction and explanation failing together because one provider is rate-limited is worse than using two providers with different limits. Groq's 14,400 RPD vs OpenRouter's 50 RPD for the same use case is a 288x difference — worth the extra SDK config.
 
**4. Separation of concerns for multilingual output.**
Generate in English → translate via a specialist. One model cannot be simultaneously best at medical reasoning and best at Hindi/Punjabi medical phrasing. Two specialists, each doing one thing well.
 
**5. Indian lab PDFs are a parsing problem that doesn't converge.**
Comma-formatted ranges, descriptive zone labels, missing range columns, em-dash vs hyphen, lakh notation — every new lab format adds new edge cases. Gemini Vision handling visual layout understanding is not a shortcut; it's the only architecture that doesn't require a new parser per lab.
 
**6. Accessibility cannot be deferred.**
WCAG contrast failures, missing focus rings, keyboard navigation gaps, and VoiceOver issues were all caught before launch. In a health literacy tool with older and low-vision users, these are correctness failures, not polish.
 
</details>
---
 
## 🐛 Notable Bugs Fixed
 
<details>
<summary><strong>Extraction, rules engine, frontend, accessibility bugs</strong></summary>
| Bug | Impact | Fix |
|---|---|---|
| Comma-formatted numbers — `"4,000 - 10,000"` parsed as 4–10 | WBC 7200 flagged See Doctor on every SRL report | Strip digit-comma-digit pattern before range parse |
| Descriptive range labels — unit stripper hit `N` in "Normal" | HbA1c 6.8% silently Normal | Strip label words first, then unit suffixes |
| Groq/OpenRouter wraps JSON in markdown fences | Pydantic crashes on `\`\`\`json` before parse | Regex strip on every raw LLM response |
| No fallback ranges when PDF omits range column | Everything silently Normal | Created `ranges_fallback.py` with 30 gender-aware entries |
| `rules.py` div-by-zero when `ref_min = 0` | Entire `/analyze` crashed on bilirubin fractions | Guard: `if ref_min == 0: return "Normal"` |
| `ranges_fallback.py` generic `"glucose"` key | Post-prandial glucose 120 incorrectly flagged Caution | Split into fasting / PP / random entries with correct ranges |
| `explainer.py` chat stuffed into single user message | Safety guardrails partially ignored by model | Proper system / user / assistant message roles |
| `extractor.py` validator raises on negative value | One bad value crashes entire page extraction | Validator returns `None` instead of raising |
| `exporter.py` NameError — age/gender undefined | Every PDF export crashed with 500 | Unpack patient dict at top of `generate_pdf()` |
| `app.js` gauge_pct unclamped | Bar overflows container on extreme values | `Math.min(100, Math.max(0, gauge_pct))` |
| `app.js` aria-pressed never updated | Screen readers announce stale toggle state | Sync attribute on every toggle click |
| `app.js` no keyboard handler on upload areas | Keyboard users could not trigger file upload | Enter/Space keydown fires `input.click()` |
| `app.js` chat turns burn on API error | User loses question without getting answer | Increment only inside success branch |
| `style.css` disabled button contrast 2.8:1 | Fails WCAG AA (requires 4.5:1) | `#2E5010` on `#C0DD97` → 4.6:1 |
| `style.css` `outline: none` on focus | Zero keyboard focus visibility | Replaced with 2px solid accent ring |
| CORS trailing slash in `allow_origins` | Browser requests blocked | Removed trailing slash — exact string match |
| Sarvam: 45 sequential API calls for 15-test Hindi report | ~9s added latency per Hindi report | Known gap — batching / async is the documented next step |
 
</details>
---
 
## 🔒 Safety & Ethics
 
- **No diagnosis.** The word "diagnosis" does not appear in any prompt or model response.
- **Medical disclaimer in Python, not prompt.** Appended in `explainer.py` regardless of model output — cannot be removed by prompt injection.
- **LLM never makes medical decisions.** `value > ref_max` is Python. Always.
- **8-turn chat cap enforced in JavaScript** before any API call is made.
- **No patient data stored.** PDFs processed in memory and discarded after response.
- **Free-tier models may use inputs for training.** Real patient data should not be uploaded to this tool.
---
 
## 🗺️ Future Scope
 
| Feature | Approach |
|---|---|
| **Batch Sarvam calls** | Send all strings in one request instead of one per string — reduces Hindi report latency from ~9s to ~1s |
| **Long report chunking** | Currently caps pymupdf text at 6,000 chars — tests beyond that are silently dropped. Fix: chunk per page, merge results |
| **mmol/L ↔ mg/dL conversion** | `pint` library + molecular weight lookup per analyte |
| **Age-aware paediatric ranges** | Extend `ranges_fallback.py` with age-band tiers (0–12, 13–17, 18+) |
| **Longitudinal tracking** | MongoDB Atlas for time-series biomarker trends |
| **WhatsApp delivery** | Twilio API → send PDF summary to patient's phone after analysis |
 
---
 
## 👨‍💻 Author
 
**Gagandeep Singh**
 
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=flat&logo=linkedin)](https://www.linkedin.com/in/gagandeep-singh-517155319)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-181717?style=flat&logo=github)](https://github.com/Gagandeep61)
 
---
 
## 📄 License
 
MIT — see [LICENSE](LICENSE) for details.
 
---
 
<div align="center">
<sub>Built with Groq · OpenRouter · Sarvam AI · FastAPI · Hugging Face Spaces · Vercel</sub>
<br>
<sub>⚠️ Not a substitute for medical advice. Always consult a qualified physician before making health decisions.</sub>
</div>
 