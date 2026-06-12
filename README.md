# TTB Label Reviewer

AI-powered alcohol label verification prototype: a vision model
extracts structured fields from label images; a deterministic,
CI-tested rule engine applies TTB labeling rules and renders the
verdict. **The AI extracts, the code decides.**

Live at <https://ttb-label-reviewer.fly.dev/>. Design docs live in
[docs/](docs/) — start with [docs/build-brief.md](docs/build-brief.md).

> Status: milestone 2 (rule engine). The extraction adapter, review UI,
> golden-set eval, and batch flow land in later milestones; the sections
> below describe the committed design and note where implementation is
> pending.

## Architecture

```
label images ──> extraction adapter ──> rule engine ──> review result
                 (vision model;         (deterministic,  (verdict, per-rule
                  raw strings only)      CI-tested)       findings, evidence)
```

The split is the architecture (D-1): the vision model only *transcribes*
what is printed on the label into a fixed JSON contract
([docs/contracts.md](docs/contracts.md) §3) — raw strings plus per-field
confidence, no parsing, no judgment. Every parse ("45% Alc./Vol." →
45.0), every comparison, and every verdict happens in deterministic,
unit-tested Python. The model is never asked to judge compliance — only
to read. Consequences: every rule is testable without an API call, and
every verdict is explainable down to the character.

*Implementation status: the rule engine is implemented and CI-tested
(`src/ttb_label_reviewer/engine/`); the extraction adapter lands in
milestone 3.*

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
4. **Targeted second-pass verification** on detected warning diffs asks
   a forced-choice question about the specific span. Known limit: same
   model, same priors — correlated evidence, a signal-booster on labels
   already headed for review, never a defense layer.

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

*Populated in milestone 5.* Golden-set results are recorded with three
reproducibility fields — (a) the model identifier, (b) a hash of the
extraction prompt, (c) the golden-set manifest version/hash — because a
bare score is not a reproducible claim; with those three fields it is.
Eval runs are a deliberate script with a committed scoreboard, not a
blocking CI gate (D-5).

## Known limitations

Deliberately out of scope (full list with citations in
[docs/ttb-requirements.md](docs/ttb-requirements.md)):

- **Same-field-of-vision rule (27 CFR 5.63(a)).** Brand name,
  class/type, and alcohol content must appear together on one side of
  the container. Under the untagged multi-image contract, a label set
  could pass every per-field check while splitting those three items
  across sides — this tool cannot detect that, and says so rather than
  pretending otherwise.
- Type-size, legibility, and contrasting-background rules — not
  measurable from an unscaled image (warning *placement* is in scope as
  a visual-mode check).
- Class/type lawfulness validation (BAM Ch. 4 taxonomy), standards of
  fill, formula/ingredient/organic/advertising rules.
- COLA system integration and permit verification.
- Distilled spirits only; wine and malt beverage rules are stubbed in
  the requirements doc for later build-out.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

## Run

```sh
uv run uvicorn ttb_label_reviewer.main:app --reload
```

Then open http://127.0.0.1:8000.

## Test & lint

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Deploy

Deployed on Fly.io as a single container:

```sh
fly deploy
```
