"""Language detection utilities for multi-language support."""

import re
from typing import Optional
from fastapi import Request


# ═══════════════════════════════════════════════════════════════
# TEXT-BASED LANGUAGE DETECTION
# ═══════════════════════════════════════════════════════════════
# Compiled once at module level for performance.
#
# Strategy: score-based detection.
# Each pattern match adds weight to a language bucket.
# The language with the highest score wins -- minimum threshold 2.
# If no language clears the threshold, returns None (undetermined).
#
# Why this matters:
# The Accept-Language header reflects the BROWSER language setting,
# not the language the user is actually typing in. A Swiss user with
# a German browser (de-CH) can write in Spanish; a US user (en-US)
# can write in Spanish too. Text-content detection is the only
# reliable signal for the actual query language.

# Spanish indicators -- ordered from strongest (unique to ES) to weakest (shared).
_ES_PATTERNS = [
    # Inverted punctuation -- exclusively Spanish
    re.compile(r"[\u00bf\u00a1]"),
    # Words with Spanish-only characters (tildes + n-tilde)
    re.compile(r"\b(qu\u00e9|c\u00f3mo|cu\u00e1l|cu\u00e1les|d\u00f3nde|cu\u00e1ndo|por qu\u00e9)\b", re.IGNORECASE),
    re.compile(r"\b(tambi\u00e9n|adem\u00e1s|est\u00e1|podr\u00eda|ser\u00eda)\b", re.IGNORECASE),
    re.compile(r"\b(p\u00e1gina|env\u00edo|tel\u00e9fono|n\u00famero|categor\u00eda)\b", re.IGNORECASE),
    # Very frequent Spanish function words unlikely in English
    re.compile(r"\b(es|son|est\u00e1n|tiene|tienen|hay|puedo|puedes|puede)\b", re.IGNORECASE),
    re.compile(r"\b(quiero|busco|necesito|tengo|hola|gracias|por\s+favor)\b", re.IGNORECASE),
    re.compile(r"\b(los|las|del|una|esto|ese|esa|ellos|ellas|nosotros)\b", re.IGNORECASE),
    re.compile(r"\b(que|como|cuando|donde|porque|para|desde|hasta|sobre)\b", re.IGNORECASE),
    # Common retail-domain Spanish words
    re.compile(r"\b(talla|tallas|precio|envio|devolucion|pago|tienda|ropa|vestido|camisa)\b", re.IGNORECASE),
]

# English indicators -- unique English words and patterns.
_EN_PATTERNS = [
    # Very high-frequency English function words absent in Spanish
    re.compile(r"\b(what|how|where|when|why|who|which|whose)\b", re.IGNORECASE),
    re.compile(r"\b(is|are|was|were|have|has|had|will|would|could|should|does|do|did)\b", re.IGNORECASE),
    re.compile(r"\b(the|this|that|these|those|with|from|for|about|into|through)\b", re.IGNORECASE),
    re.compile(r"\b(looking|searching|need|want|show|find|help|please|thanks|hello|hi)\b", re.IGNORECASE),
    # Common retail-domain English words
    re.compile(r"\b(size|price|shipping|return|payment|store|dress|shirt|jacket|order)\b", re.IGNORECASE),
    re.compile(r"\b(can\s+I|do\s+you|I\s+want|I\s+need)\b", re.IGNORECASE),
]

# Minimum number of pattern matches required to declare a language.
# A single accidental match (e.g. "para" in a product name) should not
# trigger language switching -- require at least 2 signals.
_MIN_SCORE_THRESHOLD = 2


