from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


def item_matches_allowed_languages(raw_payload: dict[str, object], title: str, body: str | None, allowed: Iterable[str]) -> bool:
    normalized_allowed = {value.strip().casefold() for value in allowed if value and value.strip()}
    if not normalized_allowed:
        return True

    explicit_language = extract_explicit_language(raw_payload)
    if explicit_language:
        return explicit_language in normalized_allowed

    detected_language = detect_language_heuristic(title=title, body=body)
    return detected_language in normalized_allowed


def extract_explicit_language(raw_payload: dict[str, object]) -> str | None:
    direct = _normalize_language(raw_payload.get("language"))
    if direct:
        return direct

    primary_location = raw_payload.get("primary_location")
    if isinstance(primary_location, dict):
        nested = _normalize_language(primary_location.get("language"))
        if nested:
            return nested

    biblio = raw_payload.get("biblio")
    if isinstance(biblio, dict):
        nested = _normalize_language(biblio.get("language"))
        if nested:
            return nested

    return None


def detect_language_heuristic(*, title: str, body: str | None) -> str:
    sample = " ".join(part for part in [title, body or ""] if part).strip()
    if not sample:
        return "unknown"

    script_language = _detect_script_language(sample)
    if script_language != "unknown":
        return script_language

    latin_text = "".join(char for char in sample if char.isascii())
    if not latin_text:
        return "unknown"

    english_markers = sum(
        1
        for token in _tokenize(latin_text)
        if token in _COMMON_ENGLISH_WORDS
    )
    if english_markers >= 2:
        return "en"
    return "unknown"


def _detect_script_language(value: str) -> str:
    saw_latin = False
    for char in value:
        if not char.isalpha():
            continue
        try:
            name = unicodedata.name(char)
        except ValueError:
            continue
        if "CYRILLIC" in name:
            return "ru"
        if "CJK" in name or "HIRAGANA" in name or "KATAKANA" in name or "HANGUL" in name:
            return "non_latin"
        if "ARABIC" in name or "HEBREW" in name or "GREEK" in name:
            return "non_latin"
        if "LATIN" in name:
            saw_latin = True
    return "unknown" if saw_latin else "unknown"


def _normalize_language(value: object) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip().casefold()
    if not cleaned:
        return None
    aliases = {
        "en": "en",
        "eng": "en",
        "english": "en",
        "ru": "ru",
        "rus": "ru",
        "russian": "ru",
    }
    return aliases.get(cleaned, cleaned)


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z]+", value.casefold())


_COMMON_ENGLISH_WORDS = {
    "a",
    "an",
    "and",
    "autonomous",
    "avoidance",
    "collision",
    "control",
    "data",
    "for",
    "in",
    "maritime",
    "model",
    "navigation",
    "of",
    "on",
    "path",
    "planning",
    "review",
    "ship",
    "study",
    "surface",
    "system",
    "the",
    "to",
    "vessel",
    "with",
}
