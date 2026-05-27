# explainer.py — explanation + chat via OpenRouter (gemini-2.5-flash:free)

import json
import os
import re
import time
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

_client: Optional[OpenAI] = None
EXPLANATION_MODEL = "google/gemini-2.5-flash:free"

LANGUAGE_NAMES = {
    "english": "English",
    "hindi":   "Hindi (Devanagari script)",
    "punjabi": "Punjabi (Gurmukhi script)",
}


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set. Check .env and HF secrets.")
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    return _client


def _call_openrouter_safe(prompt: str) -> str:
    client = _get_client()
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=EXPLANATION_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception as e:
            err = str(e).lower()
            is_rate_limit = "429" in str(e) or "quota" in err or "rate" in err or "exhausted" in err
            if is_rate_limit and attempt == 0:
                print("[explainer] Rate limit. Sleeping 62s…")
                time.sleep(62)
                continue
            raise
    raise RuntimeError("OpenRouter call failed after retry.")


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

Respond in {language}."""


def _parse_explanation_json(raw: str, expected_count: int, original_tests: list[dict]) -> list[dict]:
    """
    FIX: fallback array now copies test_name from original_tests instead of blank string.
    Previously all failed tests mapped to the same "" key in exp_map.
    """
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE).strip()

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

    print(f"[explainer] Could not parse JSON. Raw (first 300): {raw[:300]}")
    # FIX: use real test_name from original_tests so exp_map lookup succeeds per-test
    return [
        {
            "test_name":       t.get("test_name", ""),
            "explanation":     "Explanation temporarily unavailable.",
            "doctor_questions": [],
        }
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
            "flag":            t.get("flag", "Normal"),
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

    raw          = _call_openrouter_safe(prompt)
    # FIX: pass original tests so fallback can copy real test_name values
    explanations = _parse_explanation_json(raw, len(tests), tests)
    exp_map      = {e.get("test_name", "").strip().lower(): e for e in explanations}

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
    lang_str = LANGUAGE_NAMES.get(language, "English")

    system = CHAT_SYSTEM.format(
        age=age,
        gender=gender,
        report_context=report_context,
        language=lang_str,
    )

    # FIX: use proper role-separated messages instead of stuffing everything
    # into one user message — improves instruction-following and safety guardrails
    messages = [{"role": "system", "content": system}]
    for turn in history[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    client = _get_client()
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=EXPLANATION_MODEL,
                messages=messages,
            )
            reply = response.choices[0].message.content
            break
        except Exception as e:
            err = str(e).lower()
            is_rate_limit = "429" in str(e) or "quota" in err or "rate" in err or "exhausted" in err
            if is_rate_limit and attempt == 0:
                print("[explainer] Chat rate limit. Sleeping 62s…")
                time.sleep(62)
                continue
            raise
    else:
        raise RuntimeError("OpenRouter chat call failed after retry.")

    disclaimer = "Always discuss your results with your doctor before making any decisions."
    if disclaimer.lower() not in reply.lower():
        reply = reply.rstrip() + f"\n\n{disclaimer}"

    return reply.strip()
