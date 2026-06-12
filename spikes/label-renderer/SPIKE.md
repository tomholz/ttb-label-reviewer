# Spike: programmatic label rendering for the golden set

> **Promoted** (milestone 5): the production generator now lives at
> [golden/generate.py](../../golden/generate.py) — 16 cases, manifest per
> contracts.md §5, plus the degradation pipeline and hyphenated-warning
> variant this spike recommended. This directory stays as the record of
> the GO decision; nothing imports from it.

**Question:** can we render realistic label images whose text is exact by
construction, including the DS-5 bold-lead-in/regular-remainder contrast?

**Answer: yes. Recommendation: GO** — build the full golden set with this
approach.

## Approach chosen

Pillow, not HTML→PNG. macOS ships Arial regular and bold as *separate TTF
files* (`/System/Library/Fonts/Supplemental/Arial.ttf` and `Arial Bold.ttf`),
so bold control is just loading two fonts — no browser, no font-weight CSS
guesswork, one pip dependency. Run with `uv run --with pillow
render_labels.py`; output lands in `out/`.

Every string drawn on the image is a Python constant, and
`out/ground_truth.json` is serialized from those same constants, so the
sidecar cannot drift from the pixels.

## What was painful

- **Mixed-font word wrap is the one thing Pillow doesn't give you.**
  `textwrap`/`multiline_text` assume a single font, so a bold lead-in flowing
  inline into a regular remainder needs a hand-rolled greedy wrapper that
  tracks `(word, font)` pairs and measures with `draw.textlength` (~30 lines,
  `wrap_segments`/`draw_wrapped` in `render_labels.py`). Once written it's
  reusable for every variant.
- Everything else (borders, centering, type hierarchy) was trivial.

## Verification (read each PNG back visually)

- **(a) compliant:** "GOVERNMENT WARNING:" bold all-caps; remainder visibly
  lighter weight; full canonical text incl. "birth defects". Bold/regular
  contrast is plainly distinguishable at a glance — DS-5c has signal.
- **(b) title-case:** lead-in really reads "Government Warning:" (still
  bold); remainder canonical. Exactly the DS-5b probe.
- **(c) substitution:** "...because of the risk of **fetal harm**. (2)..." —
  one-word swap present, everything else canonical, lead-in correct.
- **(d) missing:** no warning anywhere; all other fields intact.

No verification failures. Wrapping never hyphenates, so DS-5a's
rejoin-hyphenation normalization is unexercised — if we want that probe, add
a deliberately hyphenated variant later.

## Caveats / next steps for the full set

- Labels are clean and flat — ideal for testing rule logic and the
  extraction-fidelity priors (the title-case probe), but they don't stress
  OCR robustness. For that, apply degradations (rotation, blur, JPEG
  artifacts, curved-bottle warp) *after* this exact-text rendering, keeping
  the same ground truth.
- Easy extensions: dropped "(2)" variant, multi-image sets (warning on a
  separate back label), other fonts/sizes for layout variety.
