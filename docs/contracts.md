# Data Contracts

The four data shapes that everything else is built against, plus the
golden-set manifest. Rules and outcome semantics live in
[ttb-requirements.md](ttb-requirements.md); decisions and rationale in
[decisions.md](decisions.md). Changing anything in this file after build
starts is a contract change — deliberate, not incidental.

## 1. Application record (input)

The subset of COLA application fields the rules consume. Used directly
by the single-review form and as the per-row schema of the batch
manifest.

| Field | Type | Required | Notes |
|---|---|---|---|
| `application_id` | string | batch: yes; single: auto-generated | Caller's identifier; echoed in results |
| `beverage_type` | enum | yes | `distilled_spirits` (only implemented value; wine/malt reserved) |
| `brand_name` | string | yes | DS-1 |
| `class_type` | string | yes | DS-2 |
| `abv_percent` | number | yes | DS-3; the number only (45.0), not a statement string |
| `net_contents` | string | yes | DS-4; e.g. "750 mL" |
| `imported` | boolean | no (default false) | gates DS-7 |
| `image_filenames` | list | yes | one or more, untagged, order-irrelevant |

## 2. Batch manifest (CSV in a zip)

A batch is one zip: `manifest.csv` + image files.

- One row per application. Columns = the fields above;
  `image_filenames` is **semicolon**-delimited within the cell
  (commas belong to CSV).
- Header row required; column order irrelevant; UTF-8.
- `imported`: `true`/`false` (case-insensitive); blank = false.
- Row-level validation errors (filename not in zip, unparseable ABV,
  missing required field) fail **that row** with a visible error in the
  results table; they never abort the batch. "Fail that row" means the
  row fails to be *processed* — a row error is an operational outcome
  outside the three-valued verdict model (the label was never reviewed,
  so it earns no `fail`), reported and counted separately from reviewed
  verdicts and surfaced above them in the results table so it is never
  buried under passes.
- The UI offers this file as a downloadable template with one example
  row.

## 3. Extraction result (vision model → rule engine)

The JSON the vision model must return. Governing principles, in
priority order:

1. **Raw strings only — no parsing, no judgment.** The model transcribes
   what is printed; code parses numerics ("45% Alc./Vol." → 45.0) and
   applies every rule. Parsers are deterministic and CI-tested; the
   model is neither.
2. **Literal transcription, as printed** — case, line breaks (`\n` where
   the label breaks), hyphenation, apostrophes all preserved.
   Normalization is code's job (DS-5a defines it), and it can only be
   code's job if extraction hasn't already "helpfully" normalized.
3. **The canonical warning text never appears in the extraction prompt**
   (hard constraint, D-2).
4. `null` means "not found on any provided image" — distinct from
   low-confidence (found but unsure), per the missing/illegible split.

```jsonc
{
  "brand_name":      { "raw": "OLD TOM DISTILLERY", "confidence": 0.98 },
  "class_type":      { "raw": "Kentucky Straight Bourbon Whiskey", "confidence": 0.97 },
  "alcohol_content": { "raw": "45% Alc./Vol.", "confidence": 0.99 },
  "proof":           { "raw": "90 Proof", "confidence": 0.99 },        // or null
  "net_contents":    { "raw": "750 mL", "confidence": 0.99 },          // or null
  "name_address":    { "raw": "Bottled by Old Tom Distillery, Bardstown, KY", "confidence": 0.95 },  // or null
  "country_of_origin": null,                                           // or { raw, confidence }
  "government_warning": {                                              // or null
    "raw_text": "GOVERNMENT WARNING: (1) According to the Surgeon\nGeneral, ...",  // verbatim, as printed
    "lead_in_bold": "yes",            // "yes" | "no" | "uncertain"
    "remainder_bold": "no",           // "yes" | "no" | "uncertain"
    "separate_and_apart": "yes",      // "yes" | "no" | "uncertain"
    "confidence": 0.93
  }
}
```

- `confidence` is the model's 0–1 legibility/certainty self-report per
  field. The illegibility threshold (below which a field routes to
  `needs_review`/`illegible`) is engine configuration, **not** part of
  this contract — it will be tuned against the golden set.
- The tri-state visual observations (`lead_in_bold`, etc.) feed the
  `visual`-mode rules DS-5c/DS-5d: `"yes"` (where that satisfies the
  rule) → `pass`; anything else → `needs_review`. By construction no
  mapping to `fail` exists.
- Extended thinking/explanations are not part of the contract; the
  model returns this object and nothing else.

## 4. Review result (rule engine → UI / API response)

```jsonc
{
  "application_id": "row-017",
  "verdict": "fail",                       // worst finding: fail > needs_review > pass
  "counts": { "fail": 1, "needs_review": 1, "pass": 5, "not_applicable": 1 },
  "findings": [
    {
      "rule_id": "DS-5b",
      "rule_name": "GOVERNMENT WARNING capitalization",
      "outcome": "fail",                   // pass | fail | needs_review | not_applicable
      "reason": "format",                  // mismatch | missing | illegible | format; null when pass/not_applicable
      "expected": "GOVERNMENT WARNING",
      "actual": "Government Warning",
      "citation": "27 CFR 16.22(a)(2)",
      "explanation": "Warning lead-in must be in capital letters; label uses title case.",
      "diff": [ /* DS-5a only: character-level diff spans, UI-renderable */ ]
    }
  ]
}
```

- `not_applicable` (DS-7 when not imported, DS-8 when no proof stated)
  is reported for UI completeness ("8 checks: 7 evaluated, 1 n/a") but
  is **excluded from aggregation** — the three-valued outcome model in
  ttb-requirements.md governs evaluated rules only.
- `expected` / `actual` appear on every evaluated finding, including
  passes — evidence is the interface (D-8), and a pass the agent can
  eyeball is more trustworthy than a green dot.
- Batch responses stream one review result per row as each completes
  (D-3), plus row-level validation errors in the same channel.

## 5. Golden-set manifest

One JSON file at the golden-set root; images alongside.

```jsonc
{
  "version": "1",                          // bumped on any change; hashed into the eval scoreboard
  "cases": [
    {
      "case_id": "warning-title-case",
      "purpose": "Extraction-fidelity probe: case autocomplete toward canonical (highest-value probe)",
      "application": { /* §1 record, inline */ },
      "expected": {
        "DS-1": { "outcome": "pass" },
        "DS-5a": { "outcome": "pass" },
        "DS-5b": { "outcome": "fail", "reason": "format" }
        // rules omitted here = expected pass; explicit is required only for non-pass and not_applicable
      }
    }
  ]
}
```

The eval harness runs each case through the real pipeline and scores
per-rule outcome matches; the scoreboard records model ID, extraction-
prompt hash, and this manifest's version/hash (D-5).
