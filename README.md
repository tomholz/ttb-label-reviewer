# TTB Label Reviewer

AI-powered alcohol label verification prototype: a vision model
extracts structured fields from label images; a deterministic,
CI-tested rule engine applies TTB labeling rules and renders the
verdict. **The AI extracts, the code decides.**

Live at <https://ttb-label-reviewer.fly.dev/>. Design docs live in
[docs/](docs/) — start with [docs/build-brief.md](docs/build-brief.md).

> Status: Wine/malt expansion complete. Single review, batch review, and
> `POST /api/review` support distilled spirits with full coverage plus
> wine and malt beverage partial coverage. The golden set, rendered demo
> imagery, eval harness, and live-eval scoreboard are committed below.

## Architecture

```
label images ──> extraction adapter ──> rule engine ──> review result
                 (vision model;         (deterministic,  (verdict, per-rule
                  raw strings only)      CI-tested)       findings, evidence)
```

Current rule scope: distilled spirits are full coverage for the prototype;
wine and malt beverage modes are partial coverage with visible scope-marker
findings for rules the prototype does not evaluate.

The split is the architecture (D-1): the vision model only *transcribes*
what is printed on the label into a fixed JSON contract
([docs/contracts.md](docs/contracts.md) §3) — raw strings plus per-field
confidence, no parsing, no judgment. Every parse ("45% Alc./Vol." →
45.0), every comparison, and every verdict happens in deterministic,
unit-tested Python. The model is never asked to judge compliance — only
to read. Consequences: every rule is testable without an API call, and
every verdict is explainable down to the character.

*Implementation status: the rule engine
(`src/ttb_label_reviewer/engine/`) and the extraction adapter
(`src/ttb_label_reviewer/extraction/`) are implemented and CI-tested —
adapter tests run against a stub client, never the live API (D-5). The
pipeline is exposed as a server-rendered single-review UI at `/`
(FastAPI + Jinja2 + vendored HTMX, no build chain per D-11), as
`POST /api/review`, and as the batch flow (zip + CSV manifest in,
SSE-streamed results table out); all run the identical pipeline path.
Every finding shows expected vs. extracted evidence — passes included —
and the warning check renders a character-level diff (D-8: evidence is
the interface). Wine and malt responses include `coverage="partial"`,
partial-coverage copy, and `not_evaluated` scope findings; distilled
spirits responses include `coverage="full"` plus their own DS-SCOPE row.*

## Assumptions

### "5 seconds" means time-to-first-result (D-3)

