# explainer.py — LLM-powered explanation and chat
# This module handles ALL plain-language generation via Gemini.
# It never makes any flag/comparison decisions — those stay in rules.py.
#
# Key design: batch ALL test explanations in ONE Gemini call.
# Why: a 20-test report processed one call per test = 20 RPM hits.
# One batch call = 1 RPM hit. With 15 RPM limit this matters.
 
import json
import os
import re
import time
 
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
 
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
 
EXPLANATION_MODEL = os.getenv("EXPLANATION_MODEL", "gemini-1.5-flash")
 
LANGUAGE_INSTRUCTIONS = {
    "english": "English",
    "hindi": "Hindi (Devanagari script)",
    "punjabi": "Punjabi (Gurmukhi script)",
}
 
# ── Prompts ──────────────────────────────────────────────────────────────────
 
PATIENT_PROMPT = """You are a health literacy assistant. The patient is {age} years old, {gender}.
 
These are their lab test results with flags already determined by our system:
{tests_json}
 
For EVERY test in this array, provide:
1. "explanation": Exactly 2 sentences in plain language.
   Sentence 1: What this specific test measures (brief, simple).
   Sentence 2: What this specific value means for this patient — reference their actual number.
   NEVER say "you have [disease]". NEVER recommend medication. NEVER diagnose.
   If flag is "Normal", the second sentence should reassure ("Your value is within the normal range...").
 
2. "doctor_questions": Array of 2 questions this patient should ask their doctor.
   Only include for "Caution" or "See Doctor" flags. For "Normal" tests: empty array [].
   Make questions specific to the actual value, not generic.
 
Respond ENTIRELY in {language}.
 
Return ONLY a valid JSON array with exactly {count} objects. Each object:
{{"test_name": "<exact name as given>", "explanation": "<2 sentences>", "doctor_questions": ["<q1>", "<q2>"]}}
 
No markdown. No code fences. No extra text. Just the JSON array."""
 
 
DOCTOR_PROMPT = """You are generating a concise clinical brief for a physician reviewing a {age}y {gender} patient's results.
 
Lab results (pre-flagged):
{tests_json}
 
For EVERY test in this array, provide:
1. "explanation": Exactly 3 clinical bullet points using the • character.
   • Bullet 1: Specific value + unit + reference range + percentage deviation if out of range.
   • Bullet 2: Clinical significance and most likely aetiology given patient demographics.
   • Bullet 3: Recommended next step or monitoring consideration.
   Use medical terminology appropriate for a physician.
 
2. "doctor_questions": [] (empty array — not applicable in clinical view)
 
Return ONLY a valid JSON array with exactly {count} objects. Each object:
{{"test_name": "<exact name as given>", "explanation": "<3 bullets>", "doctor_questions": []}}
 
No markdown. No code fences. No extra text. Just the JSON array."""
 
 
CHAT_SYSTEM = """You are a health literacy assistant helping a patient understand their blood test results.
Patient: {age} years old, {gender}.
 
Their lab report data:
{report_context}
 
STRICT RULES — follow without exception:
1. Only explain what test values mean and answer general health literacy questions.
2. NEVER diagnose any condition or disease by name.
3. NEVER recommend, name, or suggest any medication or supplement.
4. NEVER advise changing or stopping existing medications.
5. If asked for a diagnosis or treatment plan, respond EXACTLY with:
   "I can help explain what these values mean, but only your doctor can diagnose or prescribe treatment. Please consult your physician."
6. Every response MUST end with this exact line:
   "Always discuss your results with your doctor before making any decisions."
7. Keep responses concise — 3 to 5 sentences maximum.
8. Do not repeat information the patient didn't ask about.
 
Respond in {language}."""
 
 
# ── Core functions ────────────────────────────────────────────────────────────
 
def _call_gemini_safe(model, prompt: str) -> str:
    """Gemini call with 429 retry. One retry after 62s sleep."""
    try:
        response = model.generate_content(prompt)
        return response.text
    except ResourceExhausted:
        time.sleep(62)
        response = model.generate_content(prompt)
        return response.text
 
 
