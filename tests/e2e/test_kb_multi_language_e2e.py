"""
E2E Test Suite - Knowledge Base Multi-Language
===============================================

Comprehensive test suite for validating KB multi-language functionality.

Tests cover:
- All 13 sub_intents (policy_*, product_*, account_*, general_faq, unknown)
- Both languages (ES, EN)
- Language detection methods (explicit, Accept-Language, default)
- Fallback scenarios
- Error handling

Author: Retail Recommender System Team
Date: 2026-01-23
"""

import pytest
import httpx
from typing import List, Dict, Any


# ══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════

API_BASE_URL = "http://localhost:8000/api/v1"

# All available sub_intents in the system
ALL_SUB_INTENTS = [
    "policy_return",
    "policy_shipping",
    "policy_warranty",
    "policy_payment",
    "policy_privacy",
    "product_care",
    "product_sizing",
    "product_material",
    "product_availability",
    "account_modifications",
    "account_orders",
    "general_faq",
    "unknown"
]

# Supported languages
SUPPORTED_LANGUAGES = ["es", "en"]


# ══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
async def http_client():
    """Create async HTTP client for tests."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=10.0) as client:
        yield client


def _detect_language_probabilistic(text: str) -> str:
    """
    Detect language using probabilistic approach.
    
    Returns: 'es', 'en', or 'unknown'
    """
    # Spanish indicators
    spanish_chars = ["á", "é", "í", "ó", "ú", "ñ", "¿", "¡"]
    spanish_words = [
        "política", "politica", "devolución", "devolucion",
        "envío", "envio", "días", "dias", "más", "mas",
        "cómo", "como", "qué", "que", "para", "por",
        "nuestro", "nuestra", "puede", "pueden"
    ]
    
    # English indicators
    english_words = [
        "the", "and", "or", "but", "with",
        "this", "that", "your", "our",
        "can", "will", "should", "would",
        "how", "what", "product", "return",
        "shipping", "policy", "care", "guide"
    ]
    
    text_lower = text.lower()
    
    # Count Spanish indicators
    spanish_score = 0
    spanish_score += sum(2 for char in spanish_chars if char in text)  # Chars worth 2 points
    spanish_score += sum(1 for word in spanish_words if f" {word} " in f" {text_lower} ")
    
    # Count English indicators
    english_score = 0
    english_score += sum(1 for word in english_words if f" {word} " in f" {text_lower} ")
    
    # Decide
    if spanish_score > english_score:
        return "es"
    elif english_score > spanish_score:
        return "en"
    else:
        return "unknown"
    
# ══════════════════════════════════════════════════════════════════════════
# TEST SUITE 1: BASIC FUNCTIONALITY (ALL SUB_INTENTS × ALL LANGUAGES)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("sub_intent", ALL_SUB_INTENTS)
@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
async def test_kb_answer_explicit_language_improved(
    http_client: httpx.AsyncClient,
    sub_intent: str,
    language: str
):
    """
    Test: KB answer with explicit language parameter (IMPROVED VERSION).
    
    Uses probabilistic language detection instead of exact phrase matching.
    """
    # Make request
    response = await http_client.get(
        "/kb/answer",
        params={
            "sub_intent": sub_intent,
            "language": language
        }
    )
    
    # Validate HTTP status
    assert response.status_code == 200, (
        f"Expected 200 OK, got {response.status_code} "
        f"for sub_intent={sub_intent}, language={language}"
    )
    
    # Parse JSON
    data = response.json()
    
    # Validate response structure
    assert "sub_intent" in data
    assert "language" in data
    assert "answer" in data
    
    # Validate content
    assert data["sub_intent"] == sub_intent
    assert data["language"] == language
    assert len(data["answer"]) > 0
    
    # ✅ IMPROVED: Use probabilistic detection
    detected_lang = _detect_language_probabilistic(data["answer"])
    
    # Allow 'unknown' for very short content or mixed content
    assert detected_lang in [language, "unknown"], (
        f"Expected language={language}, but content appears to be {detected_lang}. "
        f"Content preview: {data['answer'][:200]}"
    )


# ══════════════════════════════════════════════════════════════════════════
# TEST SUITE 2: ACCEPT-LANGUAGE HEADER DETECTION
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("sub_intent", [
    "policy_return",  # Test representative sub_intents
    "product_care",
    "account_orders"
])
async def test_accept_language_header_en(
    http_client: httpx.AsyncClient,
    sub_intent: str
):
    """
    Test: Accept-Language header detection (EN).
    
    Validates:
    - System detects EN from Accept-Language header
    - Returns EN content without explicit language parameter
    """
    response = await http_client.get(
        "/kb/answer",
        params={"sub_intent": sub_intent},
        headers={"Accept-Language": "en-US,en;q=0.9,es;q=0.8"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should auto-detect EN from header
    assert data["language"] == "en", (
        f"Expected language=en from Accept-Language header, got {data['language']}"
    )
    assert len(data["answer"]) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("sub_intent", [
    "policy_shipping",
    "product_sizing",
    "general_faq"
])
async def test_accept_language_header_es(
    http_client: httpx.AsyncClient,
    sub_intent: str
):
    """
    Test: Accept-Language header detection (ES).
    
    Validates:
    - System detects ES from Accept-Language header
    - Returns ES content without explicit language parameter
    """
    response = await http_client.get(
        "/kb/answer",
        params={"sub_intent": sub_intent},
        headers={"Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should auto-detect ES from header
    assert data["language"] == "es", (
        f"Expected language=es from Accept-Language header, got {data['language']}"
    )
    assert len(data["answer"]) > 0


# ══════════════════════════════════════════════════════════════════════════
# TEST SUITE 3: DEFAULT LANGUAGE FALLBACK
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("sub_intent", [
    "policy_warranty",
    "product_material",
    "account_modifications"
])
async def test_default_language_es(
    http_client: httpx.AsyncClient,
    sub_intent: str
):
    """
    Test: Default language (ES) when no language specified.
    
    Validates:
    - System defaults to ES when no language parameter
    - System defaults to ES when no Accept-Language header
    """
    response = await http_client.get(
        "/kb/answer",
        params={"sub_intent": sub_intent}
        # No language parameter, no Accept-Language header
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should default to ES
    assert data["language"] == "es", (
        f"Expected default language=es, got {data['language']}"
    )
    assert len(data["answer"]) > 0


# ══════════════════════════════════════════════════════════════════════════
# TEST SUITE 4: INVALID LANGUAGE FALLBACK
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_language,sub_intent", [
    ("fr", "policy_return"),
    ("de", "product_care"),
    ("pt", "account_orders"),
    ("invalid", "general_faq"),
    ("", "policy_shipping")
])
async def test_invalid_language_fallback(
    http_client: httpx.AsyncClient,
    invalid_language: str,
    sub_intent: str
):
    """
    Test: Fallback to ES for unsupported languages.
    
    Validates:
    - System gracefully handles invalid language codes
    - Falls back to ES (default)
    - Does not return 400 error
    """
    response = await http_client.get(
        "/kb/answer",
        params={
            "sub_intent": sub_intent,
            "language": invalid_language
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should fallback to ES
    assert data["language"] == "es", (
        f"Expected fallback to language=es for invalid language={invalid_language}, "
        f"got {data['language']}"
    )
    assert len(data["answer"]) > 0


# ══════════════════════════════════════════════════════════════════════════
# TEST SUITE 5: PRIORITY ORDER
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_language_priority_explicit_over_header(http_client: httpx.AsyncClient):
    """
    Test: Explicit language parameter takes priority over Accept-Language header.
    
    Validates:
    - Explicit ?language=es overrides Accept-Language: en
    """
    response = await http_client.get(
        "/kb/answer",
        params={
            "sub_intent": "policy_return",
            "language": "es"  # Explicit ES
        },
        headers={"Accept-Language": "en-US,en;q=0.9"}  # Header says EN
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Explicit parameter should win
    assert data["language"] == "es", (
        "Explicit language parameter should override Accept-Language header"
    )


@pytest.mark.asyncio
async def test_language_priority_header_over_default(http_client: httpx.AsyncClient):
    """
    Test: Accept-Language header takes priority over default.
    
    Validates:
    - Accept-Language: en overrides default ES
    """
    response = await http_client.get(
        "/kb/answer",
        params={"sub_intent": "policy_return"},
        # No explicit language parameter
        headers={"Accept-Language": "en-US,en;q=0.9"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Header should override default
    assert data["language"] == "en", (
        "Accept-Language header should override default language"
    )


# ══════════════════════════════════════════════════════════════════════════
# TEST SUITE 6: ERROR HANDLING
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_invalid_sub_intent(http_client: httpx.AsyncClient):
    """
    Test: Invalid sub_intent returns 400 Bad Request.
    
    Validates:
    - System rejects invalid sub_intent
    - Returns appropriate error message
    """
    response = await http_client.get(
        "/kb/answer",
        params={
            "sub_intent": "invalid_intent_xyz",
            "language": "es"
        }
    )
    
    # Should return 400 Bad Request
    assert response.status_code == 400, (
        f"Expected 400 Bad Request for invalid sub_intent, got {response.status_code}"
    )
    
    # Validate error structure
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_missing_sub_intent(http_client: httpx.AsyncClient):
    """
    Test: Missing sub_intent parameter returns 422 Unprocessable Entity.
    
    Validates:
    - System requires sub_intent parameter
    """
    response = await http_client.get(
        "/kb/answer",
        params={"language": "es"}
        # Missing sub_intent
    )
    
    # Should return 422 Unprocessable Entity
    assert response.status_code == 422, (
        f"Expected 422 for missing sub_intent, got {response.status_code}"
    )


# ══════════════════════════════════════════════════════════════════════════
# TEST SUITE 7: RESPONSE STRUCTURE VALIDATION
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_response_structure_complete(http_client: httpx.AsyncClient):
    """
    Test: Response structure contains all required fields.
    
    Validates:
    - All mandatory fields present
    - Field types correct
    """
    response = await http_client.get(
        "/kb/answer",
        params={
            "sub_intent": "policy_return",
            "language": "en"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Required fields
    required_fields = [
        "sub_intent",
        "language",
        "category",
        "answer",
        "sub_intent_value",
        "sources",
        "related_links"
    ]
    
    for field in required_fields:
        assert field in data, f"Response missing required field: {field}"
    
    # Type validations
    assert isinstance(data["sub_intent"], str)
    assert isinstance(data["language"], str)
    assert data["category"] is None or isinstance(data["category"], str)
    assert isinstance(data["answer"], str)
    assert isinstance(data["sub_intent_value"], str)
    assert isinstance(data["sources"], list)
    assert isinstance(data["related_links"], list)


# ══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def _contains_only_english(text: str) -> bool:
    """
    Check if text contains ONLY English patterns (no Spanish).
    
    Improved heuristic with better detection.
    """
    # Spanish-specific characters
    spanish_chars = ["á", "é", "í", "ó", "ú", "ñ", "¿", "¡", "Á", "É", "Í", "Ó", "Ú", "Ñ"]
    
    # If text contains Spanish characters, it's NOT only English
    for char in spanish_chars:
        if char in text:
            return False
    
    # Spanish-specific words (very common in Spanish, rare in English)
    spanish_words = [
        "política", "politica",  # Without accent too
        "devolución", "devolucion",
        "envío", "envio",
        "días", "dias",
        "más", "mas",
        "cómo", "como",
        "qué", "que",
        "nuestro", "nuestra",
        "puede", "pueden",
        "para",  # Very common in Spanish
        "por",   # Very common in Spanish
        "con",   # Common in Spanish
        "este", "esta", "estos", "estas"
    ]
    
    text_lower = text.lower()
    
    # Count Spanish word occurrences
    spanish_count = sum(1 for word in spanish_words if f" {word} " in f" {text_lower} ")
    
    # If multiple Spanish words found, it's NOT only English
    if spanish_count >= 2:
        return False
    
    return True


def _contains_only_spanish(text: str) -> bool:
    """
    Check if text contains ONLY Spanish patterns (no English).
    
    Improved heuristic with better detection.
    """
    # English-specific common words
    english_words = [
        "the", "and", "or", "but", "with",  # Very common English words
        "this", "that", "these", "those",
        "your", "our", "their",
        "can", "will", "should", "would",
        "you", "we", "they",
        "how", "what", "when", "where", "why",
        "product", "products",
        "return", "returns",
        "shipping", "shipment",
        "policy", "policies",
        "care", "guide", "information"
    ]
    
    text_lower = text.lower()
    
    # Count English word occurrences
    english_count = sum(1 for word in english_words if f" {word} " in f" {text_lower} ")
    
    # If multiple English words found, it's NOT only Spanish
    if english_count >= 3:  # Threshold: 3+ English words = English content
        return False
    
    return True


# ══════════════════════════════════════════════════════════════════════════
# SUMMARY REPORT
# ══════════════════════════════════════════════════════════════════════════

def pytest_sessionfinish(session, exitstatus):
    """
    Print summary after all tests complete.
    
    This hook runs after pytest finishes all tests.
    """
    print("\n" + "=" * 70)
    print("E2E TEST SUITE - SUMMARY")
    print("=" * 70)
    
    # Stats will be printed by pytest itself
    # This is just a custom header
    
    print("\nTest Coverage:")
    print(f"  • Sub-intents tested: {len(ALL_SUB_INTENTS)}")
    print(f"  • Languages tested: {len(SUPPORTED_LANGUAGES)}")
    print(f"  • Total combinations: {len(ALL_SUB_INTENTS) * len(SUPPORTED_LANGUAGES)}")
    print(f"  • Additional tests: ~20 (headers, fallback, errors)")
    print(f"  • Estimated total tests: ~{len(ALL_SUB_INTENTS) * len(SUPPORTED_LANGUAGES) + 20}")
    print("=" * 70 + "\n")