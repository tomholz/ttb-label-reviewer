import pytest

from ttb_label_reviewer.engine.parsers import (
    parse_abv_statement,
    parse_net_contents,
    parse_proof,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("45% Alc./Vol.", 45.0),
        ("45.0% alcohol by volume", 45.0),
        ("ALC. 45% BY VOL.", 45.0),
        ("45% Alc./Vol. (90 Proof)", 45.0),
        ("40%", 40.0),
        ("Kentucky Straight Bourbon", None),
        ("90 Proof", None),  # proof never carries a % sign
    ],
)
def test_parse_abv_statement(text, expected):
    assert parse_abv_statement(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("90 Proof", 90.0),
        ("90 PROOF", 90.0),
        ("(90 proof)", 90.0),
        ("45% Alc./Vol. (90 Proof)", 90.0),
        ("86.4 Proof", 86.4),
        ("45% Alc./Vol.", None),
    ],
)
def test_parse_proof(text, expected):
    assert parse_proof(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("750 mL", (750.0, "ml")),
        ("750ML", (750.0, "ml")),
        ("750 ml", (750.0, "ml")),
        ("1 L", (1000.0, "ml")),
        ("1 Liter", (1000.0, "ml")),
        ("75 cl", (750.0, "ml")),
        ("12 FL OZ", (12.0, "floz")),
        ("12 fl. oz.", (12.0, "floz")),
        ("net contents unknown", None),
    ],
)
def test_parse_net_contents(text, expected):
    assert parse_net_contents(text) == expected
