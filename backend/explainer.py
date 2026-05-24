# explainer.py — plain-language explanation and chat via Gemini
#
# SDK: google-genai (new). Old google-generativeai is deprecated.
# Model: gemini-2.5-flash (only confirmed working model on India free tier).
#
# No response_schema here — explanation and chat return free-form text.
# We still parse the batch explanation response as JSON (Gemini formats it
# correctly given our prompt instructions).
 
import json
import os
import re
import time
from typing import Optional
 
from dotenv import load_dotenv
load_dotenv()
 
from google import genai
 
# ── Client (lazy init, same pattern as extractor.py) ─────────────────────────
 
_client: Optional[genai.Client] = None
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
 
LANGUAGE_NAMES = {
    "english": "English",
    "hindi":   "Hindi (Devanagari script)",
    "punjabi": "Punjabi (Gurmukhi script)",
}
 
 
def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set. Check your .env file.")
        _client = genai.Client(api_key=api_key)
    return _client
 
 
# ── Rate-limit-safe Gemini call ──────────────────────────────────────────────
 
def _call_gemini_safe(prompt: str) -> str:
    """
    Text-only Gemini call with 429 retry.
    Free tier (gemini-2.5-flash): 10 RPM.
    One retry after 62s sleep on rate limit.
    """
    client = _get_client()
 
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            return response.text
 
        except Exception as e:
            err = str(e).lower()
            is_rate_limit = (
                "429" in str(e) or "quota" in err
                or "rate" in err or "exhausted" in err
            )
            if is_rate_limit and attempt == 0:
                print(f"[explainer] Rate limit hit. Sleeping 62s…")
                time.sleep(62)
                continue
            raise
 
    raise RuntimeError("Gemini call failed after rate-limit retry.")
 
 
# ── Prompts ───────────────────────────────────────────────────────────────────
 
PATIENT_PROMPT = """You are a health literacy assistant. The patient is {age} years old, {gender}.
 
These are their lab test results (flags already determined by the rules engine — do not change them):
{tests_json}
 
For EVERY test in this array, write:
 
1. "explanation": Exactly 2 sentences in plain {language}.
   Sentence 1: What this specific test measures (simple, no jargon).
   Sentence 2: What this specific value means for this patient — reference their actual number.
   If flag is "Normal": second sentence should be reassuring.
   NEVER say "you have [disease]". NEVER recommend medication. NEVER diagnose.
 
2. "doctor_questions": Array of 2 specific questions to ask their doctor.
   Only for "Caution" or "See Doctor" flags. Empty array [] for "Normal" tests.
   Make questions specific to the actual value, not generic ("What does my HbA1c of 6.8% mean for my diabetes risk?" not "What is HbA1c?").
 
Return ONLY a valid JSON array with exactly {count} objects.
Each object: {{"test_name": "<exact name as given>", "explanation": "<2 sentences>", "doctor_questions": ["<q1>", "<q2>"]}}
No markdown. No code fences. No extra text before or after the JSON."""
 
 
DOCTOR_PROMPT = """Generate a concise clinical brief for a physician reviewing a {age}y {gender} patient's results.
 
Lab results (pre-flagged by rules engine):
{tests_json}
 
For EVERY test, write:
 
1. "explanation": Exactly 3 clinical bullet points using the • character.
   • Value: exact value + unit + reference range + percentage deviation if out of range.
   • Significance: clinical significance and most likely aetiology for this demographic.
   • Action: recommended monitoring or next step.
   Use clinical terminology appropriate for a physician.
 
2. "doctor_questions": [] (empty — not applicable in clinical view)
 
Return ONLY a valid JSON array with exactly {count} objects.
Each object: {{"test_name": "<exact name as given>", "explanation": "<3 bullets>", "doctor_questions": []}}
No markdown. No code fences. No extra text."""
 
 
CHAT_SYSTEM = """You are a health literacy assistant helping a patient understand their blood test results.
Patient: {age} years old, {gender}.
 
Their lab report data:
{report_context}
 
STRICT RULES — follow without exception:
1. Only explain what test values mean. Answer general health literacy questions only.
2. NEVER diagnose any condition or disease by name.
3. NEVER recommend, name, or suggest any medication or supplement.
4. NEVER advise changing or stopping existing medications.
5. If asked for diagnosis or treatment, respond EXACTLY:
   "I can help explain what these values mean, but only your doctor can diagnose or prescribe. Please consult your physician."
6. Every response MUST end with this exact line:
   "Always discuss your results with your doctor before making any decisions."
7. Keep responses to 3–5 sentences maximum.
 
Respond in {language}."""
 
 
# ── Batch explanation parsing ─────────────────────────────────────────────────
 
