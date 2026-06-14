# Documentation

Start with the root [README](../README.md) — it covers what the prototype
is, how to run it, the approach, and the trade-offs. This folder is the
depth behind it. Grouped for a reviewer below.

## Start here

- [project-description.md](project-description.md) — the original take-home
  assignment (stakeholder interviews, requirements, deliverables).
- [build-brief.md](build-brief.md) — how the work was scoped and sequenced
  from that assignment before any code was written.

## Design & decisions

- [decisions.md](decisions.md) — every design decision (D-1 … D-16) with
  the rationale to revisit it deliberately: the extract/decide split,
  canonical-text-out-of-prompt, the 5-second interpretation, the federal
  transition story, partial-coverage posture, and more.
- [design-review.md](design-review.md) — the build plan reviewed against the
  assignment: which stakeholder needs it meets, and the gaps/risks called
  out before implementation.

## Domain & contracts (reference)

- [ttb-requirements.md](ttb-requirements.md) — the curated, scoped TTB
  labeling rules with citations and the outcome model. **The single source
  of truth** for what each rule checks and what is deliberately out of
  scope, including the extraction-fidelity rationale.
- [contracts.md](contracts.md) — the four data shapes everything is built
  against (application record, extraction result, review result, and the
  golden-set manifest).

## Evaluation

- [evaluation.md](evaluation.md) — the golden-set scoreboard, the model
  choice that follows from it, and how the illegibility threshold was
  tuned (with its caveat).

## Research & planning (process artifacts)

How specific pieces were investigated and planned — useful for seeing the
reasoning, not required to understand the shipped system.

- [wine-malt-research-brief.md](wine-malt-research-brief.md) — the question:
  whether/how to add partial wine and malt review.
- [wine-malt-research-memo.md](wine-malt-research-memo.md) — the
  decision-ready answer (no code proposed in the spike).
- [wine-malt-implementation-plan.md](wine-malt-implementation-plan.md) — that
  memo turned into ordered, file-level work.
- [usability-restructure-plan.md](usability-restructure-plan.md) — a
  discoverability/usability pass (working plan).
- [single-result-label-preview-plan.md](single-result-label-preview-plan.md)
  — the UI-only label-preview enhancement plan.
