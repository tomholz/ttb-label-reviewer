# TTB Label Reviewer

AI-powered alcohol label verification prototype: a vision model extracts
structured fields from label images; a deterministic, CI-tested rule
engine applies TTB labeling rules and renders the verdict. **The AI
extracts, the code decides.**

Live at <https://ttb-label-reviewer.fly.dev/>.

> Distilled spirits are full coverage; wine and malt beverages are partial
> coverage — every result carries a `coverage` value and visible
> scope-marker findings for rules the prototype does not evaluate. Single
> review, batch review, and `POST /api/review` all run the identical
> pipeline.

## Architecture

```
label images ──> extraction adapter ──> rule engine ──> review result
                 (vision model;         (deterministic,  (verdict, per-rule
                  raw strings only)      CI-tested)       findings, evidence)
```

The split is the architecture (D-1): the vision model only *transcribes*
what is printed into a fixed JSON contract ([docs/contracts.md](docs/contracts.md)
§3) — raw strings plus per-field confidence, no parsing, no judgment.
Every parse ("45% Alc./Vol." → 45.0), every comparison, and every verdict
happens in deterministic, unit-tested Python. The model is never asked to
judge compliance — only to read. Consequences: every rule is testable
without an API call, and every verdict is explainable down to the
character (D-8: evidence is the interface — every finding shows expected
vs. extracted, and the warning check renders a character-level diff).

Design decisions and their rationale live in
[docs/decisions.md](docs/decisions.md); the full documentation map is
[docs/README.md](docs/README.md).

## Approach & tools

- **Python end to end (D-11)** — one language across the rule engine,
  extraction adapter, eval harness, golden-label renderer, and web layer.
- **FastAPI + Jinja2 + vendored HTMX** — server-rendered UI, SSE for the
  streaming batch table, no SPA build chain. Static assets are vendored —
  no CDN, no runtime outbound dependency except the model endpoint (D-10.3).
