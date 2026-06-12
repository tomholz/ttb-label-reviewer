# Build Brief

Handoff from the design session to the build session. Read these, in
this order, before writing code:

1. [project-description.md](project-description.md) — the original
   brief and stakeholder interviews (the requirements between the lines)
2. [ttb-requirements.md](ttb-requirements.md) — the rules (DS-1–DS-8),
   outcome model, extraction-fidelity constraints. Source of truth.
3. [contracts.md](contracts.md) — the five data shapes. Frozen; changes
   are deliberate contract changes, not incidental ones.
4. [decisions.md](decisions.md) — D-1–D-11: architecture, stack, cut
   order, federal transition story.

**Stack (D-11):** Python end to end. FastAPI + HTMX (vendored, no CDN),
SSE for batch streaming, Pillow for golden-label rendering, Anthropic
API behind an adapter (D-10), single Docker container, deployed on
Fly.io. Use `uv` for dependency management.

**Standing constraints (do not relax):**

- The canonical warning text never appears in any model prompt (D-2).
- The model returns raw strings per contracts.md §3; all parsing and
  all verdicts happen in deterministic, tested code (D-1).
- `visual`-mode rules can never produce `fail`.
- No runtime outbound dependency except the model API (D-10.3).
- If time pressure hits, cut in D-9's order — don't improvise.

## Build order

Each milestone leaves the repo deployable and demoable; don't start the
next until the current one is.

1. **Skeleton + deploy (day one).** Repo layout, pyproject, FastAPI
   hello-world, Dockerfile, Fly deploy, CI (lint + tests). The URL
   exists from the first day so deployment is never a scramble.
2. **Rule engine, no API.** `Finding`/`ReviewResult` types from
   contracts.md §4; parsers (ABV statement, proof, net contents);
   DS-5a normalization exactly as specified; DS-1–DS-8 as pure
   functions over (application record, extraction result). CI tests
   from canned extraction JSON: every band boundary of DS-3 (45.0 /
   45.2 / 45.3 / 45.4), every reason code, the normalization table,
   not_applicable gating. This milestone is where most of the
   correctness lives and none of the cost.
3. **Extraction adapter.** Interface + Anthropic implementation
   (vision, structured output per contracts.md §3). Prompt obeys the
   standing constraints. Wire pipeline: images → extraction → engine →
   ReviewResult.
4. **Single review UI.** Application form + multi-image upload →
   results page: verdict, counts, per-rule findings with
   expected/actual evidence, character diff on DS-5a. This is the
   polished path (Sarah's mother test). Target ~5s end to end.
5. **Golden set + eval.** Promote `spikes/label-renderer/` into a
   `golden/` generator; ~15 cases per D-6 (near-miss warnings,
   title-case probe, dropped "(2)", hyphenated warning variant, a
   multi-image case with the warning on a back label, a degraded/
   skewed image, STONE'S THROW-style brand variance, ABV band cases,
   missing fields, an imported case). Manifest per contracts.md §5.
   Eval script + scoreboard per D-5 (model ID, prompt hash, manifest
   version). Tune the illegibility threshold here.
6. **Batch flow.** Zip+CSV upload per contracts.md §2, template
   download, SSE streaming results table sorted fail >
   needs_review > pass with counts, row-level errors inline.
7. **Second-pass verification (first to cut, D-9).** Targeted
   forced-choice re-check on DS-5a/5b diffs, per ttb-requirements.md
   Extraction fidelity §4.

## README must include

Setup/run, architecture sketch (extract → decide), and the assumptions
sections we committed to during design: the 5-seconds-means-
time-to-first-result interpretation (D-3), the extraction-fidelity /
hallucination risk and countermeasures (this is a feature of the
design, write it as one), the federal transition story (D-10), the
eval scoreboard with its three reproducibility fields, and known
limitations (out-of-scope list from ttb-requirements.md, including the
same-field-of-vision gap).

## Done means

Deployed URL serving single + batch review; CI green; eval scoreboard
committed with a current score; README per above. The brief's own
words: "a working core application with clean code is preferred over
ambitious but incomplete features."
