# translator.py — Hindi / Punjabi translation via Sarvam AI
#
# WHY SARVAM: General LLMs (even 70B) produce mediocre Punjabi and inconsistent
# Hindi for medical text. Sarvam AI is an Indian-language specialist model —
# trained specifically on Indian language pairs, significantly better quality
# for health literacy content.
#
# FLOW: Groq generates English explanation → Sarvam translates → user sees Hindi/Punjabi
# This separates explanation quality (Groq) from translation quality (Sarvam).
#
# FALLBACK: If SARVAM_API_KEY is missing or API call fails, English is returned
# silently. App never crashes — translation is best-effort.
#
# GET API KEY: https://app.sarvam.ai → Sign up → API Keys → Create key (free)

import os
import requests
from typing import Optional

SARVAM_API_URL = "https://api.sarvam.ai/translate"

SARVAM_LANG_CODES: dict[str, str] = {
    "hindi":   "hi-IN",
    "punjabi": "pa-IN",
}


def _translate_single(text: str, target_code: str, api_key: str) -> str:
    """
    Translate one text string via Sarvam AI.
    Returns original text on any failure — never raises.
    """
    if not text or not text.strip():
        return text

    try:
        resp = requests.post(
            SARVAM_API_URL,
            headers={
                "api-subscription-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "input":                text,
                "source_language_code": "en-IN",
                "target_language_code": target_code,
                "speaker_gender":       "Female",
                "mode":                 "formal",
                "model":                "mayura:v1",
                "enable_preprocessing": False,
            },
            timeout=12,
        )

        if resp.status_code == 200:
            translated = resp.json().get("translated_text", "").strip()
            return translated if translated else text

        print(f"[translator] Sarvam {resp.status_code}: {resp.text[:120]}")
        return text

    except requests.exceptions.Timeout:
        print("[translator] Sarvam timeout — returning English")
        return text
    except Exception as e:
        print(f"[translator] Sarvam error: {e}")
        return text


def translate_tests(tests: list[dict], language: str) -> list[dict]:
    """
    Translate explanation + doctor_questions fields of each test.

    Args:
        tests:    list of test dicts with English explanation/doctor_questions
        language: "english" | "hindi" | "punjabi"

    Returns:
        Same list with translated text fields.
        If language is English or SARVAM_API_KEY unset — returns original unchanged.
    """
    if language == "english":
        return tests

    target_code = SARVAM_LANG_CODES.get(language)
    if not target_code:
        print(f"[translator] Unknown language '{language}' — returning English")
        return tests

    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        print("[translator] SARVAM_API_KEY not set — serving English (add key to .env)")
        return tests

    translated_tests = []

    for t in tests:
        new_t = dict(t)

        # Translate explanation
        if t.get("explanation"):
            new_t["explanation"] = _translate_single(
                t["explanation"], target_code, api_key
            )

        # Translate each doctor question
        if t.get("doctor_questions"):
            new_t["doctor_questions"] = [
                _translate_single(q, target_code, api_key)
                for q in t["doctor_questions"]
                if q
            ]

        translated_tests.append(new_t)

    return translated_tests


def translate_text(text: str, language: str) -> str:
    """
    Translate a single string. Used for chat responses.
    Returns original on any failure.
    """
    if language == "english":
        return text

    target_code = SARVAM_LANG_CODES.get(language)
    if not target_code:
        return text

    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        return text

    return _translate_single(text, target_code, api_key)
