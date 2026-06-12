"""Character-level diff for DS-5a evidence (contracts.md §4)."""

import difflib

from .types import DiffSpan


def char_diff(expected: str, actual: str) -> list[DiffSpan]:
    """Spans covering both strings end to end; comparison is
    case-insensitive (DS-5a semantics) but spans carry the original
    casing for display."""
    matcher = difflib.SequenceMatcher(
        a=expected.lower(), b=actual.lower(), autojunk=False
    )
    return [
        DiffSpan(op=op, expected=expected[i1:i2], actual=actual[j1:j2])
        for op, i1, i2, j1, j2 in matcher.get_opcodes()
    ]
