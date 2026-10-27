"""Azure AI Translator: the Linguist's safety net and the instant-caption translator.

The Linguist agent writes natural commentary in each language. When a translation fails the
Verifier's checks twice, or for the instant template captions that can't wait for a model,
Translator gives a faithful translation in a few hundred milliseconds, so a viewer who chose
Hindi never gets English.
"""

from __future__ import annotations

import os

import httpx

ENDPOINT = "https://api.cognitive.microsofttranslator.com/translate"

# Football words generic machine translation gets wrong ("goal" as in "target").
GLOSSARY = {
    "expected goals": {
        "hi": "अपेक्षित गोल",
        "es": "goles esperados",
        "fr": "buts attendus",
        "pt": "golos esperados",
        "ar": "أهداف متوقعة",
        "de": "erwartete Tore",
        "ja": "期待ゴール",
    },
    "off target": {
        "hi": "निशाने से बाहर",
        "es": "fuera",
        "fr": "non cadré",
        "pt": "ao lado",
        "ar": "خارج المرمى",
        "de": "neben das Tor",
        "ja": "枠外",
    },
    "Goal": {
        "hi": "गोल",
        "es": "Gol",
        "fr": "But",
        "pt": "Gol",
        "ar": "هدف",
        "de": "Tor",
        "ja": "ゴール",
    },
    "goal": {
        "hi": "गोल",
        "es": "gol",
        "fr": "but",
        "pt": "gol",
        "ar": "هدف",
        "de": "Tor",
        "ja": "ゴール",
    },
    "Big chance": {
        "hi": "बड़ा मौका",
        "es": "Gran ocasión",
        "fr": "Grosse occasion",
        "pt": "Grande chance",
        "ar": "فرصة كبيرة",
        "de": "Großchance",
        "ja": "決定機",
    },
    "save": {
        "hi": "बचाव",
        "es": "parada",
        "fr": "arrêt",
        "pt": "defesa",
        "ar": "تصدٍّ",
        "de": "Parade",
        "ja": "セーブ",
    },
}


def _protect(text: str, to: str) -> str:
    """Wrap glossary terms in Translator's dynamic-dictionary markup."""
    import re

    for term, by_lang in GLOSSARY.items():
        if to in by_lang:
            text = re.sub(
                rf"\b{re.escape(term)}\b",
                f'<mstrans:dictionary translation="{by_lang[to]}">{term}</mstrans:dictionary>',
                text,
            )
    return text


def enabled() -> bool:
    return bool(os.getenv("AZURE_TRANSLATOR_KEY"))


async def translate(texts: list[str], to: str) -> list[str] | None:
    """Translate texts from English. None when Translator isn't configured or the call fails."""
    if not enabled() or not texts:
        return None
    headers = {
        "Ocp-Apim-Subscription-Key": os.environ["AZURE_TRANSLATOR_KEY"],
        "Content-Type": "application/json",
    }
    region = os.getenv("AZURE_TRANSLATOR_REGION")
    if region:
        headers["Ocp-Apim-Subscription-Region"] = region
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(
                ENDPOINT,
                params={"api-version": "3.0", "from": "en", "to": to},
                headers=headers,
                json=[{"Text": _protect(t, to)} for t in texts],
            )
            r.raise_for_status()
            return [item["translations"][0]["text"] for item in r.json()]
    except httpx.HTTPError:
        return None
