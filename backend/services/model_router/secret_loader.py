from __future__ import annotations

import os
from pathlib import Path


class SecretLoader:
    """Loads and validates API secrets from environment variables only."""

    REQUIRED_KEYS = [
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
    ]

    @staticmethod
    def load(key: str) -> str:
        return os.getenv(key, "")

    @classmethod
    def validate(cls) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for key in cls.REQUIRED_KEYS:
            val = os.getenv(key, "")
            configured = bool(val) and val not in ("change-me", "your-key-here", "sk-xxx")
            result[key] = configured
        return result

    @staticmethod
    def mask(key: str) -> str:
        if len(key) <= 4:
            return "*" * len(key)
        return key[:3] + "*" * (len(key) - 7) + key[-4:]

    @classmethod
    def has_any_provider(cls) -> bool:
        return any(cls.validate().values())

    @classmethod
    def default_provider(cls) -> str:
        """Return the first configured provider, or 'local'."""
        configured = cls.validate()
        for provider_key, ok in configured.items():
            if ok:
                name = provider_key.replace("_API_KEY", "").lower()
                return name
        return "local"