def detect_language_from_text(
    text: str,
    supported_languages: set = {"es", "en"},
) -> Optional[str]:
    """
    Detect language from the actual text content of a query.

    This is the PRIMARY language signal -- it reflects what the user is
    actually typing, not what language their browser is configured in.

    Algorithm:
      1. Score the text against Spanish and English pattern sets.
      2. Each compiled regex that matches adds 1 point to that language.
      3. The language with score >= _MIN_SCORE_THRESHOLD and the highest
         score wins.
      4. In case of a tie, returns None (undetermined).
      5. If neither language reaches the threshold, returns None.

    Args:
        text: The user query string.
        supported_languages: Languages to check.

    Returns:
        'es', 'en', or None if the language cannot be determined.

    Examples:
        >>> detect_language_from_text("Cual es la politica de devoluciones?")
        'es'
        >>> detect_language_from_text("What sizes do you have?")
        'en'
        >>> detect_language_from_text("ok")
        None  # Too short to determine
        >>> detect_language_from_text("aceptan Mastercard")
        'es'  # 'aceptan' matches Spanish function word pattern
    """
    if not text or len(text.strip()) < 3:
        return None

    scores: dict = {"es": 0, "en": 0}

    if "es" in supported_languages:
        for pattern in _ES_PATTERNS:
            if pattern.search(text):
                scores["es"] += 1

    if "en" in supported_languages:
        for pattern in _EN_PATTERNS:
            if pattern.search(text):
                scores["en"] += 1

    # Find best candidate that clears the threshold
    best_lang = None
    best_score = _MIN_SCORE_THRESHOLD - 1  # must beat threshold to win

    for lang, score in scores.items():
        if score > best_score:
            best_score = score
            best_lang = lang
        elif score == best_score and best_lang is not None:
            # Tie -- cannot determine
            best_lang = None

    return best_lang


def detect_language_from_request(
    request: Request,
    supported_languages: set = {"es", "en"},
    default_language: str = "es",
    query_text: Optional[str] = None,
) -> str:
    """
    Detect user's preferred language with a three-tier priority system.

    Priority (highest to lowest):
      1. Text content of the query (detect_language_from_text) -- most reliable
         because it reflects what the user is actually writing.
      2. Accept-Language header -- reflects browser locale, not typing language;
         useful when the text is too short to determine.
      3. Default language ('es').

    Args:
        request: FastAPI Request object.
        supported_languages: Set of supported language codes.
        default_language: Fallback language when nothing else matches.
        query_text: The user's message text (optional). When provided,
                    text-based detection runs first as the primary signal.

    Returns:
        Language code (e.g., 'es', 'en').
    """
    # -- TIER 1: Text content (highest confidence) --
    if query_text:
        text_lang = detect_language_from_text(query_text, supported_languages)
        if text_lang is not None:
            return text_lang
        # Text inconclusive -- fall through to header

    # -- TIER 2: Accept-Language header --
    accept_language = request.headers.get("Accept-Language", "")

    if accept_language:
        # Parse format: "en-US,en;q=0.9,es;q=0.8,fr;q=0.7"
        languages_with_quality = []

        for lang_part in accept_language.split(","):
            parts = lang_part.split(";")
            lang_code = parts[0].split("-")[0].strip().lower()
            quality = 1.0
            if len(parts) > 1 and "q=" in parts[1]:
                try:
                    quality = float(parts[1].split("=")[1].strip())
                except (ValueError, IndexError):
                    quality = 1.0
            languages_with_quality.append((lang_code, quality))

        languages_with_quality.sort(key=lambda x: x[1], reverse=True)

        for lang_code, _ in languages_with_quality:
            if lang_code in supported_languages:
                return lang_code

    # -- TIER 3: Default --
    return default_language


def validate_language(
    language: str,
    supported_languages: set = {"es", "en"},
    default_language: str = "es",
) -> str:
    """
    Validate anim7 ffd normalize language code.

    Args:
        language: Language code to validate (e.g. 'en', 'EN', 'en-US').
        supported_languages: Set of accepted language codes.
        default_language: Fallback if the code is unsupported.

    Returns:
        Validated lowercase language code.
    """
    # Normalize: lowercase, strip whitespace, drop region suffix (en-US -> en)
    language_normalized = language.lower().strip().split("-")[0]

    if language_normalized in supported_languages:
        return language_normalized

    return default_language
