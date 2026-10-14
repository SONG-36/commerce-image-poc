"""Small evidence helpers; no model calls or separate version store."""

import json
import os
import re

from generate_image import redact

PRIVATE_FIELDS = {"api_key", "openai_api_key", "authorization", "proxy_authorization",
                  "access_token", "refresh_token", "cookie", "set_cookie",
                  "password", "client_secret", "secret_key", "id_token", "x_api_key", "api_token",
                  "token", "credentials",
                  "chain_of_thought", "encrypted_content"}
TOKEN_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9._~-]+|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}", re.I)


def safe_text(text):
    return TOKEN_PATTERN.sub("[REDACTED]", redact(text, os.environ.get("OPENAI_API_KEY", "")))


def private_field(name):
    return name.lower().replace("-", "_") in PRIVATE_FIELDS


def clean_record(value):
    """Keep returned results/usage, excluding credentials and hidden reasoning."""
    if isinstance(value, dict):
        if value.get("type") == "reasoning":
            return {"omitted": "hidden reasoning"}
        return {key: clean_record(item) for key, item in value.items() if not private_field(key)}
    if isinstance(value, list):
        return [clean_record(item) for item in value
                if not isinstance(item, dict) or item.get("type") != "reasoning"]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                decoded = json.loads(value)
                if contains_private(decoded):
                    return json.dumps(clean_record(decoded), ensure_ascii=False)
            except ValueError:
                pass
        return safe_text(value)
    return value


def contains_private(value):
    if isinstance(value, dict):
        return value.get("type") == "reasoning" or any(
            private_field(key) and item not in (None, "", [], {}) or contains_private(item)
            for key, item in value.items())
    if isinstance(value, list):
        return any(contains_private(item) for item in value)
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                if contains_private(json.loads(value)):
                    return True
            except ValueError:
                pass
        key = os.environ.get("OPENAI_API_KEY", "")
        return bool(TOKEN_PATTERN.search(value) or key and key in value)
    return False
