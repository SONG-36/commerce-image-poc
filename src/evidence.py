"""Legacy Evidence imports; filtering rules live in infrastructure.evidence.

Pass the current local bindings on each call so existing monkeypatches still
reach recursive cleaning and text redaction. No T01/SDK import is needed.
"""

import os

from infrastructure import evidence as _implementation
from infrastructure.evidence import PRIVATE_FIELDS, TOKEN_PATTERN, redact


def safe_text(text):
    return _implementation._safe_text(text, redactor=redact, pattern=TOKEN_PATTERN,
                                      environment=os.environ)


def private_field(name):
    return _implementation._private_field(name, fields=PRIVATE_FIELDS)


def clean_record(value):
    return _implementation._clean_record(value, clean=clean_record, field=private_field,
                                         private=contains_private, text=safe_text)


def contains_private(value):
    return _implementation._contains_private(value, field=private_field, private=contains_private,
                                             pattern=TOKEN_PATTERN, environment=os.environ)
