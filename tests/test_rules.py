"""Per-rule outcome tests over canned extraction results: every DS-3 band
boundary, every reason code, missing/illegible routing, and the visual-mode
no-fail construction."""

import pytest
from helpers import field, finding, make_application, make_extraction, warning

from ttb_label_reviewer.engine import Outcome, Reason, review

# --- DS-1 / DS-2: fuzzy consistency -----------------------------------------


def test_ds1_exact_match_passes():
    result = review(make_application(), make_extraction())
    f = finding(result, "DS-1")
    assert f.outcome is Outcome.PASS
    assert f.reason is None
    assert f.expected == "OLD TOM DISTILLERY"
    assert f.actual == "OLD TOM DISTILLERY"


def test_ds1_case_punctuation_variance_needs_review():
    # Dave's example: STONE'S THROW on the label, Stone's Throw in the
    # application — obviously the same thing, but a human call.
    app = make_application(brand_name="Stone's Throw")
    ext = make_extraction(brand_name=field("STONE'S THROW"))
    f = finding(review(app, ext), "DS-1")
    assert f.outcome is Outcome.NEEDS_REVIEW
    assert f.reason is Reason.MISMATCH


def test_ds1_different_name_fails():
    ext = make_extraction(brand_name=field("RIVERBEND RESERVE"))
    f = finding(review(make_application(), ext), "DS-1")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISMATCH


def test_ds1_missing_fails():
    ext = make_extraction(brand_name=None)
    f = finding(review(make_application(), ext), "DS-1")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISSING


def test_ds1_low_confidence_needs_review_even_when_text_matches():
    # Illegibility never produces fail and never a silent pass.
    ext = make_extraction(brand_name=field("OLD TOM DISTILLERY", confidence=0.2))
    f = finding(review(make_application(), ext), "DS-1")
    assert f.outcome is Outcome.NEEDS_REVIEW
    assert f.reason is Reason.ILLEGIBLE


def test_ds2_class_type_mismatch_fails():
    ext = make_extraction(class_type=field("Straight Rye Whiskey"))
    f = finding(review(make_application(), ext), "DS-2")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISMATCH


# --- DS-3: every band boundary ----------------------------------------------


@pytest.mark.parametrize(
    ("label_abv", "outcome"),
    [
        ("45% Alc./Vol.", Outcome.PASS),
        ("45.0% Alc./Vol.", Outcome.PASS),  # numeric, not string, comparison
        ("45.2% Alc./Vol.", Outcome.NEEDS_REVIEW),
        ("45.3% Alc./Vol.", Outcome.NEEDS_REVIEW),  # boundary: ≤ 0.3 pp
        ("45.4% Alc./Vol.", Outcome.FAIL),  # boundary: > 0.3 pp
        ("44.7% Alc./Vol.", Outcome.NEEDS_REVIEW),  # band is symmetric
        ("44.6% Alc./Vol.", Outcome.FAIL),
    ],
)
def test_ds3_bands(label_abv, outcome):
    ext = make_extraction(alcohol_content=field(label_abv), proof=None)
    f = finding(review(make_application(abv_percent=45.0), ext), "DS-3")
    assert f.outcome is outcome
    assert f.reason is (None if outcome is Outcome.PASS else Reason.MISMATCH)


def test_ds3_missing_fails():
    ext = make_extraction(alcohol_content=None, proof=None)
    f = finding(review(make_application(), ext), "DS-3")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISSING


def test_ds3_unparseable_statement_needs_review():
    ext = make_extraction(alcohol_content=field("forty-five percent"), proof=None)
    f = finding(review(make_application(), ext), "DS-3")
    assert f.outcome is Outcome.NEEDS_REVIEW
    assert f.reason is Reason.ILLEGIBLE