def _parse_explanation_json(raw: str, expected_count: int) -> list[dict]:
    """
    Parse Gemini's batch explanation response.
    Strips markdown fences, handles partial responses.
    """
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE).strip()
 
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        # Try extracting array from anywhere in response
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
 
    # Fallback: return empty explanations so app doesn't crash
    return [{"test_name": "", "explanation": "Explanation unavailable.", "doctor_questions": []}
            for _ in range(expected_count)]
 
 
def _build_tests_summary(tests: list[dict]) -> list[dict]:
    """
    Strip tests down to only what the explanation prompt needs.
    Reduces token count and keeps the prompt focused.
    """
    return [
        {
            "test_name": t.get("test_name", ""),
            "value": t.get("value"),
            "unit": t.get("unit", ""),
            "reference_range": t.get("reference_range") or f"{t.get('ref_min', '')}–{t.get('ref_max', '')}",
            "flag": t.get("flag", "Normal"),
        }
        for t in tests
    ]
 
 
def generate_explanations_batch(
    tests: list[dict],
    age: int,
    gender: str,
    language: str = "english",
    mode: str = "patient",
) -> list[dict]:
    """
    Generate plain-language OR clinical explanations for ALL tests in one Gemini call.
    
    Returns the input tests list enriched with 'explanation' and 'doctor_questions' fields.
    Matching is done by test_name (case-insensitive).
    """
    if not tests:
        return tests
 
    model = genai.GenerativeModel(EXPLANATION_MODEL)
    lang_str = LANGUAGE_INSTRUCTIONS.get(language, "English")
    summary = _build_tests_summary(tests)
 
    prompt_template = PATIENT_PROMPT if mode == "patient" else DOCTOR_PROMPT
    prompt = prompt_template.format(
        age=age,
        gender=gender,
        tests_json=json.dumps(summary, ensure_ascii=False),
        count=len(tests),
        language=lang_str,
    )
 
    raw = _call_gemini_safe(model, prompt)
    explanations = _parse_explanation_json(raw, len(tests))
 
    # Build lookup by test_name (lowercase) for safe merging
    exp_map = {e.get("test_name", "").strip().lower(): e for e in explanations}
 
    enriched = []
    for test in tests:
        key = test.get("test_name", "").strip().lower()
        exp = exp_map.get(key, {})
        enriched.append({
            **test,
            "explanation": exp.get("explanation", "Explanation not available."),
            "doctor_questions": exp.get("doctor_questions", []),
        })
 
    return enriched
 
 
def generate_chat_response(
    message: str,
    report_context: str,
    history: list[dict],
    age: int,
    gender: str,
    language: str = "english",
) -> str:
    """
    Generate a bounded RAG chat response.
    
    History is injected as a multi-turn conversation prefix.
    The system prompt enforces all medical safety guardrails.
    report_context is the JSON string of flagged tests (compact form).
    """
    model = genai.GenerativeModel(EXPLANATION_MODEL)
    lang_str = LANGUAGE_INSTRUCTIONS.get(language, "English")
 
    system = CHAT_SYSTEM.format(
        age=age,
        gender=gender,
        report_context=report_context,
        language=lang_str,
    )
 
    # Build conversation history as a formatted block
    history_text = ""
    for turn in history[-6:]:  # last 6 turns = 3 user/assistant pairs
        role = "Patient" if turn["role"] == "user" else "Assistant"
        history_text += f"\n{role}: {turn['content']}"
 
    full_prompt = f"{system}\n{history_text}\nPatient: {message}\nAssistant:"
 
    reply = _call_gemini_safe(model, full_prompt)
 
    # Enforce the closing disclaimer even if Gemini omits it
    disclaimer = "Always discuss your results with your doctor before making any decisions."
    if disclaimer.lower() not in reply.lower():
        reply = reply.rstrip() + f"\n\n{disclaimer}"
 
    return reply.strip()
 