# Wine & Malt Beverage Expansion — Implementation Plan

Turns [wine-malt-research-memo.md](wine-malt-research-memo.md) into ordered,
file-level work. Rationale lives in the memo; this document is the *how* and
the *order*. Rules, citations, and outcome semantics are the memo's §§2–4;
do not re-derive them here.

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

## Phase 1 — engine, dispatch, UI (the shippable core)

Ordered so each step leaves the tree green. Steps 1–4 are pure engine
(deterministic, no API); 5–7 are surface; 8 is docs.

### P1.1 — Outcome model: add `not_evaluated`

- **`engine/types.py`:** add `Outcome.NOT_EVALUATED = "not_evaluated"`;
  add `not_evaluated: int = 0` to `Counts`; add `coverage` to `ReviewResult`
  (`Literal["full", "partial"]`) per memo §5/§9.
- **`engine/engine.py`:** aggregation skips `NOT_EVALUATED` exactly as it
  skips `NOT_APPLICABLE` (the `_SEVERITY` map already omits both — verify the
  `continue` covers it); populate the new `Counts` field and `coverage`
  (derived from `application.beverage_type`).
- **Guardrail:** existing engine tests must stay green (additive enum value,
  no behavior change for DS yet — `coverage="full"`, no `not_evaluated` rows
  until P1.4). New unit tests assert aggregation-neutrality of
  `not_evaluated`.

### P1.2 — Beverage types + dispatch table

- **`engine/types.py`:** `BeverageType` gains `WINE = "wine"`,
  `MALT_BEVERAGE = "malt_beverage"`.
- **`engine/rules.py`:** replace `ALL_RULES` with
  `RULES_BY_TYPE: dict[BeverageType, list[RuleFn]]`. For this step DS keeps
  its current eight rules; wine/malt entries added in P1.3–P1.4.
- **`engine/engine.py`:** `review()` selects
  `RULES_BY_TYPE[application.beverage_type]`.
- **`engine/__init__.py`:** export `BeverageType` members already done; no
  change beyond re-exports if needed.
- **Guardrail:** DS path unchanged → 176/176 still holds.

### P1.3 — Shared helpers + wine/malt rule lists

Per D-a and D-c. Parameterize by `rule_id`/`citation`; reuse bodies.

- **Extract** `_net_contents_check(build, app_value, field, config)` from
  `ds4_net_contents` (the only working-code extraction); `ds4` becomes a thin
  wrapper, proving the helper is behavior-preserving against the golden set.
- **Reuse as-is:** `_fuzzy_consistency` (brand, class/type), the presence
  helper (name/address, origin), and the warning family `ds5a-d` — these take
  `rule_id`/`citation` args so the same body emits `WN-`/`MB-` findings.
- **New functions:**
  - `wn3_alcohol_content` — memo §3: `>14%` + missing → `fail/missing`;
    `≤14%` + qualifying designation + missing → `pass`; `≤14%` + no
    designation + missing → `needs_review`; present → band-compare
    (±1.5 pp ≤14%, ±1.0 pp >14%). Qualifying-designation detection =
    normalized-substring match for `"table wine"` / `"light wine"` in
    `class_type` (spec'd here so it isn't re-litigated in code review).
  - `mb3_alcohol_content` — memo §4: missing → `needs_review` (optional per
    7.65(a), never `fail`); present → band-compare (±0.3 pp).
- **Scope-marker rules** (always `not_evaluated`, memo §6): `WN_SCOPE`,
  `MB_SCOPE`, and `DS_SCOPE` (per D-b), each enumerating its commodity's
  out-of-scope items with plain-language reason + citation.
- **Build** `WINE_RULES` and `MALT_RULES`; register all three lists in
  `RULES_BY_TYPE`.
- **Guardrail:** new deterministic rule-engine tests over every band/branch
  boundary (wine >14 vs ≤14 × {present, missing, with/without designation};
  malt present/omitted/mismatch). No API calls.

### P1.4 — DS scope marker (the guarded DS-output change)

Isolated as its own step because it perturbs the stable path (D-b).

