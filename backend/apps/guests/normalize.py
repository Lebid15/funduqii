"""Normalization helpers for guest identity lookup fields.

These produce the canonical values stored in ``Guest.phone_normalized``,
``Guest.national_id_normalized`` and ``Guest.document_number_normalized`` and are
ALSO applied to lookup query params, so an exact match works regardless of the
spacing / punctuation a caller typed.

Pure functions, no Django imports — safe to reuse from models, serializers and
views without circular-import risk.

Non-Latin numerals
------------------
Arabic-Indic (``٠١٢٣٤٥٦٧٨٩`` U+0660-U+0669) and Extended / Persian Arabic-Indic
(``۰۱۲۳۴۵۶۷۸۹`` U+06F0-U+06F9) digits are FOLDED to Latin ``0-9`` *before* any
stripping, so a valid non-Latin identifier can NEVER normalize to ``""`` (owner
decision: never let a valid id become empty).

Phone canonicalization (deterministic, no phone library)
-------------------------------------------------------
There is no phone-parsing library in this project's requirements (checked
``backend/requirements/base.txt``). :func:`normalize_phone` is therefore a
*minimal, deterministic* canonicalizer:

- International input (leading ``+`` or ``00``) keeps its OWN embedded country
  calling code.
- A local (national) number is canonicalized to E.164 ONLY when a
  ``default_country`` (ISO-3166-1 alpha-2) is supplied AND that country is in the
  curated calling-code table below. There is NO global/implicit country
  fallback.
- Nothing is ever guessed: :func:`normalize_phone` never fabricates a country
  code. When a local number has no resolvable country it falls back to the folded
  national-digit key (the historical behavior) — an honest, country-less key,
  never an approximation.

**Limitation (flagged):** the ``_CALLING_CODES`` table is a curated subset, not
the full ITU list. A local number whose country is outside the table cannot be
promoted to E.164; enter it in international ``+``/``00`` form (which needs no
table). Strict validation for the identity service lives in
:func:`canonical_phone`, which RAISES :class:`PhoneNormalizationError` instead of
falling back — the clean seam a caller turns into a validation error.
"""
from __future__ import annotations

import re

# Everything that is NOT an ASCII digit — used to strip a phone to its digits.
_NON_DIGIT = re.compile(r"[^0-9]")
# Everything that is NOT an ASCII alphanumeric — used to canonicalize an ID.
_NON_ALNUM = re.compile(r"[^0-9A-Z]")

# --- Non-Latin digit folding ------------------------------------------------
# Arabic-Indic ZERO is U+0660; Extended / Persian Arabic-Indic ZERO is U+06F0.
# Both blocks are contiguous 0..9, so a simple offset table folds them to Latin.
_DIGIT_FOLD_MAP: dict[int, str] = {}
for _i in range(10):
    _DIGIT_FOLD_MAP[0x0660 + _i] = str(_i)  # Arabic-Indic
    _DIGIT_FOLD_MAP[0x06F0 + _i] = str(_i)  # Extended / Persian
del _i


def fold_digits(value: str) -> str:
    """Fold Arabic-Indic / Persian digits to Latin ``0-9``. Other chars pass
    through unchanged. Deterministic and pure."""
    return str(value).translate(_DIGIT_FOLD_MAP)


class PhoneNormalizationError(ValueError):
    """Strict phone canonicalization could not produce a deterministic E.164
    value (uninterpretable number, or a local number with no resolvable
    country). Callers turn this into a clean validation error — it carries NO
    sensitive number detail in its message."""


def _canonical_alnum(value: str) -> str:
    """Fold digits, uppercase, keep only ASCII alphanumerics. The shared core of
    :func:`normalize_id` and :func:`normalize_document`."""
    if not value:
        return ""
    return _NON_ALNUM.sub("", fold_digits(value).upper())


def normalize_id(value: str) -> str:
    """Canonical national-ID key: fold non-Latin digits, uppercase, strip every
    non-alphanumeric. A valid non-Latin id survives (never becomes ``""``).
    Returns ``""`` for empty input."""
    return _canonical_alnum(value)


def normalize_document(value: str) -> str:
    """Canonical document-number key — same rule as :func:`normalize_id`
    (fold + uppercase + alphanumeric-only). Kept as its own name so document and
    national-id keys have distinct, self-documenting call sites."""
    return _canonical_alnum(value)


def _phone_digits(folded: str) -> tuple[bool, str]:
    """Return ``(is_international, digits)`` for an already-folded phone string.

    A leading ``+`` or ``00`` marks an international number; the returned digits
    are the country-code + national-significant-number (the international access
    ``00`` is dropped). For a local number the raw national digits are returned.
    """
    raw = folded.strip()
    digits = _NON_DIGIT.sub("", raw)
    if raw.startswith("+"):
        return True, digits
    if raw.startswith("00"):
        # Drop the international access code; digits starts with the two zeros.
        return True, digits[2:]
    return False, digits


