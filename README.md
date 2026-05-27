<div align="center">

# 🩺 Lab Report Explainer

**Plain-language blood test summaries for Indian patients — in English, Hindi & Punjabi**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Vercel-000000?style=for-the-badge&logo=vercel)](https://lab-report-explainer-phi.vercel.app/)
[![Backend](https://img.shields.io/badge/Backend-HuggingFace%20Spaces-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black)](https://gagan61-lab-report-explainer.hf.space)
[![CI/CD](https://img.shields.io/github/actions/workflow/status/Gagandeep61/lab-report-explainer/deploy.yml?style=for-the-badge&label=CI%2FCD&logo=githubactions&logoColor=white)](https://github.com/Gagandeep61/lab-report-explainer/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

</div>

---

## 30-Second Pitch

India runs **500 million+ diagnostic tests per year**.<sup>[1]</sup> Most reports return as a wall of numbers with no explanation. Fewer than 40% of patients have the health literacy to interpret them,<sup>[2]</sup> and with doctor consultations averaging 8–12 minutes, there is no time to explain every value.

This tool takes any blood test PDF from any major Indian lab — SRL, Thyrocare, Dr. Lal, Apollo, Metropolis — and runs it through a complete IDP pipeline: Gemini Vision extracts every test row, a **deterministic Python rules engine** flags each value, and a single batch LLM call generates plain-language explanations in the patient's preferred language. Result: a structured report card, a bounded chat interface, and a downloadable PDF summary — all in under 60 seconds, at zero API cost.

<sup>[1] NATHEALTH India Healthcare Report 2023 | [2] National Health Literacy Survey, India 2022</sup>

---

## ⚡ Quick Stats

| Metric | Value |
|---|---|
| **Labs supported** | SRL · Thyrocare · Dr. Lal PathLabs · Apollo · Metropolis · any structured PDF |
| **Languages** | English · Hindi (Devanagari) · Punjabi (Gurmukhi) |
| **API cost** | ₹0 — runs entirely on OpenRouter free-tier models |
| **LLM calls per report** | 2 — one Vision extraction, one batch explanation |
| **Average response time** | 25–40 seconds end-to-end |
| **Fallback reference ranges** | 30 common tests (gender-aware) |
| **Plausibility bounds** | 25 common tests (catches hallucinated values) |
| **Chat limit** | 8 turns per session, guardrails enforced server-side |
| **PDF export** | Unicode-safe — Hindi & Punjabi render correctly |

---

## 🔴 The Problem

| Problem | Scale |
|---|---|
| Patients receive reports they cannot read | 500M+ tests/year in India |
| Hindi/Punjabi speakers excluded by English-only tools | 560M Hindi speakers · 33M Punjabi speakers |
| Doctors have no time to explain every value | 8–12 min avg. consultation |
| Patients miss early warning signs due to literacy gap | Preventable complications · late diagnoses |

This tool bridges the gap between a lab number and a patient decision.

---

## ✅ Features

| Feature | Detail |
|---|---|
| **Universal PDF extraction** | Any Indian lab format — multi-page, comma-formatted numbers, descriptive zone labels |
| **3-layer validation** | Schema enforcement → negative value rejection → physiological plausibility bounds |
| **Deterministic flagging** | Normal / Caution / See Doctor — pure Python rules engine, zero LLM arithmetic |
| **Visual gauge bars** | Per-test fill bar showing value relative to reference range |
| **Patient view** | 2 plain sentences per test — no jargon, no diagnosis |
| **Doctor view** | 3 clinical bullet points — value + deviation + aetiology + next step |
| **Language toggle** | English / Hindi / Punjabi — re-calls `/explain`, no re-extraction |
| **Bounded RAG chat** | 8-turn cap, guardrails enforced server-side in Python (not just prompt) |
| **Two-report comparison** | Diff table: improved / worsened / stable per test |
| **Doctor questions** | Consolidated list of specific questions for flagged tests only |
| **PDF export** | Unicode-safe downloadable report card |
| **Demo presets** | 4 JSON presets (no API cost) + 4 downloadable sample PDFs for full pipeline testing |

---

## 🏗️ Architecture

```
PDF (any Indian lab format)
    ↓  extractor.py   →  pdf2image → Gemini Vision → Pydantic 3-layer validation
    ↓  rules.py       →  Deterministic flag: Normal / Caution / See Doctor  (zero LLM)
    ↓  explainer.py   →  Batch explanation — 1 call for all tests · English / Hindi / Punjabi
    ↓  Frontend       →  Report cards · gauge bars · RAG chat · comparison · PDF export
```

```
┌──────────────────────────────────────────────────────────┐
│                    Frontend (Vercel)                      │
│           HTML · CSS (Sage & Ink) · Vanilla JS           │
└─────────────────────┬────────────────────────────────────┘
                      │  HTTPS REST
┌─────────────────────▼────────────────────────────────────┐
│               Backend (HF Spaces · Docker)                │
│                    FastAPI + Python 3.11                  │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ extractor   │  │    rules     │  │    explainer    │  │
│  │ pdf2image   │  │              │  │                 │  │
│  │ Gemini VLM  │─▶│  Pure Python │─▶│  Gemini Flash   │  │
│  │ Pydantic    │  │  No LLM      │  │  Batch prompts  │  │
│  │ 3-layer val │  │  Determinism │  │  Guardrails     │  │
│  └─────────────┘  └──────────────┘  └─────────────────┘  │
│                                                          │
│  ┌─────────────┐  ┌──────────────────────────────────┐   │
│  │  exporter   │  │        ranges_fallback            │   │
│  │  reportlab  │  │  30 common tests · gender-aware  │   │
│  │  Noto fonts │  │  Used only when PDF omits range  │   │
│  └─────────────┘  └──────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
                      │
               OpenRouter API
       (Gemini Vision · Gemini 2.5 Flash · free tier)
```

### Key Architectural Decisions

**Why OpenRouter instead of direct Gemini API?**
OpenRouter provides a single SDK and unified error handling across models. Switching extraction models requires changing one string — same retry logic, same interface. It also enables seamless fallback to alternative vision models without touching the rest of the pipeline.

**Why is the rules engine separate from the LLM?**
LLMs hallucinate arithmetic. `105 > 100` should never be evaluated probabilistically in a medical context. The LLM extracts text and generates explanations. Python decides what is normal. This boundary is what makes the app safe enough to deploy.

**Why batch all explanations in one API call?**
A 20-test report processed one call per test = 20 RPM hits. One batch call = 1 RPM hit, identical output quality, stays within free-tier quota. Free-tier constraints shaped the API design from the start — not retrofitted.

**Why extract reference ranges from the report itself?**
Lab machines are calibrated per instrument batch. Thyrocare's TSH range differs from SRL's. The rules engine reads the printed range from the PDF first. `ranges_fallback.py` is used only when the PDF omits a range column entirely.

**Why 3-layer validation on extracted data?**
A single validation layer is not enough when the source is an LLM. Schema enforcement catches structural errors. Pydantic field validators catch type errors (negative haemoglobin from a misread dash). A physiological plausibility dictionary catches values that pass the schema but are physiologically impossible — haemoglobin of 1400 g/dL from misreading the platelet column. Each layer catches a different class of failure.

---

## 🛠️ Tech Stack

| Layer | Choice | Why |
|---|---|---|
| **LLM — Extraction** | `google/gemini-2.0-flash-exp:free` via OpenRouter | Free tier · vision support · 200 RPD |
| **LLM — Explanation/Chat** | `google/gemini-2.5-flash:free` via OpenRouter | Free tier · best quality · 50 RPD |
| **LLM SDK** | `openai` (OpenRouter-compatible) | Single SDK for both models · standard interface |
| **Backend** | FastAPI + Python 3.11 | Async endpoints · auto docs · Pydantic native |
| **PDF → Image** | pdf2image + poppler | PIL images fed directly to Gemini Vision |
| **Validation** | Pydantic + manual JSON parsing | Handles markdown-wrapped responses from OpenRouter |
| **PDF Export** | reportlab + Noto fonts | Unicode support for Devanagari + Gurmukhi |
| **Frontend** | Vanilla HTML / CSS / JS | No build step · instant deploy · zero dependencies |
| **Design** | Sage & Ink system | Earthy greens · accessible contrast ratios · WCAG AA |
| **Backend host** | Hugging Face Spaces (Docker) | Free · persistent · full Dockerfile control |
| **Frontend host** | Vercel | Free CDN · GitHub auto-deploy |
| **CI/CD** | GitHub Actions | Push to `main` → auto-deploy to HF Spaces |

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
│   ├── main.py                 # FastAPI app — 6 endpoints, CORS, StaticFiles, lifespan
│   ├── extractor.py            # PDF → images → Gemini Vision → Pydantic validation
│   ├── rules.py                # Deterministic flagging engine — zero LLM calls
│   ├── explainer.py            # Batch explanations + RAG chat with guardrails
│   ├── exporter.py             # reportlab PDF export — Unicode-safe
│   ├── ranges_fallback.py      # 30 common tests, gender-aware fallback ranges
│   ├── units.py                # Medical unit alias normalisation (gm% → g/dL etc.)
│   ├── generate_samples.py     # Generates 4 demo PDFs at startup → static/
│   ├── requirements.txt
│   └── static/                 # Auto-generated on first startup
│       ├── sample_healthy.pdf
│       ├── sample_diabetic.pdf
│       ├── sample_lipids.pdf
│       └── sample_anemia.pdf
│
├── frontend/
│   ├── index.html              # Full page — upload, results, chat, compare, export
│   ├── style.css               # Sage & Ink design system — WCAG AA accessible
│   └── app.js                  # State, API calls, rendering, preset system
│
├── Dockerfile                  # python:3.11-slim + poppler + fonts-noto
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 🚀 Running Locally

### Prerequisites

- Python 3.11+
- poppler (`brew install poppler` / `sudo apt install poppler-utils`)
- Noto fonts (`sudo apt install fonts-noto fonts-noto-extra`)
- OpenRouter API key — free account at [openrouter.ai](https://openrouter.ai), no credit card required

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

# 4. Set API key
cp ../.env.example .env
# Edit .env: OPENROUTER_API_KEY=sk-or-v1-...

# 5. (Optional) Pre-generate sample PDFs
python generate_samples.py

# 6. Start backend
uvicorn main:app --reload --port 8000
```

**Verify setup:**
```
http://localhost:8000/health  →  {"status": "ok", "api_key_set": true}
http://localhost:8000/docs    →  Interactive API documentation
```

Open `frontend/index.html` via Live Server (VS Code) or any local static server. The status dot turns green when the backend responds.

> ⚠️ Do NOT open `index.html` directly via `file://` — CORS will block API calls. Use `localhost`.

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze` | Full pipeline: extract PDF → flag → explain |
| `POST` | `/explain` | Re-explain already-flagged tests (language/mode change, no re-extraction) |
| `POST` | `/compare` | Extract + flag two PDFs, return diff |
| `POST` | `/chat` | Bounded RAG chat against report context |
| `POST` | `/export` | Generate downloadable Unicode-safe PDF report card |
| `GET` | `/health` | Backend status + model config |

All endpoints accept `multipart/form-data`. Interactive docs at `/docs`.

**`/analyze` — Request**
```
file:     PDF upload
language: "english" | "hindi" | "punjabi"   (default: english)
mode:     "patient" | "doctor"              (default: patient)
```

**`/analyze` — Response shape**
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
  "total": 10,
  "flagged_count": 6
}
```

---

## 🎮 Demo Preset System

Ships with a hybrid demo system — zero API calls required for basic testing.

**JSON Presets (instant)**

| Profile | Patient | Key Findings |
|---|---|---|
| Healthy Adult | Priya, 25F | All 10 tests normal |
| Diabetic Pattern | Rajesh, 52M | HbA1c 8.1% · Glucose 162 · LDL 142 · TG 285 |
| Lipid Issues | Amit, 45M | LDL 188 · HDL 32 · TG 320 · VLDL 64 |
| Anaemia + Deficiencies | Sunita, 34F | Hb 8.9 · Ferritin 6 · B12 142 · Vit D 11 |

**Sample PDFs (full pipeline)**
Download a sample PDF → upload via normal file input → tests full extraction, flagging, and explanation pipeline end-to-end.

**Compare Presets (instant)**
- Diabetes: Before & After Treatment — all 5 tests improved
- Lipid Panel: Gradual Worsening — all 5 tests worsened

---

## ⚙️ CI/CD Pipeline

```
git push origin main
    │
    ├── GitHub Actions (backend/** or Dockerfile changes)
    │       └── Pushes to HF Space git repo → Docker rebuild → Space restart
    │
    └── Vercel detects push → rebuilds frontend → CDN propagation
```

**One-time setup:**
1. Get an HF token with Write access at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Add as GitHub secret: `Repo → Settings → Secrets → Actions → HF_TOKEN`
3. Connect GitHub repo to Vercel for automatic frontend deploys

> `OPENROUTER_API_KEY` lives exclusively in HF Space Secrets. Never committed to the repository.

---

## 🧠 Key Learnings

**1. LLMs and arithmetic are fundamentally incompatible.**
Even frontier models hallucinate numerical comparisons under pressure. Separating extraction (LLM) from evaluation (Python) is not a performance optimisation — it is the only correct architecture for medical data.

**2. Free-tier rate limits require upfront design, not retrofitting.**
Building with 50 RPD from day one forced the batch explanation architecture. The result is also cheaper and faster than per-test calls would be on paid tiers.

**3. Indian lab PDF formats are a parsing problem, not just a parsing task.**
Comma-formatted large numbers, descriptive zone labels inline with ranges, missing range columns, OCR em-dashes, and lakh notation all required explicit handling. Generic parsers fail silently on all of these.

**4. Real-world data never matches your assumptions.**
The comma bug: `"4,000 - 10,000"` parsed as range 4–10, flagging a normal WBC as "See Doctor" on every SRL report. The fix was one regex line, but the lesson is that testing against actual lab reports from multiple providers is non-negotiable.

**5. Accessibility is not a post-launch concern.**
WCAG contrast failures, missing focus rings, and non-functional keyboard navigation were found in the initial CSS. Fixed before launch. Screen reader compatibility and keyboard navigation are first-class requirements in health tools.

**6. OpenRouter adds a valuable abstraction layer.**
Switching extraction models required changing one string. Same SDK, same error handling, same retry logic.

---

## 🐛 Notable Bugs Fixed

| Bug | Impact | Fix |
|---|---|---|
| Comma-formatted numbers — `"4,000 - 10,000"` parsed as 4–10 | WBC 7200 flagged See Doctor | Strip digit-comma-digit before range parse |
| Descriptive range labels — unit stripper hit `N` in "Normal" | HbA1c 6.8% silently Normal | Strip label words first, then unit suffixes |
| PDF black squares for Hindi/Punjabi | Helvetica Latin-only → tofu on non-Latin chars | Dockerfile installs Noto fonts, registered at startup |
| No fallback ranges when PDF omits range column | Everything silently Normal | Created `ranges_fallback.py` |
| `rules.py` div-by-zero when `ref_min = 0` | `/analyze` crashed on bilirubin fractions | Guard: `if ref_min == 0: return "Normal"` |
| `explainer.py` chat stuffed into single user message | Safety guardrails partially ignored | Proper system / user / assistant message roles |
| `app.js` gauge_pct unclamped | Bar overflows container on extreme values | `Math.min(100, Math.max(0, gauge_pct))` |
| `app.js` aria-pressed never updated | Screen readers announce stale toggle state | Sync attribute on every toggle click |
| `style.css` disabled button contrast 2.8:1 | Fails WCAG AA (requires 4.5:1) | `#2E5010` on `#C0DD97` → 4.6:1 |

---

## 🔒 Safety & Ethics

- **No diagnosis.** The word "diagnosis" does not appear in any prompt or response. Every output ends with a physician consultation instruction.
- **Guardrail in Python, not prompt.** The medical disclaimer is appended in `explainer.py` regardless of model output — it cannot be removed by prompt injection.
- **LLM never makes medical decisions.** `value > ref_max` is Python. Never LLM.
- **8-turn chat cap enforced in JavaScript** before any API call is made.
- **No patient data stored.** PDFs processed in memory and discarded after response.
- **No real patient data in demos.** Only synthetic reports used. Free-tier models may use inputs for training — real patient data should never be sent to free-tier APIs.

---

## 🗺️ Future Scope

| Feature | Approach |
|---|---|
| **mmol/L ↔ mg/dL conversion** | `pint` library + molecular weight lookup per analyte |
| **Age-aware paediatric ranges** | Extend `ranges_fallback.py` with age-band tiers (0–12, 13–17, 18+) |
| **Low-quality scan handling** | Dual-pass pipeline: if extraction returns < N tests, retry at 300 DPI |
| **Longitudinal tracking** | MongoDB Atlas for time-series biomarker trends + Prophet forecasting |
| **FHIR-compliant ranges** | LOINC-compatible reference range API — population-stratified, age/sex/ethnicity aware |
| **WhatsApp delivery** | Twilio API → send PDF summary to patient's phone after analysis |

---

## 👨‍💻 Author

**Gagandeep Singh**

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=flat&logo=linkedin)](https://www.linkedin.com/in/gagandeep-singh-517155319)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-181717?style=flat&logo=github)](https://github.com/Gagandeep61)

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
<sub>Built with OpenRouter · Gemini Vision · FastAPI · Hugging Face Spaces · Vercel</sub>
<br>
<sub>⚠️ Not a substitute for medical advice. Always consult a qualified physician before making health decisions.</sub>
</div>