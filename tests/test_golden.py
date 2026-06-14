"""Golden-set integrity and eval-scoring tests. Deterministic and free:
the manifest must be internally consistent, and every expected outcome
must follow from the engine given a perfectly faithful extraction — so a
live eval mismatch can only mean extraction infidelity, which is the
thing the golden set exists to measure (D-6). No API calls here (D-5)."""

from pathlib import Path

import pytest
from helpers import make_application, make_extraction
from pydantic import ValidationError

from ttb_label_reviewer.engine import ExtractionResult, Outcome, Reason, review
from ttb_label_reviewer.evaluation import (
    ExpectedFinding,
    GoldenCase,
    GoldenManifest,
    StrictApplicationRecord,
    load_faithful_extractions,
    load_manifest,
    score_case,
)

GOLDEN_DIR = Path(__file__).parent.parent / "golden"

manifest = load_manifest(GOLDEN_DIR / "manifest.json")
faithful = load_faithful_extractions(GOLDEN_DIR / "faithful_extractions.json")
CASES = {case.case_id: case for case in manifest.cases}


# ---------------------------------------------------------------------------
# Manifest integrity
# ---------------------------------------------------------------------------
def test_manifest_version_present():
    assert manifest.version


def test_case_ids_unique():
    assert len(CASES) == len(manifest.cases)


def test_case_count_matches_brief():
    # ~15 cases per D-6; a sudden drop means cases were lost, not tuned.
    assert len(manifest.cases) >= 15


def test_referenced_images_exist():
    for case in manifest.cases:
        for name in case.application.image_filenames:
            assert (GOLDEN_DIR / name).is_file(), f"{case.case_id}: {name}"


def test_every_case_has_faithful_extraction():
    assert set(faithful) == set(CASES)


def test_required_probe_cases_present():
    # The build brief names these specifically; they are the point of the set.
    for case_id in (
        "warning-title-case",
        "warning-fetal-harm",
        "warning-dropped-2",
        "warning-hyphenated",
        "warning-back-label",
        "brand-case-variance",
        "degraded",
    ):
        assert case_id in CASES


def test_wine_malt_golden_cases_present():
    for case_id in (
        "wine-compliant-table",
        "wine-high-abv-missing-statement",
        "malt-compliant",
        "malt-abv-mismatch",
        "malt-abv-omitted",
    ):
        assert case_id in CASES

    assert CASES["wine-compliant-table"].expected["WN-SCOPE"].outcome is (
        Outcome.NOT_EVALUATED
    )


def test_multi_image_case_present():
    assert len(CASES["warning-back-label"].application.image_filenames) > 1


# ---------------------------------------------------------------------------
# Expected outcomes follow from the engine under faithful extraction
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("case_id", sorted(CASES))
def test_faithful_extraction_yields_expected_outcomes(case_id):
    case = CASES[case_id]
    extraction = ExtractionResult.model_validate(faithful[case_id])
    result = review(case.application, extraction)
    scores = score_case(case, result)
    failures = [
        f"{s.rule_id}: expected {s.expected_outcome}/{s.expected_reason}, "
        f"engine gave {s.actual_outcome}/{s.actual_reason}"
        for s in scores
        if not s.matched
    ]
    assert not failures, failures


# ---------------------------------------------------------------------------
# Scoring semantics (contracts.md §5)
# ---------------------------------------------------------------------------
def _case(expected: dict) -> GoldenCase:
    return GoldenCase(
        case_id="t",
        purpose="t",
        application=make_application().model_dump(),
        expected=expected,
    )


def test_omitted_rule_means_expected_pass():
    result = review(make_application(), make_extraction())
    scores = score_case(
        _case(
            {
                "DS-7": {"outcome": "not_applicable"},
                "DS-SCOPE": {"outcome": "not_evaluated"},
            }
        ),
        result,
    )
    by_id = {s.rule_id: s for s in scores}
    assert by_id["DS-1"].expected_outcome is Outcome.PASS
    assert all(s.matched for s in scores)


def test_outcome_mismatch_detected():
    result = review(make_application(), make_extraction(government_warning=None))
    scores = score_case(
        _case(
            {
                "DS-7": {"outcome": "not_applicable"},
                "DS-SCOPE": {"outcome": "not_evaluated"},
            }
        ),
        result,
    )
    by_id = {s.rule_id: s for s in scores}
    assert not by_id["DS-5a"].matched
    assert by_id["DS-5a"].actual_outcome is Outcome.FAIL
    assert by_id["DS-5a"].actual_reason is Reason.MISSING


def test_pinned_reason_must_match():
    # DS-5a fails with reason missing; the manifest pins mismatch.
    result = review(make_application(), make_extraction(government_warning=None))
    case = _case(
        {
            "DS-5a": {"outcome": "fail", "reason": "mismatch"},
            "DS-7": {"outcome": "not_applicable"},
        }
    )
    by_id = {s.rule_id: s for s in score_case(case, result)}
    assert not by_id["DS-5a"].matched


def test_unpinned_reason_matches_any():
    result = review(make_application(), make_extraction(government_warning=None))
    case = _case(
        {
            "DS-5a": {"outcome": "fail"},
            "DS-5b": {"outcome": "fail", "reason": "missing"},
            "DS-5c": {"outcome": "needs_review", "reason": "missing"},
            "DS-5d": {"outcome": "needs_review", "reason": "missing"},
            "DS-7": {"outcome": "not_applicable"},
            "DS-SCOPE": {"outcome": "not_evaluated"},
        }
    )
    assert all(s.matched for s in score_case(case, result))


def test_unknown_rule_id_raises():
    result = review(make_application(), make_extraction())
    with pytest.raises(ValueError, match="DS-99"):
        score_case(_case({"DS-99": {"outcome": "fail"}}), result)


def test_expected_finding_rejects_unknown_outcome():
    with pytest.raises(ValueError):
        ExpectedFinding(outcome="maybe")


# ---------------------------------------------------------------------------
# Manifest models reject unknown keys: a typo'd or renamed key must fail
# loudly at load time — omission semantics (omitted rule = pass, omitted
# reason = match-any) mean it would otherwise silently weaken what the
# golden set asserts, with the integrity tests staying green.
# ---------------------------------------------------------------------------
_APPLICATION = make_application().model_dump()


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        # The case nothing else catches: a typo'd `reason` would silently
        # unpin the reason check (None means "match any reason").
        (ExpectedFinding, {"outcome": "fail", "reaason": "mismatch"}),
        (StrictApplicationRecord, {**_APPLICATION, "importedd": True}),
        (
            GoldenCase,
            {
                "case_id": "t",
                "purpose": "t",
                "application": _APPLICATION,
                "expectedd": {},
            },
        ),
        (GoldenManifest, {"version": "1", "cases": [], "notes": "x"}),
    ],
)
def test_manifest_models_reject_unknown_keys(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)
