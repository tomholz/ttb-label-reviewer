"""Golden-set eval harness: manifest loading and scoring.

This module is pure and CI-tested; the live-API runner lives in
__main__.py and is a deliberate script, never a CI gate (D-5). Scoring
semantics follow contracts.md §5: a rule omitted from a case's
`expected` map is expected to pass; non-pass and not_applicable must be
explicit.
"""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..engine import ApplicationRecord, Outcome, Reason, ReviewResult

# The manifest models forbid unknown keys: omitted rules mean "expected
# pass" and an omitted `reason` means "match any reason", so a typo'd or
# renamed key would not error — it would silently weaken what the golden
# set asserts, and the integrity tests would stay green.


class StrictApplicationRecord(ApplicationRecord):
    """§1 record, but rejecting unknown keys. The strictness lives here
    rather than on the engine type: tightening the API-facing contract
    shape is a §1 contract decision, while the manifest is load-bearing
    ground truth where a dropped typo must fail loudly."""

    model_config = ConfigDict(extra="forbid")


class ExpectedFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    reason: Reason | None = None


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    purpose: str
    application: StrictApplicationRecord
    expected: dict[str, ExpectedFinding] = Field(default_factory=dict)


class GoldenManifest(BaseModel):
    """contracts.md §5 — one JSON file at the golden-set root. §5 is a
    frozen contract, so a new manifest key requires a deliberate model
    change here, never an informal extra field."""

    model_config = ConfigDict(extra="forbid")

    version: str
    cases: list[GoldenCase]


class RuleScore(BaseModel):
    rule_id: str
    expected_outcome: Outcome
    expected_reason: Reason | None = None
    actual_outcome: Outcome
    actual_reason: Reason | None = None
    matched: bool


def load_manifest(path: Path) -> GoldenManifest:
    return GoldenManifest.model_validate_json(path.read_text())


def manifest_sha256(path: Path) -> str:
    """Third reproducibility field of the scoreboard (D-5): a bare score
    is not a reproducible claim; (model ID, prompt hash, manifest
    version/hash) makes it one."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_faithful_extractions(path: Path) -> dict[str, dict]:
    """The generator's faithful-extraction fixture (not part of the §5
    contract): what a perfectly faithful read of each label set returns.
    Lets CI prove the manifest's expectations follow from the engine
    alone, and lets the runner attribute live mismatches to extraction
    infidelity."""
    return json.loads(path.read_text())


def score_case(case: GoldenCase, result: ReviewResult) -> list[RuleScore]:
    """Score one case: per-rule outcome match, plus reason match where the
    manifest pins a reason."""
    finding_ids = {finding.rule_id for finding in result.findings}
    unknown = sorted(set(case.expected) - finding_ids)
    if unknown:
        raise ValueError(
            f"case {case.case_id!r} expects outcomes for rules the engine "
            f"does not report: {unknown}"
        )
    scores = []
    for finding in result.findings:
        expected = case.expected.get(
            finding.rule_id, ExpectedFinding(outcome=Outcome.PASS)
        )
        matched = finding.outcome is expected.outcome and (
            expected.reason is None or finding.reason is expected.reason
        )
        scores.append(
            RuleScore(
                rule_id=finding.rule_id,
                expected_outcome=expected.outcome,
                expected_reason=expected.reason,
                actual_outcome=finding.outcome,
                actual_reason=finding.reason,
                matched=matched,
            )
        )
    return scores
