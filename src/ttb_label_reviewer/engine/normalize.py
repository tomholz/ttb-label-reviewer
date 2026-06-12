"""Text normalization. DS-5a's normalization is specified in
docs/ttb-requirements.md and applied to both sides before comparison;
fuzzy normalization serves the fuzzy match_mode rules (DS-1, DS-2, DS-4
fallback)."""

import re

_QUOTE_TRANSLATION = str.maketrans(
    {
        "‘": "'",  # left single curly quote
        "’": "'",  # right single curly quote / apostrophe
        "“": '"',  # left double curly quote
        "”": '"',  # right double curly quote
    }
)

_EOL_HYPHEN = re.compile(r"-\s*\n\s*")
_WHITESPACE_RUN = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s]")


def normalize_quotes(text: str) -> str:
    return text.translate(_QUOTE_TRANSLATION)


def normalize_warning(text: str) -> str:
    """DS-5a normalization, exactly as specified: normalize curly vs.
    straight apostrophes/quotes, rejoin end-of-line hyphenation, collapse
    whitespace runs and line breaks. Case handling is the comparison's
    job, not normalization's (lead-in case is DS-5b's check)."""
    text = normalize_quotes(text)
    text = _EOL_HYPHEN.sub("", text)
    text = _WHITESPACE_RUN.sub(" ", text)
    return text.strip()


def normalize_fuzzy(text: str) -> str:
    """Case/punctuation-insensitive form for fuzzy match_mode:
    STONE'S THROW ≡ Stone's Throw ≡ Stones Throw."""
    text = normalize_quotes(text).casefold()
    text = _PUNCTUATION.sub("", text)
    text = _WHITESPACE_RUN.sub(" ", text)
    return text.strip()