@pytest.mark.parametrize("statement", ["45%", "45% ABV"])
def test_ds3_matching_number_without_abv_form_needs_review(statement):
    # Required form is "__% alcohol by volume" (or permitted
    # abbreviations); a matching bare percentage routes to review, not
    # pass — and not fail, since the missing words may be extraction
    # truncation.
    ext = make_extraction(alcohol_content=field(statement), proof=None)
    f = finding(review(make_application(abv_percent=45.0), ext), "DS-3")
    assert f.outcome is Outcome.NEEDS_REVIEW
    assert f.reason is Reason.FORMAT


@pytest.mark.parametrize(
    "statement",
    ["45% Alc./Vol.", "ALC. 45% BY VOL.", "45% alcohol by volume"],
)
def test_ds3_permitted_abv_forms_pass(statement):
    ext = make_extraction(alcohol_content=field(statement), proof=None)
    f = finding(review(make_application(abv_percent=45.0), ext), "DS-3")
    assert f.outcome is Outcome.PASS


def test_ds3_band_mismatch_outranks_form_problem():
    # A bare percentage that is also numerically off fails on the
    # mismatch; the form question is moot at that point.
    ext = make_extraction(alcohol_content=field("45.4%"), proof=None)
    f = finding(review(make_application(abv_percent=45.0), ext), "DS-3")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISMATCH


# --- DS-4: net contents -----------------------------------------------------


@pytest.mark.parametrize("label_net", ["750 mL", "750ML", "750 ml", "75 cl"])
def test_ds4_unit_normalization_passes(label_net):
    ext = make_extraction(net_contents=field(label_net))
    f = finding(review(make_application(net_contents="750 mL"), ext), "DS-4")
    assert f.outcome is Outcome.PASS


def test_ds4_value_mismatch_fails():
    ext = make_extraction(net_contents=field("700 mL"))
    f = finding(review(make_application(net_contents="750 mL"), ext), "DS-4")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISMATCH


def test_ds4_missing_never_fails():
    # Net contents may be blown/embossed/molded into the container
    # (5.63(b)(2)) — invisible to a label-image-only review.
    ext = make_extraction(net_contents=None)
    f = finding(review(make_application(), ext), "DS-4")
    assert f.outcome is Outcome.NEEDS_REVIEW
    assert f.reason is Reason.MISSING


def test_ds4_unparseable_but_identical_passes():
    app = make_application(net_contents="one imperial pint")
    ext = make_extraction(net_contents=field("One Imperial Pint"))
    f = finding(review(app, ext), "DS-4")
    assert f.outcome is Outcome.PASS


def test_ds4_unparseable_and_different_needs_review():
    app = make_application(net_contents="one imperial pint")
    ext = make_extraction(net_contents=field("one quart"))
    f = finding(review(app, ext), "DS-4")
    assert f.outcome is Outcome.NEEDS_REVIEW
    assert f.reason is Reason.MISMATCH


# --- Wine/malt shared rules and alcohol branches ----------------------------


def test_wine_rules_are_registered_with_partial_coverage():
    app = make_application(
        beverage_type="wine",
        class_type="Table Wine",
        abv_percent=12.0,
        imported=False,
    )
    ext = make_extraction(
        class_type=field("Table Wine"),
        alcohol_content=None,
        proof=None,
    )
    result = review(app, ext)
    assert result.coverage == "partial"
    assert [f.rule_id for f in result.findings] == [
        "WN-1",
        "WN-2",
        "WN-3",
        "WN-4",
        "WN-5a",
        "WN-5b",
        "WN-5c",
        "WN-5d",
        "WN-6",
        "WN-7",
        "WN-SCOPE",
    ]
    assert finding(result, "WN-3").outcome is Outcome.PASS
    assert finding(result, "WN-SCOPE").outcome is Outcome.NOT_EVALUATED


