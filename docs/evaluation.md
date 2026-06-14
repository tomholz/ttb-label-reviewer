# Evaluation

How the extraction model is measured against the golden set, the model
choice that follows, and how the illegibility threshold was tuned. The
root [README](../README.md) carries only the headline; this is the
detail behind it. Commands to reproduce any of it are in the README's
*Golden set & eval* section.

## Eval scoreboard

The current golden set is 21 rendered labels with known, deliberate defects
([../golden/](../golden/), manifest per [contracts.md](contracts.md) §5) —
including the extraction-fidelity probes that exist nowhere else: title-case
"Government Warning:", "birth defects" → "fetal harm", a dropped "(2)",
end-of-line hyphenation, a warning on a separate back label, and a
degraded image — plus rendered wine and malt beverage labels proving the
extractor reads non-bourbon layouts. Every score records three
reproducibility fields — (a) the model identifier, (b) a hash of the
extraction prompt, (c) the golden-set manifest version/hash — because a
bare score is not a reproducible claim; with those three fields it is.
Eval runs are a deliberate script with a committed scoreboard, not a
blocking CI gate (D-5).

| Date | Model | Prompt hash | Golden set | Rule outcomes | Cases correct | Mean latency |
|---|---|---|---|---|---|---|
| 2026-06-11 | claude-opus-4-8 | `6886dc45365a` | v1 `464fabaa2311` | 176/176 (100.0%) | 16/16 | 5.7 s |
| 2026-06-11 | claude-sonnet-4-6 | `6886dc45365a` | v1 `464fabaa2311` | 176/176 (100.0%) | 16/16 | 6.3 s |
| 2026-06-11 | claude-haiku-4-5-20251001 | `6886dc45365a` | v1 `464fabaa2311` | 172/176 (97.7%) | 14/16 | 4.0 s |
| 2026-06-11 | claude-haiku-4-5-20251001 | `6886dc45365a` | v1 `464fabaa2311` | 148/176 (84.1%) | 11/16 | 4.2 s |
| 2026-06-13 | claude-opus-4-8 | `6886dc45365a` | v3 `2176b10ba2e4` | 247/247 (100.0%) | 21/21 | 11.0 s |

Latency note: the 2026-06-13 Opus row includes a cold structured-output
schema compile across the initial worker wave. Warmed cases completed in
roughly 4-5 seconds, which is the number relevant to the D-3 single-label
use case; the table keeps the cold run visible rather than hiding it.

- Current golden manifest v3 `2176b10ba2e4` adds one scope-marker
  `not_evaluated` row to each review and expands the live rendered set with
  wine and malt beverage cases. The 2026-06-13 Opus run scored all five
  wine/malt rendered cases correctly: `wine-compliant-table`,
  `wine-high-abv-missing-statement`, `malt-compliant`,
  `malt-abv-mismatch`, and `malt-abv-omitted`.
- The warning-fidelity probes were not duplicated per commodity. Wine and
  malt use the same canonical government-warning string and shared warning
  rules, so the existing title-case, word-substitution, dropped "(2)",
  hyphenation, back-label, and degraded probes measure the same extraction
  risk.
- **Model decision: the default stays `claude-opus-4-8`** (perfect
  score, ~5.7 s warm ≈ the D-3 budget). Sonnet matched it with no
  latency win. The two Haiku rows are *the same configuration run
  twice*: faster but noisy — every miss was conservative (visual
  bold/placement observations coming back "uncertain", routing
  pass-worthy labels to `needs_review`) plus one malformed-output
  row-level error; no false pass was observed.
- Opus and Sonnet transcribed **every fidelity probe faithfully**,
  including the title-case lead-in — the case the model's prior most
  wants to "correct".
- Historical rows before 2026-06-13 are warm runs.
- Per-run detail (including per-field confidences) lands in
  `../golden/results/` (gitignored); this table is the committed artifact.

## Illegibility threshold: tuned to 0.9, with a caveat that matters

The eval alone could not tune the threshold: models report ≥ 0.95
confidence on every golden field, degraded case included. So
[../golden/probe_illegibility.py](../golden/probe_illegibility.py)
escalates blur/downscale on a label whose warning *deviates* from
canonical (the "fetal harm" case), where reading and prior disagree:

| Degradation | Confidence | Transcription |
|---|---|---|
| up to blur 4 + 35% scale | 0.93–0.98 | faithful, deviation preserved |
| blur 6 + 25% scale and beyond | 0.80–0.85 | **silently reverts to canonical text** |

That second row is the hallucination risk from the requirements doc,
now measured: under heavy degradation the model autocompletes toward
the memorized warning *while still reporting 0.85 confidence*. The
default `illegibility_threshold` is therefore **0.9** — it splits the
observed gap (faithful ≥ 0.93, hallucinated ≤ 0.85) and costs nothing
on the golden set (all fields ≥ 0.95). The old 0.5 default caught
nothing: confidence never fell below 0.60 even at unreadable
degradation. Honest caveat: this is one synthetic label family and a
narrow margin — confidence self-report is **not** a reliable
hallucination detector; the structural defenses (canonical text out of
prompts, deterministic comparison, this golden set) remain the real
ones.
