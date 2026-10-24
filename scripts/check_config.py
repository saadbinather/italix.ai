"""Validate local configuration without displaying secret values."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from italix.config import load_settings


parser = argparse.ArgumentParser()
parser.add_argument(
    "--require-cloud",
    action="store_true",
    help="require a key for the selected cloud provider",
)
args = parser.parse_args()

try:
    settings = load_settings(require_cloud_key=args.require_cloud)
except ValueError as exc:
    raise SystemExit(f"Configuration invalid: {exc}") from exc

print("Configuration valid")
print(f"Cloud provider: {settings.cloud_provider}")
print(f"Gemini key configured: {settings.gemini_configured}")
print(f"Groq key configured: {settings.groq_configured}")
print("No cloud request was made.")
