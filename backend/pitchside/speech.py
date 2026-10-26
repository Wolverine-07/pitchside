"""Spoken commentary with Azure AI Speech neural voices (REST, no SDK needed)."""

from __future__ import annotations

import os
from functools import lru_cache
from xml.sax.saxutils import escape

import httpx

VOICES = {
    "en": ("en-GB", "en-GB-RyanNeural"),
    "hi": ("hi-IN", "hi-IN-MadhurNeural"),
    "es": ("es-ES", "es-ES-AlvaroNeural"),
}


def enabled() -> bool:
    return bool(os.getenv("AZURE_SPEECH_KEY"))


def _ssml(text: str, lang: str) -> str:
    locale, voice = VOICES.get(lang, VOICES["en"])
    # A touch faster than default: commentary, not an audiobook.
    return (
        f"<speak version='1.0' xml:lang='{locale}'><voice name='{voice}'>"
        f"<prosody rate='+8%'>{escape(text)}</prosody></voice></speak>"
    )


@lru_cache(maxsize=512)
def synthesize(text: str, lang: str) -> bytes:
    """MP3 audio for one caption. Cached, since every viewer of a match hears the same lines."""
    region = os.getenv("AZURE_SPEECH_REGION", "eastasia")
    r = httpx.post(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        headers={
            "Ocp-Apim-Subscription-Key": os.environ["AZURE_SPEECH_KEY"],
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "pitchside",
        },
        content=_ssml(text[:400], lang).encode(),
        timeout=10,
    )
    r.raise_for_status()
    return r.content
