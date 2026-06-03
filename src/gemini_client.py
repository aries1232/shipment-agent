"""Thin Gemini wrapper. Two jobs: vision->structured extraction, and text generation."""

from functools import lru_cache

from google import genai
from google.genai import types
from pydantic import BaseModel

from src.config import settings


class GeminiClient:
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

    def extract(
        self, model: str, prompt: str, doc_bytes: bytes, mime_type: str, schema: type[BaseModel]
    ) -> BaseModel:
        """Vision call constrained to a Pydantic schema; returns the parsed object."""
        response = self._client.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=doc_bytes, mime_type=mime_type), prompt],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        return response.parsed

    def generate_text(self, model: str, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0),
        )
        return (response.text or "").strip()


@lru_cache
def get_client() -> GeminiClient:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set — copy .env.example to .env and add it.")
    return GeminiClient(settings.gemini_api_key)