def _parse_explanation_json(raw: str, expected_count: int) -> list[dict]:
    """
    Parse Gemini's batch explanation response.
    Strips any markdown fences Gemini adds despite instructions.
    Falls back to empty explanations so the app never crashes.
    """
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE).strip()
 
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        # Try extracting JSON array from anywhere in the response
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
 
    # Fallback — don't crash the app
    print(f"[explainer] Could not parse explanation JSON. Raw (first 300): {raw[:300]}")
    return [
        {"test_name": "", "explanation": "Explanation unavailable.", "doctor_questions": []}
        for _ in range(expected_count)
    ]
 
 
def _tests_summary(tests: list[dict]) -> list[dict]:
    """
    Strip tests to only what the explanation prompt needs.
    Reduces token count. Never send the full object to the explanation model.
    """
    return [
        {
            "test_name":       t.get("test_name", ""),
            "value":           t.get("value"),
            "unit":            t.get("unit", ""),
            "reference_range": (
                t.get("reference_range")
                or f"{t.get('ref_min', '')}–{t.get('ref_max', '')}"
            ),
            "flag":            t.get("flag", "Normal"),
        }
        for t in tests
    ]
 
 
# ── Public functions ──────────────────────────────────────────────────────────
 
def generate_explanations_batch(
    tests: list[dict],
    age: int,
    gender: str,
    language: str = "english",
    mode: str = "patient",
) -> list[dict]:
    """
    Generate explanations for ALL tests in ONE Gemini call.
 
    Why batch: a 20-test report processed one call per test = 20 RPM hits.
    With 10 RPM limit on gemini-2.5-flash free tier, that would take 2 minutes
    and hit the limit. One batch call = 1 RPM hit. Quality is identical.
 
    Returns input tests enriched with 'explanation' and 'doctor_questions' fields.
    """
    if not tests:
        return tests
 
    lang_str = LANGUAGE_NAMES.get(language, "English")
    summary  = _tests_summary(tests)
    template = PATIENT_PROMPT if mode == "patient" else DOCTOR_PROMPT
 
    prompt = template.format(
        age=age,
        gender=gender,
        tests_json=json.dumps(summary, ensure_ascii=False),
        count=len(tests),
        language=lang_str,
    )
 
    raw = _call_gemini_safe(prompt)
    explanations = _parse_explanation_json(raw, len(tests))
 
    # Match explanations back to tests by test_name (case-insensitive)
    exp_map = {e.get("test_name", "").strip().lower(): e for e in explanations}
 
    return [
        {
            **t,
            "explanation":      exp_map.get(t.get("test_name", "").strip().lower(), {})
                                    .get("explanation", "Explanation not available."),
            "doctor_questions": exp_map.get(t.get("test_name", "").strip().lower(), {})
                                    .get("doctor_questions", []),
        }
        for t in tests
    ]
 
 
def generate_chat_response(
    message: str,
    report_context: str,
    history: list[dict],
    age: int,
    gender: str,
    language: str = "english",
) -> str:
    """
    Bounded RAG chat. System prompt enforces all medical safety guardrails.
    History limited to last 6 turns (3 pairs) to stay within context budget.
    Disclaimer is hardcoded in Python — cannot be bypassed by prompt injection.
    """
    lang_str = LANGUAGE_NAMES.get(language, "English")
 
    system = CHAT_SYSTEM.format(
        age=age,
        gender=gender,
        report_context=report_context,
        language=lang_str,
    )
 
    # Last 6 turns = 3 user/assistant pairs
    history_text = ""
    for turn in history[-6:]:
        role = "Patient" if turn["role"] == "user" else "Assistant"
        history_text += f"\n{role}: {turn['content']}"
 
    full_prompt = f"{system}\n{history_text}\nPatient: {message}\nAssistant:"
 
    reply = _call_gemini_safe(full_prompt)
 
    # Hardcoded disclaimer — appended in Python, not prompt-dependent
    # This cannot be bypassed by a user who crafts their question to avoid it
    disclaimer = "Always discuss your results with your doctor before making any decisions."
    if disclaimer.lower() not in reply.lower():
        reply = reply.rstrip() + f"\n\n{disclaimer}"
 
    return reply.strip()
 