def test_wn3_lawful_table_wine_omission_has_no_value_evidence():
    app = make_application(
        beverage_type="wine",
        class_type="Table Wine",
        abv_percent=12.0,
    )
    ext = make_extraction(
        class_type=field("Table Wine"),
        alcohol_content=None,
        proof=None,
    )
    f = finding(review(app, ext), "WN-3")
    assert f.outcome is Outcome.PASS
    assert f.expected is None
    assert f.actual is None


@pytest.mark.parametrize(
    ("app_abv", "class_type", "statement", "outcome", "reason"),
    [
        (14.1, "Red Wine", None, Outcome.FAIL, Reason.MISSING),
        (14.0, "Table Wine", None, Outcome.PASS, None),
        (14.0, "Light Wine", None, Outcome.PASS, None),
        (14.0, "Red Wine", None, Outcome.NEEDS_REVIEW, Reason.MISSING),
        (14.0, "Red Wine", "14% Alc./Vol.", Outcome.PASS, None),
        # Number matches but the prescribed wording is absent → needs_review/
        # format, same as DS-3 (4.36 requires the form just as 5.65(a) does).
        (14.0, "Red Wine", "14%", Outcome.NEEDS_REVIEW, Reason.FORMAT),
        (14.0, "Red Wine", "14% ABV", Outcome.NEEDS_REVIEW, Reason.FORMAT),
        (14.0, "Red Wine", "15.5% Alc./Vol.", Outcome.NEEDS_REVIEW, Reason.MISMATCH),
        (14.0, "Red Wine", "15.6% Alc./Vol.", Outcome.FAIL, Reason.MISMATCH),
        (14.1, "Red Wine", "15.1% Alc./Vol.", Outcome.NEEDS_REVIEW, Reason.MISMATCH),
        (14.1, "Red Wine", "15.2% Alc./Vol.", Outcome.FAIL, Reason.MISMATCH),
    ],
)
def test_wn3_alcohol_content_branches(app_abv, class_type, statement, outcome, reason):
    app = make_application(
        beverage_type="wine",
        class_type=class_type,
        abv_percent=app_abv,
    )
    ext = make_extraction(
        class_type=field(class_type),
        alcohol_content=None if statement is None else field(statement),
        proof=None,
    )
    f = finding(review(app, ext), "WN-3")
    assert f.outcome is outcome
    assert f.reason is reason


@pytest.mark.parametrize(
    ("statement", "outcome", "reason"),
    [
        (None, Outcome.NEEDS_REVIEW, Reason.MISSING),
        ("5.0% Alc./Vol.", Outcome.PASS, None),
        # Number matches but the prescribed 7.65(b) wording is absent.
        ("5.0%", Outcome.NEEDS_REVIEW, Reason.FORMAT),
        ("5.3% Alc./Vol.", Outcome.NEEDS_REVIEW, Reason.MISMATCH),
        ("5.4% Alc./Vol.", Outcome.FAIL, Reason.MISMATCH),
    ],
)
def test_mb3_alcohol_content_branches(statement, outcome, reason):
    app = make_application(
        beverage_type="malt_beverage",
        class_type="Lager",
        abv_percent=5.0,
    )
    ext = make_extraction(
        class_type=field("Lager"),
        alcohol_content=None if statement is None else field(statement),
        proof=None,
    )
    f = finding(review(app, ext), "MB-3")
    assert f.outcome is outcome
    assert f.reason is reason


def test_malt_scope_marker_is_aggregation_neutral():
    app = make_application(
        beverage_type="malt_beverage",
        class_type="Lager",
        abv_percent=5.0,
    )
    ext = make_extraction(
        class_type=field("Lager"),
        alcohol_content=field("5.0% Alc./Vol."),
        proof=None,
    )
    result = review(app, ext)
    assert result.coverage == "partial"
    assert finding(result, "MB-SCOPE").outcome is Outcome.NOT_EVALUATED
    assert result.counts.not_evaluated == 1
    assert result.verdict is Outcome.PASS


