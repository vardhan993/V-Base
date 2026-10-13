"""Phone-number normalization with country-code awareness.

Spreadsheet phone columns arrive in every imaginable shape (``+1 (415) 555-0132``,
``0044 20 7946 0958``, ``98765 43210`` …). This module reduces each raw value to
one canonical display form plus machine-usable facts:

- :func:`normalize_phone` strips separators, converts a leading ``00`` to
  ``+``, and validates the digit count (ITU-T E.164 allows at most 15 digits,
  and anything under 7 is not a diallable number).
- Numbers that already carry a ``+`` country code are kept verbatim (apart
  from separator removal) — the country code is never guessed or rewritten.
- Numbers without any international prefix are kept as dialled and flagged
  with ``has_country_code=False`` so Data Quality can ask for review instead
  of silently inventing a ``+1`` or ``+91``.

The function is deliberately dependency-free (no ``phonenumbers`` package) so
it works identically in the API, the importer, and the test suite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MIN_DIGITS = 7
_MAX_DIGITS = 15


@dataclass(frozen=True)
class NormalizedPhone:
    """Result of normalizing one raw phone value."""

    #: Canonical display form, e.g. ``+14155550132`` or ``98765 43210``-as-digits.
    display: str
    #: ``+``-prefixed E.164-style value, or None when no country code is present.
    e164: str | None
    #: True when the value carries an explicit international prefix.
    has_country_code: bool
    #: True when the digit count is outside the diallable range.
    suspicious: bool


def normalize_phone(raw: object) -> NormalizedPhone | None:
    """Normalize ``raw`` to a :class:`NormalizedPhone`, or None when blank.

    Non-string numerics (ints/floats from spreadsheet cells) are accepted and
    stringified first. Extension suffixes (``x123``, ``ext. 4``) are dropped —
    V-Base stores the reachable number, not the PBX routing.
    """
    if raw is None:
        return None
    text = str(raw).strip() if not isinstance(raw, str) else raw.strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "-"}:
        return None

    # Drop common extension suffixes before anything else.
    text = re.split(r"\s*(?:ext\.?|x|extension)\s*:?\s*\d+\s*$", text, flags=re.IGNORECASE)[0].strip()
    if not text:
        return None

    has_plus = text.startswith("+")
    working = text
    if working.startswith("00"):
        working = "+" + working[2:]
        has_plus = True

    # Keep a leading + and digits only; everything else is formatting noise.
    digits = re.sub(r"\D", "", working)
    if not digits:
        return None

    display = ("+" + digits) if has_plus else digits
    suspicious = not (_MIN_DIGITS <= len(digits) <= _MAX_DIGITS)
    # Without an explicit prefix the digits cannot be placed in any country,
    # so no E.164 form is claimed.
    e164 = ("+" + digits) if has_plus and not suspicious else None
    return NormalizedPhone(display=display, e164=e164, has_country_code=has_plus, suspicious=suspicious)


def canonical_for_matching(raw: object) -> str | None:
    """Comparison key for duplicate detection.

    Uses the E.164 form when a country code is present, otherwise the bare
    digits — two differently-formatted writings of one number still match,
    while a local number never collides with an international one.
    """
    parsed = normalize_phone(raw)
    if parsed is None:
        return None
    return parsed.e164 or parsed.display
