"""AI providers that read PDF pages and return ChunkFindings.

    gemini  free tier available — key from https://aistudio.google.com/apikey (GEMINI_API_KEY)
    claude  Anthropic API (ANTHROPIC_API_KEY or an `ant auth login` profile)

Choose with AUTOTAX_EXTRACTOR=gemini|claude; otherwise the first provider with credentials wins
(Gemini first, since it is free). Both get the same instructions and the same output schema, and
everything they return is validated in extract.merge() before it reaches a draft.
"""

from __future__ import annotations

import base64
import os
import re
import time
from pathlib import Path
from typing import Protocol

from .schema import SYSTEM, ChunkFindings


class ChunkFailed(Exception):
    """The provider could not produce usable findings for this chunk (recorded, not fatal)."""


class Provider(Protocol):
    name: str
    model: str
    pages_per_chunk: int
    max_chunk_bytes: int

    def read_chunk(self, pdf: bytes, prompt: str) -> ChunkFindings: ...


# --- Gemini ----------------------------------------------------------------------------------

GEMINI_FLASH = re.compile(r"^models/gemini-(\d+(?:\.\d+)?)-flash(-lite)?$")


def pick_gemini_model(names: list[str]) -> str:
    """Newest stable 'flash' model (falls back to 'flash-lite'). Override with GEMINI_MODEL."""
    ranked = []
    for n in names:
        m = GEMINI_FLASH.match(n)
        if m:
            ranked.append((m.group(2) is None, float(m.group(1)), n.removeprefix("models/")))
    if not ranked:
        raise RuntimeError("no Gemini flash model available for this key; set GEMINI_MODEL")
    return max(ranked)[2]


class GeminiProvider:
    name = "gemini"
    pages_per_chunk = 30
    max_chunk_bytes = 14 * 1024 * 1024  # inline request limit is 20 MB after base64 (+33%)
    max_attempts = 6

    def __init__(self, model: str | None = None, client=None):
        from google import genai

        self.client = client or genai.Client(api_key=_gemini_key())
        self.model = model or os.environ.get("GEMINI_MODEL") or pick_gemini_model(
            [m.name for m in self.client.models.list() if "generateContent" in (m.supported_actions or [])]
        )

    def read_chunk(self, pdf: bytes, prompt: str) -> ChunkFindings:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=ChunkFindings,
        )
        contents = [types.Part.from_bytes(data=pdf, mime_type="application/pdf"), prompt]
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = self.client.models.generate_content(model=self.model, contents=contents, config=config)
                break
            except errors.APIError as e:
                # Free tier: 429 = per-minute/day quota, 503 = overloaded. Back off and retry.
                if e.code in (429, 500, 503) and attempt < self.max_attempts:
                    time.sleep(_retry_delay(e, attempt))
                    continue
                if e.code == 429:
                    raise ChunkFailed(f"Gemini quota exhausted ({self.model}); try tomorrow or set GEMINI_MODEL") from e
                raise
        cand = (resp.candidates or [None])[0]
        reason = getattr(getattr(cand, "finish_reason", None), "name", None)
        if reason not in (None, "STOP"):
            raise ChunkFailed(f"Gemini stopped early ({reason})")
        if resp.parsed is None:
            raise ChunkFailed("Gemini returned no parsable JSON")
        return resp.parsed


def _retry_delay(err, attempt: int) -> float:
    # The API often says how long to wait, e.g. "retryDelay": "37s".
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s", str(getattr(err, "details", "") or err))
    return min(float(m.group(1)) + 1 if m else 2**attempt * 5, 120)


def _gemini_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


# --- Claude ----------------------------------------------------------------------------------

class ClaudeProvider:
    name = "claude"
    model = "claude-opus-5-5"
    pages_per_chunk = 60
    max_chunk_bytes = 22 * 1024 * 1024  # request limit is 32 MB after base64 (+33%)

    def __init__(self, client=None):
        import anthropic

        self.client = client or anthropic.Anthropic()

    def read_chunk(self, pdf: bytes, prompt: str) -> ChunkFindings:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "high"},
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.standard_b64encode(pdf).decode()}},
                    {"type": "text", "text": prompt},
                ],
            }],
            output_format=ChunkFindings,
        )
        if response.stop_reason == "refusal":
            raise ChunkFailed(f"model declined ({getattr(response.stop_details, 'category', None)})")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise ChunkFailed(f"incomplete response ({response.stop_reason})")
        return response.parsed_output


def _claude_credentials() -> bool:
    if any(os.environ.get(v) for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_FEDERATION_RULE_ID")):
        return True
    return (Path.home() / ".config" / "anthropic").is_dir()


# --- selection -------------------------------------------------------------------------------

def available() -> list[str]:
    return [n for n, ok in (("gemini", bool(_gemini_key())), ("claude", _claude_credentials())) if ok]


def get_provider(name: str | None = None) -> Provider | None:
    """The requested provider, or the first with credentials. None means: skip extraction."""
    name = name or os.environ.get("AUTOTAX_EXTRACTOR")
    if name is None:
        avail = available()
        if not avail:
            return None
        name = avail[0]
    if name == "gemini":
        return GeminiProvider()
    if name == "claude":
        return ClaudeProvider()
    raise ValueError(f"unknown extractor {name!r} (use gemini or claude)")
