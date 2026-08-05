"""
Optional real-LLM AI layer. This is the "swap-in" referenced throughout the
SRS, final report, and ai_service.py docstrings: it implements the exact same
extraction and interaction-check behavior as the offline rule-based layer,
but backed by an actual hosted LLM (Groq's API, which is OpenAI-compatible).

This module is only used when GROQ_API_KEY is set (see config.py). It is
never imported/called on the default offline path, so the app's zero-API-key
guarantee is unaffected unless you deliberately opt in.

Every function here fails soft: if the API call errors, times out, or
returns malformed JSON, the caller (routers/prescriptions.py) catches the
exception and falls back to the rule-based ai_service functions, so a flaky
network or an expired key degrades gracefully instead of breaking the app.
"""
import json
from typing import List, Dict

import httpx

from ..config import settings


class LLMServiceError(Exception):
    """Raised on any failure talking to the LLM provider; callers should
    catch this and fall back to the rule-based ai_service layer."""


def is_configured() -> bool:
    return bool(settings.GROQ_API_KEY)


def _call_groq(system_prompt: str, user_content: str) -> dict:
    if not settings.GROQ_API_KEY:
        raise LLMServiceError("GROQ_API_KEY is not configured")

    try:
        response = httpx.post(
            settings.GROQ_API_URL,
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            json={
                "model": settings.GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=20.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMServiceError(f"Groq API request failed: {exc}") from exc

    try:
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise LLMServiceError(f"Groq API returned unexpected response shape: {exc}") from exc


def parse_prescription_text_llm(raw_text: str) -> List[Dict]:
    """
    LLM equivalent of ai_service.parse_prescription_text. Extracts medicine
    name, dosage, and frequency per line using a real language model instead
    of regex. Catalog matching still happens afterward in the router using
    the same substring-match logic as the rule-based path, so behavior stays
    consistent regardless of which extraction backend produced the names.
    """
    system_prompt = (
        "You extract structured data from prescription text. For each medicine "
        "line, identify the medicine name, dosage (e.g. '500mg'), and dosing "
        "frequency in plain English (e.g. 'Once daily', 'Twice daily', 'Three "
        "times daily', 'As needed'). Respond ONLY with JSON in this exact shape: "
        '{"items": [{"extracted_name": "...", "dosage": "...", "frequency": "..."}]}. '
        "Use null for dosage or frequency if not present in the text. Do not "
        "invent medicines that are not in the input."
    )
    data = _call_groq(system_prompt, raw_text)
    items = data.get("items", [])
    if not isinstance(items, list):
        raise LLMServiceError("Groq API 'items' field was not a list")
    return items


def check_drug_interactions_llm(medicine_names: List[str]) -> List[Dict]:
    """
    LLM equivalent of ai_service.check_drug_interactions. Asks the model for
    clinically known interactions strictly between pairs of medicines that
    are BOTH present in the given list, rather than checking against the
    small static KNOWN_INTERACTIONS table.
    """
    if len(medicine_names) < 2:
        # No pair possible — skip the call entirely rather than let the
        # model report general-knowledge interactions with drugs that
        # aren't actually part of this prescription.
        return []

    system_prompt = (
        "You are a pharmacology assistant. You will be given a specific list of "
        "medicine names that were prescribed TOGETHER. Identify only interactions "
        "that occur BETWEEN TWO OR MORE MEDICINES THAT ARE BOTH PRESENT IN THE GIVEN "
        "LIST. Do NOT report an interaction with any medicine that is not explicitly "
        "in the provided list, even if it is a well-known interaction in general — "
        "the list may contain only one medicine with no interactions to report, and "
        "that is a valid, expected outcome. Respond ONLY with JSON in this exact "
        'shape: {"interactions": [{"medicines": ["exact name from the list", "exact '
        'name from the list"], "severity": "low|medium|high", "message": "short '
        'explanation"}]}. If there are no interactions among the given medicines, '
        'respond with {"interactions": []}.'
    )
    user_content = "Medicines prescribed together: " + ", ".join(medicine_names)
    data = _call_groq(system_prompt, user_content)
    hits = data.get("interactions", [])
    if not isinstance(hits, list):
        raise LLMServiceError("Groq API 'interactions' field was not a list")

    # Defensive filter: even if the model ignores the instruction above, only
    # keep hits where every mentioned medicine is actually in the input list.
    normalized_input = {name.strip().lower() for name in medicine_names}
    safe_hits = []
    for hit in hits:
        mentioned = hit.get("medicines", [])
        if mentioned and all(
            any(m.strip().lower() in n or n in m.strip().lower() for n in normalized_input)
            for m in mentioned
        ):
            safe_hits.append(hit)
    return safe_hits
