"""Tests never call Azure: blank the service keys before .env is loaded (load_dotenv won't override them)."""

import os

for key in (
    "AZURE_TRANSLATOR_KEY",
    "AZURE_SPEECH_KEY",
    "AZURE_CONTENT_SAFETY_KEY",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
):
    os.environ[key] = ""
os.environ.setdefault("PITCHSIDE_PROVIDER", "templates")
