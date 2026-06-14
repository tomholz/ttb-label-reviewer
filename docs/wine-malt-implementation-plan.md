# Wine & Malt Beverage Expansion — Implementation Plan

Turns [wine-malt-research-memo.md](wine-malt-research-memo.md) into ordered,
file-level work. Rationale lives in the memo; this document is the *how* and
the *order*. Rules, citations, and outcome semantics are the memo's §§2–4;
do not re-derive them here.

> **Status:** Phase 1 is done and committed (collapsed to a summary below);
> Phase 2 (golden/demo/eval breadth) is the remaining, cuttable work.

**Decisions settled before planning (2026-06-13):**

- **D-a — Reuse, don't refactor.** Code inspection showed the shared logic
  largely already exists: `ds1`/`ds2` already delegate to
  `_fuzzy_consistency`; the warning family (`ds5a-d`) is already
  commodity-independent (Part 16 citations are byte-identical). Only net
  contents needs a body-extraction; alcohol content is purely additive. The
  176/176 golden set is the guardrail — any sharing change that regresses DS
  fails CI.
- **D-b — DS gets scope markers too.** DS's out-of-scope items
  (same-field-of-vision, type size) become a visible `DS-SCOPE`
  `not_evaluated` finding, matching wine/malt. The honesty story is symmetric
  across commodities. *Cost, accepted:* this changes the stable DS path's
  output — every DS result gains a finding; golden manifest, demo counts, and
  the demo "what you should see" copy all shift. Guarded by a dedicated step.
- **D-c — Per-commodity rule IDs.** Shared helpers take the `rule_id` as a
  parameter and emit `DS-1`/`WN-1`/`MB-1`, `DS-5a`/`WN-5a`/`MB-5a`, etc. The
  rule dimension and the commodity dimension stay separate; a wine label
  never shows a `DS-` id.
- **D-d — Both phases, P1 first.** P1 (engine + dispatch + UI + CI-
  deterministic goldens) ships standalone. P2 (rendered wine/malt imagery +
  live eval) is sequenced after and is cuttable per D-9.

---

## Phase 1 — engine, dispatch, UI — DONE

Shipped and committed on `main`; wine and malt are reviewable end-to-end
(single + batch + API), honestly scoped, fully CI-tested (257 passing), with
no new live-extraction dependency. Step-by-step detail lives in git; the
product decisions are recorded in `decisions.md` (D-12…D-16).

- **`fb08b9b`** — P1.1–4: outcome model (`not_evaluated`, `coverage`),
  `RULES_BY_TYPE` dispatch, shared helpers + WN-/MB- rule lists, `DS-SCOPE`
  marker (golden manifest → v2; README scoreboard noted 176→192).
- **`72b4db4`** — P1.5–7: `beverage_type` form/API field, batch accepts
  wine/malt, partial-coverage UI (badge, verdict relabel, `not_evaluated`
  rows, banner).
- **`7b9b243`** — P1.8: contracts, decisions (D-12…D-16), requirements
  (WN-/MB- promoted from stubs), README.
- **`6531893`** — UI polish: verdict-label dicts → Jinja globals; banner
  beverage word passed in, not inferred from rule-ID prefixes.

Two fixes the review surfaced, now in the tree:

- **WN-3/MB-3 share DS-3's `% alcohol by volume` form check** — it was
  dropped in the refactor, so a bare matching number passed where DS would
  route to `needs_review`/`format`. Now consistent across all three.
- **WN-3 lawful table-wine omission renders a pass with no `expected`/
  `actual`** — a presence/lawful-absence finding, not a value comparison, so
  it no longer reads as a miss that somehow passed.

---

## Phase 2 — golden / demo / eval breadth (cuttable)

### P2.1 — Deterministic golden cases (no imagery) — DONE

- **`golden/faithful_extractions.json` + `manifest.json`:** add memo §8 cases
  1–7 as hand-written faithful extractions (engine-and-dispatch coverage).
  Cases 4, 5, 6 are CI-only; bump `MANIFEST_VERSION`.

### P2.2 — Rendered wine/malt imagery — DONE

- **`golden/generate.py`:** extend the renderer beyond the bourbon shape to
  produce the live-eval cases (memo §8 cases 1–3: `wine-compliant-table`,
  `wine-high-abv-missing-statement`, `malt-compliant`). This is the real-work
  item and the first cut if time-boxed.

### P2.3 — Mixed-category demo batch — DONE

- **`golden/build_demo.py`:** assemble the mixed DS+wine+malt+unknown demo
  batch (memo §8 case 7); update demo copy and counts;
  `tests/test_demo.py` enforces rebuild.

### P2.4 — Live eval + scoreboard — DONE

- Ran the live eval on the current v3 manifest, including the rendered
  wine/malt images, and appended the README scoreboard row:
  `247/247 (100.0%)`, `21/21`, `claude-opus-4-8`, prompt
  `6886dc45365a`, manifest `2176b10ba2e4`.
- The warning-fidelity probes are unchanged (identical canonical string
  across commodities), so the fidelity claim transfers without duplicating
  probes per commodity; README states this explicitly.

---

## Cut order within this expansion (mirrors D-9)

If time-boxed, cut from the bottom of P2 up: P2.4 live eval → P2.3 demo batch
→ P2.2 imagery (ship P1 + P2.1 CI-only wine/malt with honest scope markers).
**Never cut:** the `not_evaluated` outcome + scope-marker rules (the honesty
mechanism), per-category dispatch, and the partial-coverage badge — without
those, partial coverage becomes the silent-omission failure the brief forbids.

## Test strategy summary

- Every rule decision is exercised by a deterministic engine test (no API),
  consistent with D-5; the live eval only proves extraction reads non-bourbon
  imagery.
- The DS golden set was the regression guardrail through the engine refactor;
  the `DS-SCOPE` step deliberately and visibly changed DS output (new scope
  rows, golden manifest → v2) in one commit. The same discipline applies to
  P2: any manifest change ships with its `MANIFEST_VERSION` bump.
- No API calls in CI; the golden integrity test continues to prove every
  expected outcome follows from the engine given faithful extraction.