def test_distilled_spirits_scope_marker_is_aggregation_neutral():
    result = review(make_application(), make_extraction())
    assert result.coverage == "full"
    assert finding(result, "DS-SCOPE").outcome is Outcome.NOT_EVALUATED
    assert result.counts.not_evaluated == 1
    assert result.verdict is Outcome.PASS


# --- DS-5a: warning text verbatim -------------------------------------------


def test_ds5a_canonical_with_line_breaks_passes():
    f = finding(review(make_application(), make_extraction()), "DS-5a")
    assert f.outcome is Outcome.PASS


def test_ds5a_hyphenation_rejoined_passes():
    from helpers import WARNING_ON_LABEL

    hyphenated = WARNING_ON_LABEL.replace(
        "pregnancy because of\n", "preg-\nnancy because of "
    )
    ext = make_extraction(government_warning=warning(raw_text=hyphenated))
    f = finding(review(make_application(), ext), "DS-5a")
    assert f.outcome is Outcome.PASS


def test_ds5a_word_substitution_fails_with_diff():
    from helpers import WARNING_ON_LABEL

    deviant = WARNING_ON_LABEL.replace("birth defects", "fetal harm")
    ext = make_extraction(government_warning=warning(raw_text=deviant))
    f = finding(review(make_application(), ext), "DS-5a")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISMATCH
    # The diff spans tile both strings completely and flag a difference.
    assert f.diff
    assert "".join(s.expected for s in f.diff) == f.expected
    assert "".join(s.actual for s in f.diff) == f.actual
    assert any(s.op != "equal" for s in f.diff)


def test_ds5a_dropped_clause_number_fails():
    from helpers import WARNING_ON_LABEL

    deviant = WARNING_ON_LABEL.replace("(2) ", "")
    ext = make_extraction(government_warning=warning(raw_text=deviant))
    f = finding(review(make_application(), ext), "DS-5a")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISMATCH


def test_ds5a_missing_warning_fails():
    ext = make_extraction(government_warning=None)
    f = finding(review(make_application(), ext), "DS-5a")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISSING


def test_ds5a_low_confidence_needs_review():
    ext = make_extraction(government_warning=warning(confidence=0.3))
    f = finding(review(make_application(), ext), "DS-5a")
    assert f.outcome is Outcome.NEEDS_REVIEW
    assert f.reason is Reason.ILLEGIBLE


# --- DS-5b: lead-in capitalization (the title-case rejection) ----------------


def test_ds5b_capitals_pass():
    f = finding(review(make_application(), make_extraction()), "DS-5b")
    assert f.outcome is Outcome.PASS


def test_ds5b_title_case_fails_format_while_ds5a_passes():
    # Jenny's catch: "Government Warning" in title case — wording is
    # correct (DS-5a passes case-insensitively), capitalization is not.
    from helpers import WARNING_ON_LABEL

    title_case = WARNING_ON_LABEL.replace("GOVERNMENT WARNING:", "Government Warning:")
    ext = make_extraction(government_warning=warning(raw_text=title_case))
    result = review(make_application(), ext)
    assert finding(result, "DS-5a").outcome is Outcome.PASS
    f = finding(result, "DS-5b")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.FORMAT
    assert f.actual == "Government Warning"


def test_ds5b_lead_in_split_across_line_break_passes():
    from helpers import WARNING_ON_LABEL

    wrapped = WARNING_ON_LABEL.replace("GOVERNMENT WARNING:", "GOVERNMENT\nWARNING:")
    ext = make_extraction(government_warning=warning(raw_text=wrapped))
    f = finding(review(make_application(), ext), "DS-5b")
    assert f.outcome is Outcome.PASS


def test_ds5b_lead_in_absent_fails_missing():
    ext = make_extraction(government_warning=warning(raw_text="Drink responsibly."))
    f = finding(review(make_application(), ext), "DS-5b")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISSING


# --- DS-5c / DS-5d: visual mode can never fail -------------------------------