- Add `DS_SCOPE` to `DS_RULES`.
- **`golden/manifest.json`:** every DS case now expects one `not_evaluated`
  finding. Decide the manifest convention for `not_evaluated` (explicit, like
  non-pass — the "omitted = pass" shorthand can't cover it). Bump
  `MANIFEST_VERSION`.
- **`golden/faithful_extractions.json`:** unaffected (the scope rule ignores
  extraction), but the integrity test that "every expected outcome follows
  from the engine" must accept the new always-`not_evaluated` row.
- **Guardrail:** golden integrity test green; the live-eval score is
  unaffected (scope rule is extraction-independent), so the committed
  scoreboard's 176/176 becomes 176/176 + N scope rows — note the count change
  in the README table rather than re-running the eval.

### P1.5 — Single-review form + API

- **`main.py`:** add a beverage-type selector to the review form (default
  `distilled_spirits`); thread `beverage_type` into the `ApplicationRecord`
  instead of the hard-coded `DISTILLED_SPIRITS` at `main.py:141`. `/api/review`
  accepts the field; response carries `coverage`.
- **Guardrail:** existing API test (DS) green; add a wine and a malt request
  test against a stub extractor.

### P1.6 — UI: coverage badge, banners, `not_evaluated` rendering

- **`templates/partials/{results,findings,batch_row}.html`:** coverage badge
  (`Full coverage` / `Partial coverage`); wine/malt verdict relabel
  ("No issue found in checked rules" / "Needs agent review" / "Issue found"
  — presentation-only, memo §6); neutral-grey `not_evaluated` rows; banner
  notice copy from memo §6; beverage-type-control notice.
- **`static/style.css`:** badge + neutral row styles (vendored, no CDN).
- **Carried-over fix (from the P1.1–4 review):** WN-3's lawful-omission pass
  (table/light wine ≤14% with no ABV statement) currently carries a populated
  `expected` (`"12% alcohol by volume"`) with `actual=None`. Rendered as an
  evidence row this reads as a miss that somehow passed. This is a
  *presence/lawful-absence* finding, not a *value comparison* — so on that one
  branch set `expected=None`/`actual=None` and let the explanation carry it
  (do **not** stuff prose like "no statement required" into a value field).
  Deferred to here deliberately: the right shape is clearest once the evidence
  row renders alongside the others. Note the contrast with `needs_review`/
  `fail` branches, where a populated `expected` correctly helps the human
  investigate (as DS-4 missing-net-contents does).

### P1.7 — Batch parser

- **`batch.py`:** accept `wine`/`malt_beverage` (relax the
  `!= DISTILLED_SPIRITS` reject at `batch.py:215`); unknown types stay row
  errors listing the three accepted values; expand the template example rows
  (`batch.py:39`) to one per commodity. No new columns.
- **Guardrail:** new batch-parser tests for a wine row, a malt row, and an
  unknown-type row error.

### P1.8 — Docs (contracts move deliberately, per their own warning)

- **`ttb-requirements.md`:** promote the Part 4/Part 7 stubs into full WN-/MB-
  rule sections; add `not_evaluated` to the outcome model.
- **`contracts.md`:** add `wine`/`malt_beverage` to the `beverage_type` enum
  (§1); add `not_evaluated` + `coverage` to the review result (§4); note the
  manifest accepts the new types (§2).
- **`decisions.md`:** record D-12…D-16 (memo §9 plus D-b's DS-scope decision).
- **`README.md`:** scope line "distilled spirits only" → "distilled spirits
  (full) + wine/malt (partial)"; update known-limitations; update the demo
  "what you should see" counts.

**End of P1: wine and malt are reviewable end-to-end (single + batch + API),
honestly scoped, fully CI-tested, with no new live-extraction dependency.**

---

## Phase 2 — golden / demo / eval breadth (cuttable)

### P2.1 — Deterministic golden cases (no imagery)

- **`golden/faithful_extractions.json` + `manifest.json`:** add memo §8 cases
  1–7 as hand-written faithful extractions (engine-and-dispatch coverage).
  Cases 4, 5, 6 are CI-only; bump `MANIFEST_VERSION`.

### P2.2 — Rendered wine/malt imagery

- **`golden/generate.py`:** extend the renderer beyond the bourbon shape to
  produce the live-eval cases (memo §8 cases 1–3: `wine-compliant-table`,
  `wine-high-abv-missing-statement`, `malt-compliant`). This is the real-work
  item and the first cut if time-boxed.

### P2.3 — Mixed-category demo batch

- **`golden/build_demo.py`:** assemble the mixed DS+wine+malt+unknown demo
  batch (memo §8 case 7); update demo copy and counts;
  `tests/test_demo.py` enforces rebuild.

### P2.4 — Live eval + scoreboard

- Run the eval on the new wine/malt images; append a scoreboard row. The
  warning-fidelity probes are unchanged (identical canonical string across
  commodities), so the fidelity claim transfers without re-measuring — state
  this rather than duplicating probes per commodity.

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
- The 176/176 DS golden set is the regression guardrail through P1.1–P1.3; P1.4
  deliberately and visibly changes DS output (new scope rows) and updates the
  manifest in the same step.
- No API calls in CI; the golden integrity test continues to prove every
  expected outcome follows from the engine given faithful extraction.
