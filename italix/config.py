"""Safe local configuration loading without making cloud requests."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

SUPPORTED_CLOUD_PROVIDERS = ("gemini", "groq")


@dataclass(frozen=True)
class Settings:
    cloud_provider: str
    gemini_configured: bool
    groq_configured: bool


def load_settings(
    env_file: str | Path = ".env", *, require_cloud_key: bool = False
) -> Settings:
    """Load configuration and report key presence without returning key values."""
    load_dotenv(dotenv_path=env_file, override=False)
    provider = os.getenv("CLOUD_PROVIDER", "gemini").strip().lower()
    if provider not in SUPPORTED_CLOUD_PROVIDERS:
        choices = ", ".join(SUPPORTED_CLOUD_PROVIDERS)
        raise ValueError(f"CLOUD_PROVIDER must be one of: {choices}")

    key_presence = {
        "gemini": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "groq": bool(os.getenv("GROQ_API_KEY", "").strip()),
    }
    if require_cloud_key and not key_presence[provider]:
        variable = f"{provider.upper()}_API_KEY"
        raise ValueError(f"{variable} is required when cloud access is requested")

    return Settings(
        cloud_provider=provider,
        gemini_configured=key_presence["gemini"],
        groq_configured=key_presence["groq"],
    )
