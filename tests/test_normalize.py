"""The DS-5a normalization table from docs/ttb-requirements.md: collapse
whitespace runs and line breaks, rejoin end-of-line hyphenation, normalize
curly vs. straight apostrophes and quotes."""

import pytest

from ttb_label_reviewer.engine.normalize import normalize_fuzzy, normalize_warning


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # collapse whitespace runs
        ("GOVERNMENT  WARNING:   text", "GOVERNMENT WARNING: text"),
        # collapse line breaks
        ("women\nshould not drink", "women should not drink"),
        ("women \n should not drink", "women should not drink"),
        # rejoin end-of-line hyphenation
        ("during preg-\nnancy because", "during pregnancy because"),
        ("during preg- \n nancy because", "during pregnancy because"),
        # in-line hyphens are kept — only end-of-line hyphenation rejoins
        ("a well-known brand", "a well-known brand"),
        # curly → straight apostrophes and quotes
        ("women’s health", "women's health"),
        ("“warning”", '"warning"'),
        # leading/trailing whitespace stripped
        ("  text  ", "text"),
        # combined
        (
            "risk of birth de-\nfects. (2)  Consumption",
            "risk of birth defects. (2) Consumption",
        ),
    ],
)
def test_normalize_warning(text, expected):
    assert normalize_warning(text) == expected


def test_normalize_warning_preserves_case():
    # Case is the comparison's concern (DS-5a case-insensitive, DS-5b
    # case-sensitive), so normalization must not touch it.
    assert normalize_warning("Government Warning:") == "Government Warning:"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("STONE'S THROW", "Stone's Throw"),
        ("STONE’S THROW", "Stone's Throw"),  # curly apostrophe
        ("Stone's Throw", "Stones Throw"),
        ("OLD  TOM", "old tom"),
    ],
)
def test_normalize_fuzzy_equates(a, b):
    assert normalize_fuzzy(a) == normalize_fuzzy(b)


def test_normalize_fuzzy_distinguishes_different_names():
    assert normalize_fuzzy("OLD TOM DISTILLERY") != normalize_fuzzy(
        "STONE'S THROW DISTILLERY"
    )
