# explainer.py — explanation + chat via Groq + Sarvam translation
#
# WHY GROQ: OpenRouter free tier = 50 RPD for explanation model.
# Groq free tier = 14,400 RPD for llama-3.3-70b-versatile.
# Same openai-compatible SDK — 2-line change, 288x more headroom.
#
# LANGUAGE FLOW:
#   Always generate explanations in English (Groq — best quality, high quota).
#   If user selected Hindi/Punjabi → translate via Sarvam AI (Indian language specialist).
#   Sarvam quality >> general LLM for Hindi/Punjabi medical text.
#   If SARVAM_API_KEY missing → silently serve English (no crash).

import json
import os
import re
import time
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from translator import translate_tests, translate_text

_client: Optional[OpenAI] = None
EXPLANATION_MODEL = "llama-3.3-70b-versatile"   # Groq — 14,400 RPD free

LANGUAGE_NAMES = {
    "english": "English",
    "hindi":   "Hindi (Devanagari script)",
    "punjabi": "Punjabi (Gurmukhi script)",
}


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set. Add to .env and HF secrets.")
        _client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
    return _client


def _call_groq_safe(messages: list[dict]) -> str:
    client = _get_client()
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=EXPLANATION_MODEL,
                messages=messages,
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception as e:
            err = str(e).lower()
            is_rate = "429" in str(e) or "rate" in err or "quota" in err
            if is_rate and attempt == 0:
                print("[explainer] Groq rate limit — sleeping 5s")
                time.sleep(5)
                continue
            raise
    raise RuntimeError("Groq call failed after retry.")


# ── Prompts ───────────────────────────────────────────────────────────────────
# Always in English — Sarvam handles translation separately.

PATIENT_PROMPT = """You are a health literacy assistant. The patient is {age} years old, {gender}.

These are their lab test results (flags already determined by the rules engine — do not change them):
{tests_json}

For EVERY test in this array, write:

1. "explanation": Exactly 2 sentences in plain English.
   Sentence 1: What this specific test measures (simple, no jargon).
   Sentence 2: What this specific value means for this patient — reference their actual number.
   If flag is "Normal": second sentence should be reassuring.
   NEVER say "you have [disease]". NEVER recommend medication. NEVER diagnose.

2. "doctor_questions": Array of 2 specific questions to ask their doctor.
   Only for "Caution" or "See Doctor" flags. Empty array [] for "Normal" tests.
   Make questions specific to the actual value, not generic.

Return ONLY a valid JSON array with exactly {count} objects.
Each object: {{"test_name": "<exact name as given>", "explanation": "<2 sentences>", "doctor_questions": ["<q1>", "<q2>"]}}
No markdown. No code fences. No extra text."""


DOCTOR_PROMPT = """Generate a concise clinical brief for a physician reviewing a {age}y {gender} patient's results.

Lab results (pre-flagged by rules engine):
{tests_json}

For EVERY test, write:

1. "explanation": Exactly 3 clinical bullet points using the • character.
   • Value: exact value + unit + reference range + percentage deviation if out of range.
   • Significance: clinical significance and most likely aetiology for this demographic.
   • Action: recommended monitoring or next step.

2. "doctor_questions": []

Return ONLY a valid JSON array with exactly {count} objects.
Each object: {{"test_name": "<exact name as given>", "explanation": "<3 bullets>", "doctor_questions": []}}
No markdown. No code fences. No extra text."""


CHAT_SYSTEM = """You are a health literacy assistant helping a patient understand their blood test results.
Patient: {age} years old, {gender}.

Their lab report data:
{report_context}

STRICT RULES — follow without exception:
1. Only explain what test values mean.
2. NEVER diagnose any condition or disease by name.
3. NEVER recommend, name, or suggest any medication or supplement.
4. NEVER advise changing or stopping existing medications.
5. If asked for diagnosis or treatment, respond EXACTLY:
   "I can help explain what these values mean, but only your doctor can diagnose or prescribe. Please consult your physician."
6. Every response MUST end with this exact line:
   "Always discuss your results with your doctor before making any decisions."
7. Keep responses to 3–5 sentences maximum.

Respond in English. (Translation handled separately if needed.)"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_explanation_json(raw: str, original_tests: list[dict]) -> list[dict]:
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```$',          '', cleaned,     flags=re.MULTILINE).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    print(f"[explainer] JSON parse failed. Raw (first 300): {raw[:300]}")
    # Use real test_name from original so exp_map lookup works per-test
    return [
        {"test_name": t.get("test_name", ""), "explanation": "Explanation temporarily unavailable.", "doctor_questions": []}
        for t in original_tests
    ]


def _tests_summary(tests: list[dict]) -> list[dict]:
    return [
        {
            "test_name":       t.get("test_name", ""),
            "value":           t.get("value"),
            "unit":            t.get("unit", ""),
            "reference_range": (
                t.get("reference_range")
                or f"{t.get('ref_min', '')}–{t.get('ref_max', '')}"
            ),
            "flag": t.get("flag", "Normal"),
        }
        for t in tests
    ]


# ── Public functions ──────────────────────────────────────────────────────────

def generate_explanations_batch(
    tests:    list[dict],
    age:      int,
    gender:   str,
    language: str = "english",
    mode:     str = "patient",
) -> list[dict]:
    """
    Generate explanations for all tests in English via Groq,
    then translate to Hindi/Punjabi via Sarvam if needed.
    """
    if not tests:
        return tests

    summary  = _tests_summary(tests)
    template = PATIENT_PROMPT if mode == "patient" else DOCTOR_PROMPT

    prompt = template.format(
        age=age,
        gender=gender,
        tests_json=json.dumps(summary, ensure_ascii=False),
        count=len(tests),
    )

    # Always generate in English (Groq handles it best)
    raw          = _call_groq_safe([{"role": "user", "content": prompt}])
    explanations = _parse_explanation_json(raw, tests)
    exp_map      = {e.get("test_name", "").strip().lower(): e for e in explanations}

    explained = [
        {
            **t,
            "explanation":      exp_map.get(t.get("test_name", "").strip().lower(), {})
                                    .get("explanation", "Explanation not available."),
            "doctor_questions": exp_map.get(t.get("test_name", "").strip().lower(), {})
                                    .get("doctor_questions", []),
        }
        for t in tests
    ]

    # Translate to Hindi/Punjabi via Sarvam if needed
    if language != "english":
        explained = translate_tests(explained, language)

    return explained


def generate_chat_response(
    message:        str,
    report_context: str,
    history:        list[dict],
    age:            int,
    gender:         str,
    language:       str = "english",
) -> str:
    """
    Generate chat response in English via Groq,
    then translate via Sarvam if user is in Hindi/Punjabi mode.
    """
    system = CHAT_SYSTEM.format(
        age=age,
        gender=gender,
        report_context=report_context,
    )

    messages = [{"role": "system", "content": system}]
    for turn in history[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    reply = _call_groq_safe(messages)

    # Ensure disclaimer present
    disclaimer = "Always discuss your results with your doctor before making any decisions."
    if disclaimer.lower() not in reply.lower():
        reply = reply.rstrip() + f"\n\n{disclaimer}"

    reply = reply.strip()

    # Translate if needed
    if language != "english":
        reply = translate_text(reply, language)

    return reply
