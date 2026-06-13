# Design Decisions

Project-management and design decisions that are *choices*, not domain
truth. Domain truth (rules, citations, outcome model) lives in
[ttb-requirements.md](ttb-requirements.md). Each entry records the
decision and enough rationale to revisit it deliberately rather than
re-litigate it accidentally.

## D-1 — The AI extracts, the code decides

A vision model converts label images into structured fields (a defined
JSON contract); a deterministic rule engine applies every rule in
ttb-requirements.md. The nondeterministic component is confined to
extraction. Consequences: every rule is unit-testable without an API
call, every verdict is explainable ("character 47 differs"), and the
model is never asked to *judge* compliance — only to *read*.

## D-2 — Canonical warning text lives only in the rule engine

Hard constraint (rationale in ttb-requirements.md → Extraction
fidelity): the canonical government warning never appears in the
extraction prompt. Recorded here too because it is a standing constraint
on all future prompt changes, not a one-time implementation detail.

## D-3 — "5 seconds" means time-to-first-result

The stakeholder constraint ("results back in about 5 seconds or nobody
uses it") is interpreted as: a single-label review completes in ~5s, and
a batch begins streaming per-label results immediately with parallel
processing — not "300 labels in 5 seconds." This interpretation is
inferred, not stated in the brief; it is documented in the README as an
assumption.

## D-4 — Batch input contract: zip of images + CSV manifest

- One CSV row per application; columns are the application fields plus
  `image_filenames` (delimiter-separated, **plural**, order-irrelevant,
  untagged — no front/back designation required).
- Multi-image-per-application is in the contract from day one because
  27 CFR 16.21 anticipates the warning on a back/side label; retrofitting
  it later would break the manifest format.
- The UI offers a downloadable CSV template.
- The single-review form (one application, one-or-more images) is the
  primary, polished path; batch is the same pipeline with a loop and a
  streaming results table sorted worst-first (fail > needs_review >
  pass), with per-label counts for triage.

## D-5 — CI tests vs. model evals are separate layers

- **Rule-engine tests** (canned extraction JSON → expected per-rule
  outcomes): deterministic, free, exhaustive over band boundaries. Run
  in CI, block merges.
- **Extraction evals** (golden label images → live vision model): slow,
  cost money, not perfectly deterministic. Run as a deliberate script
  with a committed scoreboard recording model ID, extraction-prompt
  hash, and golden-set hash/version. **Not** a blocking CI gate — a
  flaky gate trains people to ignore it.

## D-6 — Golden set is load-bearing, not demo garnish

~15 AI-generated labels with deliberate, known defects and a manifest of
expected per-rule outcomes. Must include near-miss warnings (one word
changed, "birth defects" → "fetal harm", dropped "(2)") and the
title-case "Government Warning" lead-in — these exist specifically to
measure extraction autocomplete-toward-canonical, which no other
mechanism can measure. Doubles as demo material.

## D-7 — Second-pass verification is a booster, not a defense layer

Targeted forced-choice re-check on detected warning diffs. Limits
recorded in ttb-requirements.md → Extraction fidelity: correlated
evidence (same model, same priors), never promoted into the first pass,
runs only on already-discrepant labels.

## D-8 — Decision-support, not decision-making

The agent stays the authority; the tool makes the routine majority
instant and surfaces evidence for the judgment cases. UI expression:
**evidence is the interface** — every finding shows extracted label
value vs. application value side by side; the warning check shows a
character-level diff. Outcomes route to `needs_review` rather than
guessing whenever the call requires judgment or the image is illegible.

## D-9 — Pre-agreed cut order

This is a time-boxed prototype whose brief explicitly rewards a complete
core over ambitious sprawl. If time pressure hits, cut in this order —
decided now, not under duress:

1. Second-pass verification (booster, not load-bearer)
2. Character-level diff UI (plain side-by-side evidence still works)
3. Batch streaming polish (sequential with a progress bar is acceptable)
4. Eval automation (run the goldens manually, report the score)

**Never cut:** rule-engine tests, the golden set itself, the multi-image
manifest contract, the canonical-text-out-of-prompt constraint. Cutting
features is cheap; cutting contracts is expensive — the contracts ship
regardless.

## D-10 — Cloud model API for the prototype, with a concrete federal transition story

The deliverable requires a deployed, publicly testable URL, so a cloud
vision-model API is acceptable for the prototype. But the stakeholder
constraints (firewall blocks outbound ML endpoints; FedRAMP'd Azure
shop) get a designed-in transition story, not just a README mention.
Three design rules, adopted from the first line of code:

1. **Model client is a swappable adapter.** One module owns the vision
   API; Anthropic API for the prototype, FedRAMP-authorized endpoint
   (Claude via AWS Bedrock GovCloud, or Azure OpenAI Government on
   TTB's own substrate) for production — a config change plus one
   adapter, not a rewrite.
2. **Single OCI container.** Fly.io deploys from a Dockerfile, so the
   deployable artifact is already portable — the same image runs on
   Azure Government, GovCloud ECS, or on-prem. Fly hosts the prototype
   URL; it is not load-bearing in the architecture.
3. **All static assets vendored — no CDN, no runtime outbound
   dependencies except the model API.** Derived directly from the
   firewall constraint that killed half the prior vendor's pilot.
4. **Stateless, ephemeral processing.** Uploads exist only for the
   duration of a review; nothing is retained. Keeps the PII /
   records-retention surface near zero for a future ATO conversation.

## D-11 — Stack: Python end to end (FastAPI + HTMX), deployed on Fly.io

One language across the rule engine, eval harness, golden-label
renderer (Pillow — spike-validated GO in spikes/label-renderer/),
Claude SDK, and web layer. Server-rendered UI with HTMX (single
vendored ~14KB file) and SSE for the streaming batch table; no SPA
build chain. This is also the more government-deployable shape per
D-10(3) — fewer moving parts, no CDN pull. Considered and rejected:
Next.js/Vercel (splits the project across two languages or forces a
TS renderer); FastAPI + React SPA (two build systems for a time-boxed
prototype).

## D-12 — Partial coverage is a first-class result posture

Wine and malt beverage review is shipped as partial coverage, not as a
quiet subset of full compliance. Every result carries a coverage value:
`full` for distilled spirits, `partial` for wine and malt beverages. The
UI renders this as a persistent badge and partial-coverage notice, and
the API returns the same signal. The reason is product safety: a reviewer
must never mistake "no issue found in checked rules" for "fully compliant
wine/malt label."

## D-13 — `not_evaluated` is distinct from `not_applicable`

`not_applicable` means a rule does not apply to the label in front of the
tool; `not_evaluated` means the rule family applies to the commodity, but
this prototype does not perform that check. Both are aggregation-neutral,
but they are counted and rendered separately. This keeps scope limits in
the same evidence channel as other findings instead of burying them in a
README.

## D-14 — Wine and malt add no extraction fields

Wine and malt beverage support is an engine and UX expansion over the
existing raw-string extraction contract. Brand, class/type, alcohol
content, net contents, name/address, country of origin, and government
warning already cover the defensible partial scope. Adding legal-conclusion
fields such as "is this a low-alcohol product?" would weaken D-1 by asking
the model to judge rather than transcribe.

## D-15 — Rule lists are per commodity, helpers are shared

The engine dispatches through per-beverage rule lists so rule IDs stay
commodity-specific (`DS-`, `WN-`, `MB-`) while the implementation reuses
shared helpers for common checks. Alcohol content remains category-specific:
distilled spirits use the DS banding posture, wine uses the 14% threshold
and ±1.5/±1.0 percentage-point bands, and malt beverages use the ±0.3
percentage-point band with optional omission behavior.

## D-16 — Distilled spirits gets a scope marker too

The wine/malt expansion made scope honesty visible through
`WN-SCOPE`/`MB-SCOPE`. Distilled spirits uses the same mechanism via
`DS-SCOPE` for same-field-of-vision, type-size, and standards-of-fill
checks. This intentionally changes the stable DS output by adding one
`not_evaluated` finding per review, but it makes the honesty story
symmetric across commodities and avoids implying the DS path checks rules
it does not.
