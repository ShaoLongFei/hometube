"""
Translation system for the YouTube downloader app
"""

import os
from typing import Any

# Cache for translations to avoid repeated loading
_translations_cache = None
_configured_language = None
_default_language = "en"

_LANGUAGE_MODULES = {
    "en": "en",
    "fr": "fr",
    "zh": "zh",
    "zh-cn": "zh",
}


def configure_language(language: str) -> None:
    """
    Configure the UI language programmatically (used by main.py)

    Args:
        language: Language code (e.g., 'en', 'fr')
    """
    global _configured_language, _translations_cache
    normalized = (language or _default_language).lower()
    _configured_language = normalized
    _translations_cache = None  # Clear cache to force reload


def normalize_language_code(language: str | None) -> str:
    """Normalize a language code and apply safe fallback."""
    normalized = (language or _default_language).lower()
    return _LANGUAGE_MODULES.get(normalized, _default_language)


def get_supported_languages() -> list[str]:
    """Return languages that should be shown in the UI selector."""
    return ["en", "zh", "fr"]


def get_translations() -> dict[str, Any]:
    """Get translations based on configured language or UI_LANGUAGE environment variable"""
    global _translations_cache

    # Use cached translations if available
    if _translations_cache is not None:
        return _translations_cache

    # Priority: configured language > environment variable > default
    if _configured_language is not None:
        language = normalize_language_code(_configured_language)
    else:
        language = normalize_language_code(os.getenv("UI_LANGUAGE", _default_language))

    module_name = _LANGUAGE_MODULES.get(language, _default_language)

    if module_name == "en":
        try:
            from .en import TRANSLATIONS
        except ImportError:
            from en import TRANSLATIONS
    elif module_name == "fr":
        try:
            from .fr import TRANSLATIONS
        except ImportError:
            from fr import TRANSLATIONS
    else:
        try:
            from .zh import TRANSLATIONS
        except ImportError:
            from zh import TRANSLATIONS

    # Cache the translations
    _translations_cache = TRANSLATIONS
    return TRANSLATIONS


def t(key: str, **kwargs) -> str:
    """
    Translate a key with optional formatting

    Args:
        key: Translation key
        **kwargs: Format arguments for string formatting

    Returns:
        Translated string with optional formatting applied
    """
    translations = get_translations()
    text = translations.get(key, f"[MISSING: {key}]")

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text

    return text
