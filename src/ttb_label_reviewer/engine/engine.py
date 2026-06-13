"""Run every rule and aggregate per the outcome model: verdict is the
worst evaluated outcome (fail > needs_review > pass); not_applicable and
not_evaluated are reported for UI completeness but excluded from aggregation."""

from collections import Counter

from .rules import RULES_BY_TYPE
from .types import (
    ApplicationRecord,
    BeverageType,
    Counts,
    EngineConfig,
    ExtractionResult,
    Outcome,
    ReviewResult,
)

_SEVERITY = {Outcome.PASS: 0, Outcome.NEEDS_REVIEW: 1, Outcome.FAIL: 2}


def review(
    application: ApplicationRecord,
    extraction: ExtractionResult,
    config: EngineConfig | None = None,
) -> ReviewResult:
    config = config or EngineConfig()
    rules = RULES_BY_TYPE[application.beverage_type]
    findings = [rule(application, extraction, config) for rule in rules]
    tally = Counter(finding.outcome for finding in findings)
    verdict = Outcome.PASS
    for finding in findings:
        if finding.outcome in (Outcome.NOT_APPLICABLE, Outcome.NOT_EVALUATED):
            continue
        if _SEVERITY[finding.outcome] > _SEVERITY[verdict]:
            verdict = finding.outcome
    return ReviewResult(
        application_id=application.application_id,
        verdict=verdict,
        counts=Counts(
            fail=tally[Outcome.FAIL],
            needs_review=tally[Outcome.NEEDS_REVIEW],
            pass_=tally[Outcome.PASS],
            not_applicable=tally[Outcome.NOT_APPLICABLE],
            not_evaluated=tally[Outcome.NOT_EVALUATED],
        ),
        coverage=(
            "full"
            if application.beverage_type is BeverageType.DISTILLED_SPIRITS
            else "partial"
        ),
        findings=findings,
    )
