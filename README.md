# TTB Label Reviewer

AI-powered alcohol label verification prototype: a vision model
extracts structured fields from label images; a deterministic,
CI-tested rule engine applies TTB labeling rules and renders the
verdict. **The AI extracts, the code decides.**

Design docs live in [docs/](docs/) — start with
[docs/build-brief.md](docs/build-brief.md).

> Status: milestone 1 (skeleton + deploy). The rule engine, extraction
> adapter, review UI, golden-set eval, and batch flow land in later
> milestones; this README grows with them.

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
