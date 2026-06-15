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
    # Common retail-domain Spanish words (plurals added: vestidos?, camisas?, etc.)
    re.compile(r"\b(talla|tallas|precio|env[i\u00ed]o|devolucion|pago|tienda|ropa|vestidos?|camisas?|pantalones?|faldas?)\b", re.IGNORECASE),
    # Spanish imperative+pronoun verbs — exclusive to ES ('recomiendame', 'muestrame')
    re.compile(r"\b(recomien[dh]a?me|muestrame|d\u00e9jame|cu\u00e9ntame|ayudame|a\u00fcdame|busqueme)\b", re.IGNORECASE),
    # Spanish adjectives for clothing — exclusive to ES in this context
    re.compile(r"\b(cortos?|largos?|medios?|midi|elegantes?|casuales?|similares?)\b", re.IGNORECASE),
    # FIX (19/04/2026 — BUG-LANG-KB): Short Spanish queries were scoring 0 or 1 (<threshold 2)
    # causing fallback to Accept-Language header (often 'en' for Swiss/international users).
    # Examples that failed:
    #   'aceptan Paypal?' → ES=0, EN=0 → None → Accept-Language='en' → English KB response
    #   'Lo tiene en stock?' → ES=1 (tiene), EN=0 → None (below threshold 2) → English response
    # Fix: add action verbs (3P plural) typical of short Spanish e-commerce queries,
    # and the pronoun 'lo' which is unambiguous in Spanish but absent in English.
    re.compile(r"\b(aceptan?|acepta|tienen|toman|cobran|pagan|mandan|hacen|ofrecen|venden|env\u00edan)\b", re.IGNORECASE),
    re.compile(r"\b(lo|le)\b", re.IGNORECASE),   # 'lo tiene', 'le pregunto' — extremely rare in English
    re.compile(r"\b(stock|disponible|disponibles|agotado|agotada)\b", re.IGNORECASE),  # retail terms ES/EN shared but context resolves
]

# English indicators -- unique English words and patterns.
_EN_PATTERNS = [
    # Very high-frequency English function words absent in Spanish
    re.compile(r"\b(what|how|where|when|why|who|which|whose)\b", re.IGNORECASE),
    re.compile(r"\b(is|are|was|were|have|has|had|will|would|could|should|does|do|did|it|its)\b", re.IGNORECASE),
    re.compile(r"\b(the|this|that|these|those|with|from|for|about|into|through)\b", re.IGNORECASE),
    re.compile(r"\b(looking|searching|need|want|show|find|help|please|thanks|hello|hi)\b", re.IGNORECASE),
    # Common retail-domain English words
    re.compile(r"\b(size|price|shipping|return|payment|store|dress|shirt|jacket|order)\b", re.IGNORECASE),
    re.compile(r"\b(can\s+I|do\s+you|I\s+want|I\s+need)\b", re.IGNORECASE),
    # FIX (15/06/2026 — EN override for CH market): short EN retail queries like
    # "It's available?" and "Is it in stock?" had EN=0 because 'available' and
    # 'stock' were missing from EN patterns. Without these, the router fell back
    # to the body language ('fr'), making LFM respond in French for EN queries.
    re.compile(r"\b(available|availability|in\s+stock|out\s+of\s+stock)\b", re.IGNORECASE),
]