- **Pillow** — renders the golden-set label images from one source of truth.
- **Anthropic SDK** — the vision-extraction client; `EXTRACTOR_BACKEND`
  selects the endpoint (see [Setup](#setup)).
- **Fly.io** — single OCI container; the same image is portable to a
  federal environment (D-10).

## Assumptions

- **"5 seconds" means time-to-first-result (D-3).** A single-label review
  completes in ~5 s; a batch begins streaming per-label results immediately
  — not "300 labels in 5 seconds." Inferred from the interview failure mode
  (agents out-raced a 30–40 s/label scanner), not stated in the brief.
- **Scope: distilled spirits full, wine + malt partial (D-12).** Wine/malt
  responses carry `coverage="partial"` and `not_evaluated` scope findings so
  a reviewer never mistakes "no issue found in checked rules" for "fully
  compliant." The bourbon example in the brief is the fully-covered path.
- **Extraction fidelity is the designed-against risk.** A vision model that
  already knows the canonical government warning may transcribe what it
  *should* say rather than what it *does* — silently defeating the checks
  that matter most. The defenses: the canonical text never appears in any
  prompt (D-2), the prompt demands literal transcription, and the
  golden-set eval measures fidelity directly with near-miss probes. Detail:
  [docs/ttb-requirements.md](docs/ttb-requirements.md) → Extraction fidelity
  and [docs/evaluation.md](docs/evaluation.md).
- **Cloud API now, federal endpoint later (D-10).** A public cloud API is
  fine for a publicly testable prototype; the model client is a swappable
  adapter (Bedrock GovCloud / Vertex via the same SDK), the only runtime
  outbound dependency, behind a stateless container. The choice of Anthropic
  is not a vendor lock-in: the deterministic engine makes every compliance
  decision, so the model stays a replaceable, competitively procurable,
  FedRAMP-authorized commodity behind the adapter. Full transition story:
  [docs/decisions.md](docs/decisions.md) D-10.

## Eval

Against a golden set of 21 rendered labels with known, deliberate defects —
including extraction-fidelity probes (title-case lead-in, "birth defects" →
"fetal harm", a dropped "(2)", hyphenation, a back-label warning, a
degraded image) built specifically to measure whether deviations are
transcribed faithfully — the default model `claude-opus-4-8` scores
**247/247 rule outcomes (21/21 cases), ~5 s warm**. Full scoreboard,
model-choice rationale, and the illegibility-threshold analysis:
[docs/evaluation.md](docs/evaluation.md).

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

Without a key the app still runs; a review attempt returns a clear 503 (a
visible error box in the UI). The extraction model defaults to
`claude-opus-4-8`, tuned against the golden set (see
[docs/evaluation.md](docs/evaluation.md) for the measured accuracy/latency
trade-off and why the cheaper models were not adopted).

`EXTRACTOR_BACKEND` selects the Claude endpoint (D-10.1): `anthropic`
(default, the public API), `bedrock` (Claude on AWS Bedrock, GovCloud /
FedRAMP High), `vertex` (GCP), or `offline` (no network call — returns a
zero-confidence result so every review routes to `needs_review`; proves the
app boots and serves with zero outbound dependency, does not read labels).
Bedrock and Vertex authenticate via their cloud's ambient credentials, so
the production move is one environment variable, not a code change. Leave
`EXTRACTOR_BACKEND` unset on the public deployment.

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
reported inline and never stops the rest of the batch
([docs/contracts.md](docs/contracts.md) §2). Limits: 500 rows and a
100 MB zip per batch.

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

Methodology and results: [docs/evaluation.md](docs/evaluation.md).

## Deploy

Deployed on Fly.io as a single container:

```sh
fly secrets set ANTHROPIC_API_KEY=sk-ant-...   # once
fly deploy
```

After deploying, verify the public app is reachable and current:

```sh
curl -s https://ttb-label-reviewer.fly.dev/healthz
```

The response should include `{"status":"ok", ...}` plus version/revision
metadata. The homepage should show a beverage-type selector with
Distilled spirits, Wine, and Malt beverage options; if it says distilled
spirits only, Fly is still serving an old image.

## Human-in-the-loop: disposition (deliberate next step, not built)

This is decision-support, not an autograder — the agent makes the final
call. Dave's example in the brief (`STONE'S THROW` on the label vs
`Stone's Throw` in the application) is a *technical* mismatch a human
correctly waves through; the tool's job is to surface it with evidence,
not to be overruled silently. The natural next feature is therefore a
per-result **disposition**: accept the verdict, override a finding with a
recorded reason, or annotate — and for a batch, export the dispositioned
queue.

It is deliberately not in this prototype. Persistence is out of scope by
the brief ("We're not storing anything sensitive for this exercise"; a
"standalone proof-of-concept", no COLA system of record to write back to),
and a half-built stateful review-of-record is precisely the "ambitious but
incomplete" path the brief steers away from — it would also pull in the
PII/retention surface IT asked us to avoid. The substrate is already here:
every finding renders expected-vs-extracted evidence (D-8), so this is a
disposition/persistence layer over existing output, not new analysis.

## Known limitations

Deliberately out of scope (full list with citations in
[docs/ttb-requirements.md](docs/ttb-requirements.md)):

- **Same-field-of-vision rules (27 CFR 5.63(a), 4.39(a), 7.61).** Brand
  name, class/type, and alcohol content must appear together on one side.
  Under the untagged multi-image contract a label set could pass every
  per-field check while splitting those across sides — the tool says so
  rather than pretending otherwise.
- Type-size, legibility, and contrasting-background rules — not measurable
  from an unscaled image (warning *placement* is in scope as a visual check).
- Class/type lawfulness, wine appellation/vintage/varietal and
  semi-generic/geographic-name checks, standards of fill, malt low-alcohol
  claims, formula/ingredient/organic/advertising rules.
- COLA system integration and permit verification.

## Documentation

[docs/README.md](docs/README.md) indexes everything: the design decisions,
the TTB rule reference, the data contracts, the evaluation methodology, and
the research/planning artifacts.
