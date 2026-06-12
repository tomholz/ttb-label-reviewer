"""Deterministic parsers for label statement strings. The extraction
contract (contracts.md §3) returns raw strings; these parsers — not the
model — produce the numbers the rules compare (D-1)."""

import re

_ABV = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_PROOF = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*proof\b", re.IGNORECASE)
_NET_CONTENTS = re.compile(
    r"(\d+(?:\.\d+)?)\s*(fl\.?\s*oz\.?|liters?|litres?|ml|cl|l)(?![a-z])",
    re.IGNORECASE,
)


def parse_abv_statement(text: str) -> float | None:
    """ "45% Alc./Vol." → 45.0; "45.0% alcohol by volume" → 45.0.
    The first percentage in the statement is the ABV; proof never
    carries a % sign, so "45% Alc./Vol. (90 Proof)" parses as 45.0."""
    match = _ABV.search(text)
    return float(match.group(1)) if match else None


def parse_proof(text: str) -> float | None:
    """ "90 Proof" → 90.0."""
    match = _PROOF.search(text)
    return float(match.group(1)) if match else None


def parse_net_contents(text: str) -> tuple[float, str] | None:
    """ "750 mL" → (750.0, "ml"); "750ML" → (750.0, "ml"); "1 L" →
    (1000.0, "ml"); "12 FL OZ" → (12.0, "floz"). Metric units normalize
    to milliliters; fluid ounces stay in their own system (no cross-system
    conversion — differing systems read as a mismatch for a human)."""
    match = _NET_CONTENTS.search(text)
    if match is None:
        return None
    value = float(match.group(1))
    unit = re.sub(r"[.\s]", "", match.group(2)).lower()
    if unit in ("l", "liter", "liters", "litre", "litres"):
        return (value * 1000, "ml")
    if unit == "cl":
        return (value * 10, "ml")
    if unit == "ml":
        return (value, "ml")
    return (value, "floz")
