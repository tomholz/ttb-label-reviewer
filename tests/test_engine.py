"""Aggregation per the outcome model: worst-of verdict, counts, and
not_applicable excluded from aggregation but reported."""

from helpers import field, finding, make_application, make_extraction

from ttb_label_reviewer.engine import Outcome, review


def test_compliant_label_set_passes():
    result = review(make_application(), make_extraction())
    assert result.verdict is Outcome.PASS
    assert result.counts.fail == 0
    assert result.counts.needs_review == 0
    assert result.counts.pass_ == 10
    assert result.counts.not_applicable == 1  # DS-7, not imported
    assert len(result.findings) == 11


def test_verdict_is_worst_finding():
    # One fail (brand mismatch) + one needs_review (proof inconsistency):
    # fail wins.
    ext = make_extraction(
        brand_name=field("RIVERBEND RESERVE"), proof=field("86 Proof")
    )
    result = review(make_application(), ext)
    assert result.verdict is Outcome.FAIL
    assert result.counts.fail == 1
    assert result.counts.needs_review == 1


def test_needs_review_outranks_pass():
    ext = make_extraction(proof=field("86 Proof"))
    result = review(make_application(), ext)
    assert result.verdict is Outcome.NEEDS_REVIEW


def test_not_applicable_excluded_from_aggregation():
    # All-pass with two n/a rules must still aggregate to pass.
    ext = make_extraction(proof=None)
    result = review(make_application(), ext)
    assert result.counts.not_applicable == 2  # DS-7 and DS-8
    assert result.verdict is Outcome.PASS


def test_counts_cover_all_rules():
    result = review(make_application(), make_extraction())
    total = (
        result.counts.fail
        + result.counts.needs_review
        + result.counts.pass_
        + result.counts.not_applicable
    )
    assert total == len(result.findings) == 11


def test_application_id_echoed():
    app = make_application(application_id="row-017")
    assert review(app, make_extraction()).application_id == "row-017"


def test_counts_serialize_with_pass_key():
    # contracts.md §4: the JSON key is "pass", not "pass_".
    result = review(make_application(), make_extraction())
    dumped = result.model_dump()
    assert dumped["counts"]["pass"] == 10
    assert "pass_" not in dumped["counts"]


def test_evaluated_findings_carry_evidence():
    # D-8: expected/actual appear on every evaluated finding, including
    # passes — a pass the agent can eyeball beats a green dot.
    result = review(make_application(), make_extraction())
    for f in result.findings:
        if f.outcome is not Outcome.NOT_APPLICABLE:
            assert f.expected is not None
            assert f.citation
            assert f.explanation


def test_reason_is_null_on_pass_and_not_applicable():
    result = review(make_application(), make_extraction())
    for f in result.findings:
        if f.outcome in (Outcome.PASS, Outcome.NOT_APPLICABLE):
            assert f.reason is None


def test_diff_only_on_ds5a():
    from helpers import WARNING_ON_LABEL, warning

    deviant = WARNING_ON_LABEL.replace("birth defects", "fetal harm")
    ext = make_extraction(
        brand_name=field("RIVERBEND RESERVE"),
        government_warning=warning(raw_text=deviant),
    )
    result = review(make_application(), ext)
    assert finding(result, "DS-5a").diff
    assert finding(result, "DS-1").diff is None
