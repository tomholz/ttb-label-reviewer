"""Golden-set eval runner: live vision model -> rule engine -> score.

A deliberate script with a committed scoreboard, never a CI gate (D-5):

    uv run --env-file .env python -m ttb_label_reviewer.evaluation
    uv run --env-file .env python -m ttb_label_reviewer.evaluation \\
        --model claude-haiku-4-5-20251001 --threshold 0.5

Each run prints per-case results plus a ready-to-paste scoreboard row
carrying the three reproducibility fields (model ID, extraction-prompt
hash, manifest version/hash), and writes the full detail — including
per-field extraction confidences for illegibility-threshold tuning — to
golden/results/ (gitignored; the committed artifact is the scoreboard).

When a rule mismatches, the runner re-derives that case's outcomes from
the generator's faithful-extraction fixture: if the faithful outcome
matches the expectation, the live miss is attributed to extraction
infidelity (the measurement D-6 exists to take) rather than to the
engine or the manifest.
"""

import argparse
import datetime
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from ..engine import BeverageType, EngineConfig, ExtractionResult, Outcome, review
from ..engine.rules import RULES_BY_TYPE
from ..extraction import (
    DEFAULT_MODEL,
    AnthropicExtractor,
    ExtractionError,
    LabelImage,
    prompt_sha256,
)
from . import (
    GoldenCase,
    load_faithful_extractions,
    load_manifest,
    manifest_sha256,
    score_case,
)

GOLDEN_DIR = Path(__file__).parents[3] / "golden"

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def load_images(case: GoldenCase, golden_dir: Path) -> list[LabelImage]:
    return [
        LabelImage(
            filename=name,
            media_type=_MEDIA_TYPES[Path(name).suffix.lower()],
            data=(golden_dir / name).read_bytes(),
        )
        for name in case.application.image_filenames
    ]


def confidences(extraction: ExtractionResult) -> dict[str, float | None]:
    return {
        name: None if field is None else field.confidence for name, field in extraction
    }


def run_case(
    case: GoldenCase,
    golden_dir: Path,
    extractor: AnthropicExtractor,
    config: EngineConfig,
    faithful: dict[str, dict],
) -> dict:
    images = load_images(case, golden_dir)
    started = time.perf_counter()
    try:
        extraction = extractor.extract(images)
    except ExtractionError as exc:
        return {"case_id": case.case_id, "error": str(exc)}
    latency = time.perf_counter() - started

    result = review(case.application, extraction, config)
    scores = score_case(case, result)

    mismatches = []
    faithful_result = None
    for score in scores:
        if score.matched:
            continue
        if faithful_result is None and case.case_id in faithful:
            faithful_extraction = ExtractionResult.model_validate(
                faithful[case.case_id]
            )
            faithful_result = review(case.application, faithful_extraction, config)
        faithful_outcome = None
        if faithful_result is not None:
            faithful_outcome = next(
                f.outcome
                for f in faithful_result.findings
                if f.rule_id == score.rule_id
            )
        finding = next(f for f in result.findings if f.rule_id == score.rule_id)
        mismatches.append(
            {
                **score.model_dump(),
                "faithful_outcome": faithful_outcome,
                "extraction_attributed": faithful_outcome is not None
                and faithful_outcome is score.expected_outcome,
                "evidence": {"expected": finding.expected, "actual": finding.actual},
            }
        )

    return {
        "case_id": case.case_id,
        "latency_s": round(latency, 2),
        "matched": sum(s.matched for s in scores),
        "total": len(scores),
        "mismatches": mismatches,
        "confidences": confidences(extraction),
        "extraction": extraction.model_dump(mode="json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--manifest", type=Path, default=GOLDEN_DIR / "manifest.json")
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="override EngineConfig.illegibility_threshold",
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    golden_dir = args.manifest.parent
    manifest = load_manifest(args.manifest)
    manifest_hash = manifest_sha256(args.manifest)
    faithful_path = golden_dir / "faithful_extractions.json"
    faithful = (
        load_faithful_extractions(faithful_path) if faithful_path.exists() else {}
    )
    config = (
        EngineConfig(illegibility_threshold=args.threshold)
        if args.threshold is not None
        else EngineConfig()
    )
    # The adapter's no-silent-retry policy is right for the UI (a stuck
    # review must surface, D-3); an offline eval sweep should instead wait
    # out 429s, so its client gets a deep SDK retry budget (backoff honors
    # retry-after).
    extractor = AnthropicExtractor(
        model=args.model, client=anthropic.Anthropic(max_retries=8)
    )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        reports = list(
            pool.map(
                lambda case: run_case(case, golden_dir, extractor, config, faithful),
                manifest.cases,
            )
        )

    rule_total = rule_matched = cases_correct = 0
    latencies = []
    for report in reports:
        if "error" in report:
            # An errored case scores zero across the board rather than
            # vanishing from the denominator.
            rule_total += len(RULES_BY_TYPE[BeverageType.DISTILLED_SPIRITS])
            print(f"{report['case_id']:<28} ERROR  {report['error']}")
            continue
        rule_total += report["total"]
        rule_matched += report["matched"]
        cases_correct += not report["mismatches"]
        latencies.append(report["latency_s"])
        line = (
            f"{report['case_id']:<28} {report['matched']}/{report['total']}"
            f"  {report['latency_s']:.1f}s"
        )
        print(line)
        for miss in report["mismatches"]:
            attribution = (
                "extraction-attributed"
                if miss["extraction_attributed"]
                else "engine/manifest?"
            )
            print(
                f"    {miss['rule_id']}: expected "
                f"{_fmt(miss['expected_outcome'], miss['expected_reason'])}, got "
                f"{_fmt(miss['actual_outcome'], miss['actual_reason'])} "
                f"[{attribution}] actual={miss['evidence']['actual']!r}"
            )

    today = datetime.date.today().isoformat()
    mean_latency = sum(latencies) / len(latencies) if latencies else 0.0
    pct = 100 * rule_matched / rule_total if rule_total else 0.0

    print()
    print(f"rule outcomes matched: {rule_matched}/{rule_total} ({pct:.1f}%)")
    print(f"cases fully correct:   {cases_correct}/{len(manifest.cases)}")
    print(f"mean extraction latency: {mean_latency:.1f}s")
    print()
    print("scoreboard row:")
    print(
        f"| {today} | {args.model} | `{prompt_sha256()[:12]}` "
        f"| v{manifest.version} `{manifest_hash[:12]}` "
        f"| {rule_matched}/{rule_total} ({pct:.1f}%) "
        f"| {cases_correct}/{len(manifest.cases)} | {mean_latency:.1f} s |"
    )

    results_dir = golden_dir / "results"
    results_dir.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    out_path = results_dir / f"{stamp}-{args.model}.json"
    out_path.write_text(
        json.dumps(
            {
                "run": {
                    "date": today,
                    "model": args.model,
                    "prompt_sha256": prompt_sha256(),
                    "manifest_version": manifest.version,
                    "manifest_sha256": manifest_hash,
                    "illegibility_threshold": config.illegibility_threshold,
                    "rule_matched": rule_matched,
                    "rule_total": rule_total,
                    "cases_correct": cases_correct,
                    "case_count": len(manifest.cases),
                    "mean_latency_s": round(mean_latency, 2),
                },
                "cases": reports,
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    print(f"\nfull results: {out_path}")


def _fmt(outcome: Outcome | str, reason) -> str:
    text = outcome.value if isinstance(outcome, Outcome) else str(outcome)
    if reason:
        reason_text = getattr(reason, "value", str(reason))
        return f"{text}/{reason_text}"
    return text


if __name__ == "__main__":
    main()
