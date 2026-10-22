"""Evidence sanitization only: no SDK, business imports or filesystem access.

The private helpers accept the old module's function bindings explicitly. They
let its compatibility functions retain monkeypatch behavior without duplicating
the filtering rules or using a global provider/registry.
"""

import json
import os
import re


PRIVATE_FIELDS = {"api_key", "openai_api_key", "authorization", "proxy_authorization",
                  "access_token", "refresh_token", "cookie", "set_cookie",
                  "password", "client_secret", "secret_key", "id_token", "x_api_key", "api_token",
                  "token", "credentials",
                  "chain_of_thought", "encrypted_content"}
TOKEN_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9._~-]+|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}", re.I)


def redact(text, key):
    if key:
        text = text.replace(key, "[REDACTED]")
    return re.sub(r"sk-[A-Za-z0-9_-]{10,}", "[REDACTED]", text)


def _safe_text(text, *, redactor, pattern, environment):
    return pattern.sub("[REDACTED]", redactor(text, environment.get("OPENAI_API_KEY", "")))


def safe_text(text):
    return _safe_text(text, redactor=redact, pattern=TOKEN_PATTERN, environment=os.environ)


def _private_field(name, *, fields):
    return name.lower().replace("-", "_") in fields


def private_field(name):
    return _private_field(name, fields=PRIVATE_FIELDS)


def _clean_record(value, *, clean, field, private, text):
    if isinstance(value, dict):
        if value.get("type") == "reasoning":
            return {"omitted": "hidden reasoning"}
        return {key: clean(item) for key, item in value.items() if not field(key)}
    if isinstance(value, list):
        return [clean(item) for item in value
                if not isinstance(item, dict) or item.get("type") != "reasoning"]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                decoded = json.loads(value)
                if private(decoded):
                    return json.dumps(clean(decoded), ensure_ascii=False)
            except ValueError:
                pass
        return text(value)
    return value


def clean_record(value):
    """Keep returned results/usage, excluding credentials and hidden reasoning."""
    return _clean_record(value, clean=clean_record, field=private_field,
                         private=contains_private, text=safe_text)


def _contains_private(value, *, field, private, pattern, environment):
    if isinstance(value, dict):
        return value.get("type") == "reasoning" or any(
            field(key) and item not in (None, "", [], {}) or private(item)
            for key, item in value.items())
    if isinstance(value, list):
        return any(private(item) for item in value)
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                if private(json.loads(value)):
                    return True
            except ValueError:
                pass
        key = environment.get("OPENAI_API_KEY", "")
        return bool(pattern.search(value) or key and key in value)
    return False


def contains_private(value):
    return _contains_private(value, field=private_field, private=contains_private,
                             pattern=TOKEN_PATTERN, environment=os.environ)