The stakeholder constraint ("if we can't get results back in about
5 seconds, nobody's going to use it") is interpreted as: a single-label
review completes in ~5 s, and a batch begins streaming per-label results
immediately — not "300 labels in 5 seconds." This interpretation is
inferred from the failure mode described in the interviews (agents
out-raced a 30–40 s/label scanner), not stated in the brief.

### Extraction fidelity: the hallucination risk is designed against

The vision model already knows the canonical government warning text.
Reading a label whose warning is paraphrased or differently cased, it
may transcribe what the warning *should* say rather than what it *does*
say — silently defeating exactly the checks that matter most. This is
treated as a first-class design constraint, not a footnote:

1. **The golden-set eval is the only real defense.** The test set
   includes near-miss warnings (one word changed, a dropped "(2)", the
   title-case lead-in) built specifically to measure whether extraction
   reproduces deviations faithfully. Everything else reduces the risk;
   only this measures it.
2. **The canonical warning text never appears in any model prompt**
   (hard constraint, D-2). It lives in exactly one place: the rule
   engine.
3. **The extraction prompt demands literal transcription** and forbids
   correction — hygiene that reduces, but does not eliminate, the risk.
4. **Targeted second-pass verification** on detected warning diffs —
   a forced-choice question about the specific span — is *designed but
   not implemented*: it is milestone 7, deliberately last in the build
   order and first in the pre-agreed cut order (D-9), because it is a
   signal-booster on labels already headed for review, never a defense
   layer (same model, same priors — correlated evidence). The eval
   bears the cut out: the default model transcribed every fidelity
   probe faithfully (no false fails for a second pass to rescue), and
   the hallucinated reads that were observed report confidence below
   the 0.9 threshold, so they are already routed to review.

### Federal transition story (D-10)

A public cloud API is acceptable for the prototype (the deliverable is
a publicly testable URL), but the stakeholder constraints — a firewall
that blocks outbound ML endpoints, a FedRAMP'd Azure shop — get a
designed-in transition story:

1. **The model client is a swappable adapter.** One module owns the
   vision API: Anthropic for the prototype; a FedRAMP-authorized
   endpoint (Claude via AWS Bedrock GovCloud, or an Azure Government
   model on TTB's own substrate) in production. A config change plus
   one adapter, not a rewrite.
2. **Single OCI container.** The same image that deploys to Fly.io runs
   unchanged on Azure Government, GovCloud ECS, or on-prem. Fly hosts
   the prototype URL; it is not load-bearing.
3. **All static assets vendored** — no CDN, no runtime outbound
   dependency except the model API. Derived directly from the firewall
   constraint that killed half the prior vendor's pilot.
4. **Stateless, ephemeral processing.** Uploads exist only for the
   duration of a review; nothing is retained — near-zero PII and
   records-retention surface for a future ATO conversation.

## Eval scoreboard

The current golden set is 21 rendered labels with known, deliberate defects
([golden/](golden/), manifest per contracts.md §5) — including the
extraction-fidelity probes that exist nowhere else: title-case
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
  `golden/results/` (gitignored); this table is the committed artifact.

### Illegibility threshold: tuned to 0.9, with a caveat that matters

The eval alone could not tune the threshold: models report ≥ 0.95
confidence on every golden field, degraded case included. So
[golden/probe_illegibility.py](golden/probe_illegibility.py) escalates
blur/downscale on a label whose warning *deviates* from canonical
(the "fetal harm" case), where reading and prior disagree:

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

## Known limitations

Deliberately out of scope (full list with citations in
[docs/ttb-requirements.md](docs/ttb-requirements.md)):

- **Same-field-of-vision rules (27 CFR 5.63(a), 4.39(a), 7.61).** Brand name,
  class/type, and alcohol content must appear together on one side of
  the container. Under the untagged multi-image contract, a label set
  could pass every per-field check while splitting those three items
  across sides — this tool cannot detect that, and says so rather than
  pretending otherwise.
- Type-size, legibility, and contrasting-background rules — not
  measurable from an unscaled image (warning *placement* is in scope as
  a visual-mode check).
- Class/type lawfulness validation, wine appellation/vintage/varietal and
  semi-generic/geographic-name checks, standards of fill, malt low-alcohol
  claim verification, formula/ingredient/organic/advertising rules.
- COLA system integration and permit verification.
- Wine under 7% ABV and non-malt beer jurisdictional edges are not handled.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

Extraction needs an Anthropic API key. Locally, put it in a gitignored
`.env` (or export it):

```sh
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
```

Without a key the app still runs; a review attempt returns a clear
503 (a visible error box in the UI). The extraction model defaults to
`claude-opus-4-8` — an adapter parameter, tuned against the golden set
(see the eval scoreboard above for the measured accuracy/latency
trade-off and why the cheaper models were not adopted).

## Run

```sh
uv run --env-file .env uvicorn ttb_label_reviewer.main:app --reload
```

Then open http://127.0.0.1:8000 for the single-review form: enter the
application fields, attach one or more label images, press **Review
label**. The same review is available as an API:

```sh
curl -s http://127.0.0.1:8000/api/review \
  -F beverage_type='distilled_spirits' \
  -F brand_name='OLD TOM DISTILLERY' \
  -F class_type='Kentucky Straight Bourbon Whiskey' \
  -F abv_percent=45.0 \
  -F net_contents='750 mL' \
  -F images=@spikes/label-renderer/out/label_a_compliant.png
```

## Deploy Smoke Check

After deploying, verify the public app is reachable and current:

```sh
curl -s https://ttb-label-reviewer.fly.dev/healthz
```

The response should include `{"status":"ok", ...}` plus version/revision
metadata. The homepage should show a beverage-type selector with
Distilled spirits, Wine, and Malt beverage options; if it says distilled
spirits only, Fly is still serving an old image.

### Batch review

The batch form on the same page takes one zip containing a
`manifest.csv` (template downloadable from the form; one row per
application, `image_filenames` semicolon-separated, `beverage_type` one of
`distilled_spirits`, `wine`, or `malt_beverage`) plus the label images it
names. Results stream in over SSE as each label completes
(rows are reviewed 4 at a time), grouped worst-first — row errors on
top, then fail > needs review > pass — with a live counts line; each
row expands to the same per-rule findings as a single review. A row
with a problem (missing image, unparseable ABV, blank field) is
reported inline and never stops the rest of the batch (contracts.md
§2). Limits: 500 rows and a 100 MB zip per batch.

Batch jobs live in process memory only — consistent with the
nothing-is-retained posture (D-10.4). A dropped connection resumes
where it left off (SSE `Last-Event-ID` replay), but a server restart
mid-batch loses the job; re-upload the zip.

### Demo data

The index page has a **Try it with sample data** card: downloadable
single-review images (with the form values to enter) and a 16-application
demo batch zip, all generated from the golden set — known, deliberate
defects, so the card can state exactly what you should see (5 fail ·
2 needs review · 6 pass · 3 row errors). The batch is mixed-category:
distilled spirits, wine, and malt beverage rows together, plus an
unsupported-`beverage_type` row that exercises the row-error path. The
assets are built by `golden/build_demo.py` and committed;
`tests/test_demo.py` fails CI if the goldens are regenerated without
rebuilding them. Note the demo runs real extraction: one demo batch
upload is ~13 vision-API calls.

## Test & lint

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

CI includes the golden-set integrity tests: the manifest must validate
against the contracts, and every expected outcome must follow from the
rule engine given a perfectly faithful extraction
(`golden/faithful_extractions.json`) — so a live eval miss can only mean
extraction infidelity, never a manifest/engine disagreement. No API
calls run in CI (D-5).

## Golden set & eval

```sh
# score a model against the golden set (writes golden/results/, prints
# a ready-to-paste scoreboard row)
uv run --env-file .env python -m ttb_label_reviewer.evaluation
uv run --env-file .env python -m ttb_label_reviewer.evaluation \
  --model claude-haiku-4-5-20251001 --threshold 0.9 --workers 2

# regenerate the golden images + manifest from their single source of
# truth (macOS fonts; a deliberate act — bump MANIFEST_VERSION), then
# rebuild the demo assets derived from them (CI fails if you forget)
uv run python golden/generate.py
uv run python golden/build_demo.py

# the degradation/confidence probe behind the threshold decision
uv run --env-file .env python golden/probe_illegibility.py --case warning-fetal-harm
```

## Deploy

Deployed on Fly.io as a single container:

```sh
fly secrets set ANTHROPIC_API_KEY=sk-ant-...   # once
fly deploy
```
