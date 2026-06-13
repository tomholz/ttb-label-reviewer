# Wine and Malt Beverage Expansion Research Brief

Purpose: research whether and how to add partial wine and malt beverage
review modes while preserving the current project's evidence-first,
deterministic, clearly scoped design.

This is a research and design spike, not an implementation task. Do not
write production code during this spike. The output should be a
decision-ready memo that can become an implementation plan later.

## Starting Point

The app currently implements distilled spirits review deeply: the model
extracts raw label fields and deterministic code applies DS-1 through
DS-8. The README explicitly documents the distilled-spirits scope and
known limitations.

The project description mentions alcohol labels broadly, including beer,
wine, and distilled spirits. The sample label is bourbon, so the current
scope is defensible. Still, partial wine and malt beverage coverage may
improve evaluator perception if it is implemented honestly and with
clear user-facing limitations.

Use the term **malt beverage** in regulations, code, docs, tests, and
contracts. UI copy may say **beer/malt beverage** where that helps
ordinary users recognize the category, but the internal category name
should be `malt_beverage`.

## Research Objective

Define an 80/20 expansion that:

- Adds useful category-specific behavior for wine and malt beverages.
- Reuses shared checks where regulations and product behavior genuinely
  overlap.
- Makes partial coverage impossible to miss in the UI and result output.
- Avoids shallow checkbox coverage that would weaken the current
  correctness story.
- Preserves "the AI extracts, the code decides."

## Non-Goals

- Do not implement code.
- Do not claim full wine or malt beverage compliance.
- Do not add wine/malt fields to the extraction contract unless the
  research justifies each new field.
- Do not weaken existing distilled-spirits behavior, tests, golden cases,
  or README claims.
- Do not hide unsupported category-specific rules. Unsupported checks
  should be visible as not evaluated, not silently omitted.

## Standing Constraints

Carry over the existing project constraints:

- The canonical government warning text never appears in any model
  prompt.
- The model returns raw strings only. All parsing, comparison, and
  verdicts happen in deterministic, tested code.
- Visual-mode rules can never produce autonomous `fail`.
- The UI is decision support, not decision making; the reviewing agent
  stays the authority.
- No runtime outbound dependency except the model API.
- Batch and single-review paths must use the same underlying rule
  behavior.

## Questions To Answer

### 1. Regulatory Scope Matrix

Create a matrix for:

- Distilled spirits
- Wine
- Malt beverages

Rows should include at least:

- Brand name
- Class/type designation
- Alcohol content
- Net contents
- Name/address
- Country of origin for imports
- Government health warning text
- Government warning capitalization/bold/layout
- Proof or proof-like internal consistency, if applicable
- Wine-specific high-value items
- Malt-beverage-specific high-value items
- Known out-of-scope items

Each cell should state:

- `implemented`, `partial`, `not applicable`, or `not evaluated`
- the relevant citation
- what evidence the current extraction contract can or cannot provide
- whether the rule can safely produce `fail`, or only `needs_review`

### 2. 80/20 Rule Proposal

Identify the smallest defensible category-specific rule set for wine and
malt beverages.

Prefer rules that are:

- common on labels
- easy for evaluators to understand
- supported by fields already extracted, or by a very small contract
  extension
- deterministic enough to test without live model calls
- valuable in batch triage

Be skeptical of rules that require deeper taxonomy, formula, ingredient,
or claim analysis.

### 3. Extraction Contract Impact

Decide whether the existing extraction result is sufficient.

For each proposed new extraction field, document:

- field name and shape
- which wine or malt rule consumes it
- why existing fields are insufficient
- whether the model can realistically transcribe it as raw evidence
- golden cases needed to test extraction fidelity
- prompt-risk analysis, especially any field that might prime the model
  toward legal conclusions instead of transcription

If a category-specific rule cannot be supported without expanding the
contract, either justify the expansion or mark the rule `not evaluated`.

### 4. UX and Result Vocabulary

Design user-facing language for partial coverage.

Answer:

- Should the top-level result vocabulary stay `Pass` / `Needs review` /
  `Fail`, or should the UI use labels such as `No issue found in checked
  rules`, `Needs agent review`, and `Issue found`?
- How should the app distinguish full distilled-spirits coverage from
  partial wine/malt coverage?
- What exact notice appears next to the beverage-type control?
- What exact notice appears in the result banner for wine/malt?
- How should per-rule `not evaluated` findings read?
- Should `not evaluated` count separately from `not_applicable`?

The desired UX signal: a reviewer should never mistake partial wine or
malt review for full category compliance.

### 5. Batch Compatibility

Define batch behavior for wine and malt beverage rows.

Answer:

- Accepted `beverage_type` values.
- Manifest template changes.
- Row validation behavior for unknown or unsupported beverage types.
- Whether demo batch should include distilled spirits, wine, and malt
  beverage rows together.
- How partial-coverage notices appear in streamed batch rows.
- Whether batch sorting changes when a result has only checked-rule
  passes plus several `not evaluated` rows.

### 6. Golden and Demo Expansion

Propose exact new golden/demo cases.

Minimum expected shape:

- one wine row/image with no issue found in checked rules
- one wine row/image with a category-specific issue
- one malt beverage row/image with no issue found in checked rules
- one malt beverage row/image with a category-specific issue
- at least one case that proves `not evaluated` rows are visible
- at least one batch case mixing categories

For each case, specify:

- purpose
- application fields
- label fields
- expected findings
- whether it belongs in the live extraction eval, the deterministic
  faithful-extraction tests, the demo assets, or all three

### 7. Architecture Recommendation

Recommend a structure before implementation.

Expected direction: separate rule lists per category, composed from
shared helper rules where appropriate:

- common helpers for brand, class/type, warning, name/address, origin
- category-specific rules for alcohol content and net contents
- explicit not-evaluated scope marker rules

Call out any changes needed in:

- engine types
- parser functions
- review dispatch
- API and UI forms
- batch parser
- demo builder
- golden manifest and faithful extractions
- README and requirements docs

### 8. Cut Line

Define what should remain out of scope for this expansion, even if it
looks nearby.

The cut line should protect the project from turning into broad but
unverified compliance software. Any unsupported but important rule
should become a visible `not evaluated` finding with a plain-language
explanation and citation.

## Suggested Output

Produce a memo with these sections:

1. Recommendation
2. Regulatory scope matrix
3. Proposed wine rules
4. Proposed malt beverage rules
5. Extraction contract impact
6. UX vocabulary and notices
7. Batch compatibility
8. Golden/demo expansion
9. Architecture impact
10. Cut line
11. Implementation plan candidates

The memo should separate facts from recommendations. Cite primary
sources, preferably current eCFR sections and TTB guidance pages. If a
recommendation is an inference from stakeholder needs rather than a
regulatory requirement, label it as such.

## Prompt For A Future Research Session

Use this prompt to start the research spike:

```text
We are considering adding partial wine and malt beverage review modes to
the TTB Label Reviewer. Read docs/project-description.md,
docs/ttb-requirements.md, docs/contracts.md, docs/decisions.md, README.md,
and docs/wine-malt-research-brief.md.

Do not implement code. Research the wine and malt beverage regulatory
domains and produce a decision memo that recommends an 80/20 partial
coverage scope. Preserve the project's current posture: the AI extracts
raw strings, deterministic code decides, unsupported checks are visibly
not evaluated, and the UI must not imply full compliance for partial
categories.

Use primary sources for regulatory claims. Prefer current eCFR and TTB
guidance. Be explicit about citations, extraction-contract impact, UX
language, batch compatibility, golden/demo cases, architecture changes,
and the cut line.
```
