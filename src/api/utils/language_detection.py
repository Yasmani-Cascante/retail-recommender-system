"""Language detection utilities for multi-language support."""

from typing import Optional
from fastapi import Request


def detect_language_from_request(
    request: Request,
    supported_languages: set = {"es", "en"},
    default_language: str = "es"
) -> str:
    """
    Detect user's preferred language from Accept-Language header.
    
    Priority:
    1. Accept-Language header (browser/client preference)
    2. Default language
    
    Args:
        request: FastAPI Request object
        supported_languages: Set of supported language codes
        default_language: Fallback language
        
    Returns:
        Language code (e.g., 'es', 'en')
        
    Examples:
        >>> # Header: "en-US,en;q=0.9,es;q=0.8"
        >>> detect_language_from_request(request)
        'en'
        
        >>> # Header: "es-ES,es;q=0.9"
        >>> detect_language_from_request(request)
        'es'
        
        >>> # No header
        >>> detect_language_from_request(request)
        'es'  # default
    """
    # Get Accept-Language header
    accept_language = request.headers.get("Accept-Language", "")
    
    if not accept_language:
        return default_language
    
    # Parse Accept-Language header
    # Format: "en-US,en;q=0.9,es;q=0.8,fr;q=0.7"
    languages_with_quality = []
    
    for lang_part in accept_language.split(","):
        # Split by ';' to separate language from quality
        parts = lang_part.split(";")
        
        # Extract language code (before '-' for locale variants)
        lang_code = parts[0].split("-")[0].strip().lower()
        
        # Extract quality value (default 1.0)
        quality = 1.0
        if len(parts) > 1 and "q=" in parts[1]:
            try:
                quality = float(parts[1].split("=")[1].strip())
            except (ValueError, IndexError):
                quality = 1.0
        
        languages_with_quality.append((lang_code, quality))
    
    # Sort by quality (descending)
    languages_with_quality.sort(key=lambda x: x[1], reverse=True)
    
    # Find first supported language
    for lang_code, quality in languages_with_quality:
        if lang_code in supported_languages:
            return lang_code
    
    # No supported language found → default
    return default_language


def validate_language(
    language: str,
    supported_languages: set = {"es", "en"},
    default_language: str = "es"
) -> str:
    """
    Validate and normalize language code.
    
    Args:
        language: Language code to validate
        supported_languages: Set of supported languages
        default_language: Fallback if invalid
        
    Returns:
        Validated language code
    """
    language_normalized = language.lower().strip()
    
    if language_normalized in supported_languages:
        return language_normalized
    
    return default_language