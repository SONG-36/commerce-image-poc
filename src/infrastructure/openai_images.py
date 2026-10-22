"""Existing Images API transport/configuration; no business or CLI policy."""

from openai import OpenAI

MODELS = ("gpt-image-2.5-sunburst", "gpt-image-2.5-flare")
PARAMETERS = {"n": 1, "quality": "low", "size": "1024x1536", "output_format": "png"}
TIMEOUT_SECONDS = 180.0


def _make_client(api_key, *, client_class, timeout_seconds):
    # Fixed official endpoint; no paid retry or fallback, including SDK defaults.
    return client_class(api_key=api_key, base_url="https://api.openai.com/v1",
                        max_retries=0, timeout=timeout_seconds)


def make_client(api_key):
    return _make_client(api_key, client_class=OpenAI, timeout_seconds=TIMEOUT_SECONDS)