@pytest.mark.parametrize("lead_in_bold", ["yes", "no", "uncertain"])
@pytest.mark.parametrize("remainder_bold", ["yes", "no", "uncertain"])
def test_ds5c_never_fails(lead_in_bold, remainder_bold):
    ext = make_extraction(
        government_warning=warning(
            lead_in_bold=lead_in_bold, remainder_bold=remainder_bold
        )
    )
    f = finding(review(make_application(), ext), "DS-5c")
    assert f.outcome in (Outcome.PASS, Outcome.NEEDS_REVIEW)
    expected_pass = lead_in_bold == "yes" and remainder_bold == "no"
    assert (f.outcome is Outcome.PASS) == expected_pass


@pytest.mark.parametrize(
    ("separate_and_apart", "outcome", "reason"),
    [
        ("yes", Outcome.PASS, None),
        ("no", Outcome.NEEDS_REVIEW, Reason.FORMAT),
        ("uncertain", Outcome.NEEDS_REVIEW, Reason.ILLEGIBLE),
    ],
)
def test_ds5d_outcomes(separate_and_apart, outcome, reason):
    ext = make_extraction(
        government_warning=warning(separate_and_apart=separate_and_apart)
    )
    f = finding(review(make_application(), ext), "DS-5d")
    assert f.outcome is outcome
    assert f.reason is reason


def test_visual_rules_route_to_review_when_warning_missing():
    ext = make_extraction(government_warning=None)
    result = review(make_application(), ext)
    for rule_id in ("DS-5c", "DS-5d"):
        f = finding(result, rule_id)
        assert f.outcome is Outcome.NEEDS_REVIEW
        assert f.reason is Reason.MISSING


# --- DS-6: presence ----------------------------------------------------------


def test_ds6_present_passes():
    f = finding(review(make_application(), make_extraction()), "DS-6")
    assert f.outcome is Outcome.PASS


def test_ds6_missing_fails():
    ext = make_extraction(name_address=None)
    f = finding(review(make_application(), ext), "DS-6")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISSING


# --- DS-7: not_applicable gating on imported --------------------------------


def test_ds7_not_imported_is_not_applicable():
    f = finding(review(make_application(imported=False), make_extraction()), "DS-7")
    assert f.outcome is Outcome.NOT_APPLICABLE
    assert f.reason is None


def test_ds7_imported_present_passes():
    ext = make_extraction(country_of_origin=field("Product of Canada"))
    f = finding(review(make_application(imported=True), ext), "DS-7")
    assert f.outcome is Outcome.PASS


def test_ds7_imported_missing_fails():
    f = finding(review(make_application(imported=True), make_extraction()), "DS-7")
    assert f.outcome is Outcome.FAIL
    assert f.reason is Reason.MISSING


# --- DS-8: not_applicable gating on proof; never fails ------------------------


def test_ds8_no_proof_is_not_applicable():
    ext = make_extraction(proof=None)
    f = finding(review(make_application(), ext), "DS-8")
    assert f.outcome is Outcome.NOT_APPLICABLE
    assert f.reason is None


def test_ds8_consistent_proof_passes():
    f = finding(review(make_application(), make_extraction()), "DS-8")
    assert f.outcome is Outcome.PASS  # 90 proof ⇔ 45% ABV


def test_ds8_inconsistent_proof_needs_review_not_fail():
    ext = make_extraction(proof=field("86 Proof"))
    f = finding(review(make_application(), ext), "DS-8")
    assert f.outcome is Outcome.NEEDS_REVIEW
    assert f.reason is Reason.MISMATCH


def test_ds8_proof_without_abv_statement_needs_review():
    ext = make_extraction(alcohol_content=None)
    f = finding(review(make_application(), ext), "DS-8")
    assert f.outcome is Outcome.NEEDS_REVIEW
    assert f.reason is Reason.MISSING