def normalize_phone(value: str, *, default_country: str | None = None) -> str:
    """Lenient canonical phone KEY used by ``Guest.save``, the reservation-form
    lookup and data migrations. Never raises.

    - Empty / digit-less input -> ``""`` ("no phone").
    - Non-Latin digits are folded to Latin first.
    - International input (``+`` / ``00``) -> ``"+"`` + its own country code +
      national number.
    - Local input WITH a resolvable ``default_country`` -> ``"+"`` + that
      country's calling code + national number (a single national trunk ``0`` is
      dropped).
    - Local input with NO resolvable country -> the folded national-digit key
      (honest, country-less; never a guessed country code).
    """
    if not value:
        return ""
    folded = fold_digits(value)
    intl, digits = _phone_digits(folded)
    if not digits:
        return ""
    if intl:
        return f"+{digits}"
    cc = _resolve_calling_code(default_country)
    if cc is None:
        # No country context: keep the historical country-less digit key.
        return digits
    return f"+{cc}{_strip_trunk_zero(digits)}"


def canonical_phone(value: str, *, default_country: str | None = None) -> str:
    """STRICT canonical E.164-style value for the identity service (next wave).

    Returns ``""`` for empty input ("no phone" is valid). Otherwise returns a
    ``+``-prefixed E.164 string, or RAISES :class:`PhoneNormalizationError` when
    the number cannot be canonicalized deterministically — an uninterpretable
    number, or a local number with no resolvable ``default_country`` (NO global
    fallback, never an approximation).

    Not wired into any write path in this wave; it is the clean validation seam.
    """
    if not value:
        return ""
    folded = fold_digits(value)
    intl, digits = _phone_digits(folded)
    if not digits:
        raise PhoneNormalizationError("phone has no digits")
    if intl:
        if not _plausible_e164(digits):
            raise PhoneNormalizationError("international number out of E.164 bounds")
        return f"+{digits}"
    cc = _resolve_calling_code(default_country)
    if cc is None:
        raise PhoneNormalizationError("local number needs a resolvable country")
    national = _strip_trunk_zero(digits)
    combined = f"{cc}{national}"
    if not _plausible_e164(combined):
        raise PhoneNormalizationError("number out of E.164 bounds")
    return f"+{combined}"


def _strip_trunk_zero(national_digits: str) -> str:
    """Drop a single national trunk-prefix ``0`` (used by most countries)."""
    if national_digits.startswith("0"):
        return national_digits[1:]
    return national_digits


def _plausible_e164(digits: str) -> bool:
    """A loose E.164 sanity bound: 7..15 significant digits. Used only by the
    STRICT path — the lenient key path never rejects, so stored keys stay
    consistent with historical values."""
    return 7 <= len(digits) <= 15


def _resolve_calling_code(default_country: str | None) -> str | None:
    """ISO-3166-1 alpha-2 (case-insensitive) -> E.164 calling code, or ``None``
    when unknown / not supplied. Never guesses."""
    if not default_country:
        return None
    return _CALLING_CODES.get(default_country.strip().upper())


# Curated ISO-3166-1 alpha-2 -> E.164 country calling code table. Not the full
# ITU list (see the module docstring's flagged limitation): it covers the
# operational region and the widely-used origins. A country outside this table
# cannot be locally canonicalized — its numbers must be entered international.
_CALLING_CODES: dict[str, str] = {
    # Middle East & North Africa (operational core)
    "SA": "966", "AE": "971", "QA": "974", "BH": "973", "KW": "965",
    "OM": "968", "YE": "967", "JO": "962", "LB": "961", "SY": "963",
    "IQ": "964", "PS": "970", "IL": "972", "EG": "20", "LY": "218",
    "TN": "216", "DZ": "213", "MA": "212", "SD": "249", "MR": "222",
    "TR": "90", "IR": "98",
    # Europe (common)
    "GB": "44", "IE": "353", "FR": "33", "DE": "49", "IT": "39",
    "ES": "34", "PT": "351", "NL": "31", "BE": "32", "LU": "352",
    "CH": "41", "AT": "43", "SE": "46", "NO": "47", "DK": "45",
    "FI": "358", "IS": "354", "PL": "48", "CZ": "420", "SK": "421",
    "HU": "36", "RO": "40", "BG": "359", "GR": "30", "CY": "357",
    "RU": "7", "UA": "380", "BY": "375", "RS": "381", "HR": "385",
    "SI": "386", "BA": "387", "MK": "389", "AL": "355", "MT": "356",
    "MD": "373", "GE": "995", "AM": "374", "AZ": "994",
    # Americas
    "US": "1", "CA": "1", "MX": "52", "BR": "55", "AR": "54",
    "CL": "56", "CO": "57", "PE": "51", "VE": "58",
    # Asia-Pacific (common)
    "CN": "86", "JP": "81", "KR": "82", "IN": "91", "PK": "92",
    "BD": "880", "LK": "94", "AF": "93", "ID": "62", "MY": "60",
    "SG": "65", "TH": "66", "PH": "63", "VN": "84", "HK": "852",
    "AU": "61", "NZ": "64",
    # Sub-Saharan Africa (common)
    "NG": "234", "KE": "254", "ET": "251", "GH": "233", "ZA": "27",
    "TZ": "255", "UG": "256", "SO": "252", "DJ": "253", "SS": "211",
}
