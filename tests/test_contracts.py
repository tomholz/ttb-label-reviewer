"""The literal example JSON from contracts.md §3 must validate against the
engine's ExtractionResult type — proving the engine consumes exactly what
the contract says the model returns."""

# ruff: noqa: E501 — the contract JSON is quoted verbatim, not wrapped

from helpers import make_application

from ttb_label_reviewer.engine import ExtractionResult, Outcome, review

CONTRACT_EXAMPLE_JSON = """\
{
  "brand_name":      { "raw": "OLD TOM DISTILLERY", "confidence": 0.98 },
  "class_type":      { "raw": "Kentucky Straight Bourbon Whiskey", "confidence": 0.97 },
  "alcohol_content": { "raw": "45% Alc./Vol.", "confidence": 0.99 },
  "proof":           { "raw": "90 Proof", "confidence": 0.99 },
  "net_contents":    { "raw": "750 mL", "confidence": 0.99 },
  "name_address":    { "raw": "Bottled by Old Tom Distillery, Bardstown, KY", "confidence": 0.95 },
  "country_of_origin": null,
  "government_warning": {
    "raw_text": "GOVERNMENT WARNING: (1) According to the Surgeon\\nGeneral, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
    "lead_in_bold": "yes",
    "remainder_bold": "no",
    "separate_and_apart": "yes",
    "confidence": 0.93
  }
}
"""


def test_contract_example_validates_and_reviews():
    extraction = ExtractionResult.model_validate_json(CONTRACT_EXAMPLE_JSON)
    result = review(make_application(), extraction)
    assert result.verdict is Outcome.PASS
