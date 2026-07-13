"""Normalization helpers for guest identity lookup fields.

These produce the canonical values stored in ``Guest.phone_normalized`` and
``Guest.national_id_normalized`` and are ALSO applied to lookup query params, so
an exact match works regardless of the spacing / punctuation a caller typed.

Pure functions, no Django imports — safe to reuse from models, serializers and
views without circular-import risk.
"""
from __future__ import annotations

import re

# Everything that is NOT a digit — used to strip a phone down to its digits.
_NON_DIGIT = re.compile(r"\D")
# Everything that is NOT an ASCII alphanumeric — used to canonicalize an ID.
_NON_ALNUM = re.compile(r"[^0-9A-Z]")


def normalize_phone(value: str) -> str:
    """Digits only, keeping a single leading ``+`` if the input had one.

    A ``+`` is only meaningful as an international prefix at the very start, so
    any other punctuation, spaces or embedded ``+`` are dropped. Returns ``""``
    for empty / digitless input.
    """
    if not value:
        return ""
    raw = str(value).strip()
    has_plus = raw.startswith("+")
    digits = _NON_DIGIT.sub("", raw)
    if not digits:
        return ""
    return f"+{digits}" if has_plus else digits


def normalize_id(value: str) -> str:
    """Strip spaces / dashes / punctuation and uppercase — a canonical ID key.

    Only ASCII alphanumerics survive; everything else is removed. Returns ``""``
    for empty input.
    """
    if not value:
        return ""
    return _NON_ALNUM.sub("", str(value).upper())
