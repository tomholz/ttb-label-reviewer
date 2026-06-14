# Structure & usability: discoverability pass

> Working plan (not yet implemented). Captures the agreed direction so it can be
> picked up in a fresh session. Sequencing is **incremental**: build PR1 and PR2,
> then reassess before PR3/PR4.

## Context

The app now has a clean "modern federal" restyle, which makes its **structural**
weaknesses more visible. Today `index.html` is one long single-column scroll with
three stacked cards — single-review form, a sample-data card, and the batch form —
and `#results` renders inline *below* a tall form. Problems we agreed on:

1. Two workflows (single / batch) are interleaved, with the sample card wedged
   between them; the single-vs-batch choice is never surfaced.
2. After submit, the result swaps into a mid-page `#results` with no scroll or
   focus move — the payoff of the whole app is easy to miss.
3. Trying a sample is the worst-case chore: download an image, read its values,
   retype them, re-attach the file — all *before* a first result is seen.
4. The wine/malt partial-coverage caveat renders unconditionally, even for the
   default Distilled-spirits path.

**Decisions made** (via AskUserQuestion): server-side one-click sample runs;
segmented tabs for single/batch; **incremental** sequencing. This plan details the
first committed chunk — **PR1 (results take over)** and **PR2 (one-click samples)**
— which is where we reassess. PR3 (tabs) and PR4 (dynamic notice) are sketched only.

Guiding constraints from the codebase: vendored assets only, no CDN/external
requests (asserted in `test_ui.py::test_index_serves_the_form`); demo assets are
generated from the golden set by `golden/build_demo.py` and drift-tested
(`test_demo.py`) — never hand-edited.

---

## PR1 — Results take over on submit

**Goal:** when a single review (or an error) returns, bring the result to the top
of the viewport and move keyboard/screen-reader focus to it, with a clear heading
so the user knows what they're looking at. **Keep the form visible** (not collapsed)
so the common "tweak a field and re-run" loop stays one scroll away — collapsing
would force a reset click on every iteration.

**Changes**
- `templates/index.html`
  - On the `#results` section, add a settle handler so *any* swap into it (result
    or error fragment) scrolls its first child into view and focuses it:
    `hx-on::htmx:after-settle` → scroll first element child to `block:'start'` and
    `.focus()` it. (Handler is inert under TestClient; JS only runs in the browser.)
- `templates/partials/results.html`
  - Add a visible heading to `.results-card` (e.g. `<h2>Review result</h2>`) and
    make the card focusable: `tabindex="-1"` + `aria-labelledby` to the heading.
    Today the card jumps straight to the coverage badge with no orientation.
- `templates/partials/error.html`
  - Add `tabindex="-1"` to the `.error-card` (a `div.card.error-card[role=alert]`)
    so errors also take focus/scroll.
- `static/style.css`
  - Style the new results heading (serif, matches `.card h2`); subtle focus outline
    on `.results-card:focus`/`.error-card:focus` using `--accent-bright`. Optional
    light entrance (respect `prefers-reduced-motion`).

**Tests** (`tests/test_ui.py`)
- Existing substring assertions are unaffected (heading text is additive).
- Add: results fragment contains `tabindex="-1"` and the "Review result" heading;
  `#results` section carries the `hx-on::htmx:after-settle` hook.

---

## PR2 — One-click, server-side sample runs

**Goal:** a "Run this sample ▸" button next to each single sample that runs a *real*
review against the bundled image and renders the normal result into `#results`
(reusing PR1's scroll/focus). Zero typing, zero file attaching. Keep the existing
download link too (some users want the image); only the batch sample is unchanged.

**Why server-side:** browsers forbid JS from populating a file input, so true
one-click requires the server to use the bundled image. The images
(`static/demo/compliant.png`, `warning-title-case.png`, `warning-fetal-harm.png`)
and their golden-true values (`demo.json` `singles`) already ship.

**Changes**
- `src/ttb_label_reviewer/main.py`
  - New endpoint `POST /review/sample` (form field `sample` = the demo filename).
    Whitelist `sample` against `_demo_data()["singles"]` filenames → unknown ⇒
    `HTTPException(404)` (also blocks path traversal; never reads arbitrary files).
  - Build a `LabelImage` from the bundled bytes (`media_type="image/png"`) and an
    `ApplicationRecord` from the sample's values, then run the pipeline. **Reuse**
    by extracting a tiny helper from `_run_single_review` (the application-built →
    `review_label_set(...)` + `ExtractionError`→502 part) so both paths share it.
  - Uses `Depends(get_extractor)` like `/review` — same real model call (~5s, a few
    cents), same 503 when `ANTHROPIC_API_KEY` is unset. Not a new abuse surface
    beyond the already-open `/review`.
  - Render `partials/results.html` (same fragment, same `beverage_label`).
- `golden/build_demo.py` + regenerated `static/demo/demo.json`
  - Add `beverage_type` to each `singles` entry (sourced from the golden
    application) so the sample run is correct rather than hardcoded to spirits.
    Regenerate `demo.json` via the script (do **not** hand-edit) so drift tests pass.
- `templates/index.html`
  - In the sample-data card, render a `Run this sample ▸` button per single with
    `hx-post="/review/sample"`, `hx-vals` carrying the filename, `hx-target="#results"`,
    matching `hx-swap`, and `hx-indicator`/`hx-disabled-elt`. Keep the download link
    and the displayed values for transparency.

**Tests**
- `tests/test_ui.py`: `POST /review/sample` with the fake extractor + a known
  filename ⇒ 200 and a results fragment (verdict present); unknown filename ⇒ 404
  visible fragment; confirm the button (`hx-post="/review/sample"`) is on the index.
- `tests/test_demo.py`: extend `test_single_samples_match_the_golden_set` to assert
  each single's `beverage_type` matches its golden application; keep the existing
  `href="/static/demo/{filename}"` assertion (download link stays).

---

## Deferred — reassess after PR2

- **PR3 — Segmented tabs** (`Review one label | Review a batch`): show one workflow
  at a time; relocate the sample affordances into their mode; likely CSS/`:target`
  or a tiny toggle, no new backend. Re-decide scope once PR1/PR2 are in.
- **PR4 — Context-sensitive coverage notice**: show the wine/malt partial-coverage
  caveat only when wine/malt is selected (currently always-on in `index.html`).

---

## Verification

- **Automated:** `uv run pytest tests/test_ui.py tests/test_demo.py` (and full
  `uv run pytest` before commit). PR2 also exercises the demo drift tests.
- **Manual (browser):** run `uv run uvicorn ttb_label_reviewer.main:app --port 8099`,
  reload `/`.
  - PR1: submit a sample/real review → result scrolls to top of viewport, heading
    visible, focus lands on it; trigger an error (e.g. bad ABV) → same behavior.
  - PR2: click `Run this sample ▸` → a real result renders with no typing/attaching;
    verify the three samples and a 404 path. Confirm no `http(s)://` leaks on the page.
- Each PR is a separate reviewable commit; we feel PR1 and PR2 before deciding PR3.