# French indicators — mercado CH (fr-CH).
# Objetivo: detectar FR incluso cuando el body POST dice 'es'/'en'
# porque validate_language ignoraba FR anteriormente.
# Patrones discriminantes: contracciones con apostrofe (d', l', j'),
# inversion interrogativa (est-il, est-elle), preposiciones exclusivas FR,
# y acentos tipicos del frances (ê, û, ô, œ) ausentes en espanol.
_FR_PATTERNS = [
    # Inversion interrogativa — construccion exclusivamente francesa
    re.compile(r"\best-(il|elle|ce|on)\b", re.IGNORECASE),
    # Contracciones frances + vocal — 'd\'autres', 'l\'article', 'qu\'il'
    re.compile(r"\b(d'|l'|j'|n'|qu'|s'|m'|t'|c')[aeiouéèêëàâùûôœhæ]", re.IGNORECASE),
    # Preposiciones/conjunciones exclusivas del frances (no compartidas con ES)
    re.compile(r"\b(dans|chez|après|avant|depuis|pendant|donc|alors|aussi)\b", re.IGNORECASE),
    # Acentos tipicos del frances ausentes en espanol (ê û ô œ æ)
    re.compile(r"[êûôœæÊÛÔŒÆ]"),
    # Pronombres sujeto franceses no presentes en espanol con este uso
    re.compile(r"\b(je|tu|nous|vous|ils|elles)\b", re.IGNORECASE),
    # Determinantes y palabras comunes exclusivas del frances
    re.compile(r"\b(autres?|notre|votre|leur|leurs|encore|toujours|jamais)\b", re.IGNORECASE),
    # Terminos retail comunes en FR
    re.compile(r"\b(livraison|retour|paiement|boutique|commande|produit|taille)\b", re.IGNORECASE),
]

# Minimum number of pattern matches required to declare a language.
# A single accidental match (e.g. "para" in a product name) should not
# trigger language switching -- require at least 2 signals.
_MIN_SCORE_THRESHOLD = 2


def detect_language_from_text(
    text: str,
    supported_languages: set = {"es", "en", "fr", "de", "it"},
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

    # Idiomas soportados actualmente: ES (mercados CL/MX/España), EN (internacional),
    # FR/DE/IT (mercado CH). DE e IT añadidos como extensión futura;
    # patrones activos solo para ES, EN y FR en esta versión.
    scores: dict = {"es": 0, "en": 0, "fr": 0}

    if "es" in supported_languages:
        for pattern in _ES_PATTERNS:
            if pattern.search(text):
                scores["es"] += 1

    if "en" in supported_languages:
        for pattern in _EN_PATTERNS:
            if pattern.search(text):
                scores["en"] += 1

    if "fr" in supported_languages:
        for pattern in _FR_PATTERNS:
            if pattern.search(text):
                scores["fr"] += 1

    # FIX (19/04/2026 — BUG-LANG-KB): Asymmetric threshold.
    # Old logic: require score >= 2 for BOTH languages (strict symmetric threshold).
    # Problem: short queries like 'aceptan Paypal?' score ES=1, EN=0 -> None -> falls
    # to Accept-Language header (often 'en' for Swiss users) -> wrong language.
    #
    # New logic:
    #   - If score_winner >= 2: high confidence, return winner (strict mode)
    #   - If score_winner >= 1 AND loser == 0: no competing signal, return winner (lax mode)
    #   - If score_winner == 1 AND loser >= 1: tied/ambiguous, return None
    #   - If both == 0: undetermined, return None
    # This correctly handles 'aceptan Paypal?' (ES=1, EN=0) -> 'es'
    # and 'Lo tiene en stock?' (ES=2, EN=0) -> 'es'.
    # Risk of false positives: low -- the 'lo/le' pattern and action verbs are
    # unambiguous in the e-commerce domain; a single EN-only signal still wins.
    best_lang = None
    best_score = 0

    for lang, score in scores.items():
        if score > best_score:
            best_score = score
            best_lang = lang
        elif score == best_score and best_lang is not None:
            best_lang = None  # tie -- cannot determine

    if best_lang is None or best_score == 0:
        return None

    # Check competing language score (highest among non-winners)
    other_score = max(v for k, v in scores.items() if k != best_lang)

    if best_score >= 2:
        # High confidence: winner clear (handles tied case above)
        return best_lang
    elif best_score == 1 and other_score == 0:
        # Low confidence but uncontested: accept
        return best_lang
    else:
        # best_score == 1 and other_score >= 1: ambiguous
        return None


def detect_language_from_request(
    request: Request,
    supported_languages: set = {"es", "en", "fr", "de", "it"},
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
    supported_languages: set = {"es", "en", "fr", "de", "it"},
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
