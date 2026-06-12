# TTB Label Verification Requirements

Curated, scoped distillation of TTB labeling requirements for the label
verification prototype. This file is the single source of truth for the
rules implemented in code. Each rule cites its authority.

**Scope:** Distilled spirits only (the sample label is a bourbon).
Wine (27 CFR Part 4) and malt beverages (27 CFR Part 7) are stubbed below
for later build-out using the same schema.

**Verified against:** eCFR current as of June 2026. Note that the
Distilled Spirits Beverage Alcohol Manual (BAM, TTB P 5110.7) dates from
04/2007 and predates the 2022 reorganization of Part 5 (T.D. TTB-176);
where they conflict, the eCFR controls.

---

## Rule schema

Each rule declares:

| Field | Meaning |
|---|---|
| `kind` | `consistency` (label must match the application), `compliance` (label must satisfy regulation regardless of application), or `internal` (label must be self-consistent) |
| `match_mode` | `fuzzy` (case/punctuation-insensitive), `banded` (numeric, with pass / needs_review / fail bands), `exact_verbatim` (character-exact after defined normalization), `presence` (field must exist and be legible), `visual` (format/layout judgment from the image; outcomes restricted to `pass` / `needs_review` **by construction** — a `visual` rule can never autonomously fail a label) |
| `applies_when` | Optional condition (e.g., `imported == true`) |
| `citation` | Controlling regulation / guidance section |

## Outcome model

Per-rule outcomes are three-valued — **pass**, **fail**, **needs_review**
— and every non-pass finding carries a **reason code**:

| Reason | Meaning |
|---|---|
| `mismatch` | Field found and legible, but disagrees with the application (or, for `internal` rules, with another label field) |
| `missing` | Field not found on any provided label image |
| `illegible` | Field located but extraction confidence is too low to compare |
| `format` | Content matches but a format requirement is violated (e.g., capitalization) |

Handling rules:

- **Illegibility never produces `fail` and never produces a silent
  `pass`.** Low-confidence or unreadable extraction → `needs_review` with
  reason `illegible`. This mirrors current agent practice (reject and
  request a better image — a human call, not an automated one).
- **Per-label aggregation:** worst of the per-rule outcomes, ordered
  `fail > needs_review > pass`. The UI surfaces counts (e.g., "2 fail,
  1 review, 4 pass"), not just the aggregate verdict, to support triage
  of large batches.

## Label images: cardinality

An application may supply **one or more label images** (front, back,
side, neck). All images for an application are evaluated together as a
single label set; a field satisfied on any image satisfies the rule.
Images are untagged — no front/back designation is required, and order
is irrelevant.

This is regulation-aligned, not just practical: 27 CFR 16.21 expressly
permits the health warning to appear on the brand label **or** a
separate front, back, or side label. A single-image contract would
mis-handle the most common real-world placement (warning on the back
label).

The multi-image contract is what gives `missing` vs `illegible` meaning:
"not found across any provided image" is `missing`; "found but
unreadable" is `illegible`.

---

## Distilled spirits rules

### DS-1 — Brand name

- **kind:** consistency
- **match_mode:** fuzzy
- **check:** Brand name on label matches brand name in application.
  Case differences and minor punctuation variance (e.g., `STONE'S THROW`
  vs `Stone's Throw`) → `needs_review`, not `fail`.
- **citation:** 27 CFR 5.63 (mandatory information), 5.64 (brand name);
  BAM Ch. 1 §1

### DS-2 — Class/type designation

- **kind:** consistency
- **match_mode:** fuzzy
- **check:** Class/type on label (e.g., "Kentucky Straight Bourbon
  Whiskey") matches the application. Validating that the designation is
  itself a lawful class/type (BAM Ch. 4 taxonomy) is **out of scope**.
- **citation:** 27 CFR 5.63(a); BAM Ch. 1 §2

### DS-3 — Alcohol content

- **kind:** consistency
- **match_mode:** banded
- **check:** ABV stated on label as a percentage of alcohol by volume.
  Comparison is on the **parsed numeric value**, never the string —
  "45%", "45.0%", and "45% Alc./Vol." are the same number.
  - **Bands:** exact numeric match → `pass`; difference ≤ 0.3 pp →
    `needs_review` (reason `mismatch`); difference > 0.3 pp → `fail`.
  - Required form: "__% alcohol by volume"; permitted abbreviations:
    `alc`, `%`, `/` for "by", `vol` (e.g., "45% Alc./Vol.").
  - Proof (e.g., "90 Proof") is optional and may appear in addition to,
    never instead of, the ABV statement. See DS-8 for the proof
    cross-check.
- **design caveat (state in code comment):** the ±0.3 pp tolerance in
  27 CFR 5.65(c) governs label vs. *product as analyzed* — a production
  tolerance, not a paperwork tolerance. The application and label should
  state the same number, so exact match is required for `pass`. We
  **borrow** the 0.3 pp figure from the adjacent regulation purely as
  the boundary between "human judgment" (`needs_review`) and "clear
  mismatch" (`fail`). That boundary is a design choice, not a derived
  requirement.
- **citation:** 27 CFR 5.65(a)–(c)

### DS-4 — Net contents

- **kind:** consistency
- **match_mode:** fuzzy (numeric + unit normalization, e.g., "750 mL" ≡
  "750ML")
- **check:** Net contents stated on label and matches application.
  Whether the value is an authorized standard of fill is **out of scope**.
- **citation:** 27 CFR 5.63(a), 5.70; BAM Ch. 1 §6

### DS-5 — Government health warning

Three sub-checks with **different decidability**; they report
independently.

Canonical text (lives in the rule engine **only** — see Extraction
fidelity below):

> GOVERNMENT WARNING: (1) According to the Surgeon General, women
> should not drink alcoholic beverages during pregnancy because of the
> risk of birth defects. (2) Consumption of alcoholic beverages impairs
> your ability to drive a car or operate machinery, and may cause
> health problems.

#### DS-5a — Text verbatim

- **kind:** compliance
- **match_mode:** exact_verbatim
- **check:** Warning text matches the canonical statement word-for-word
  after normalization. Paraphrases, omissions, substitutions (e.g.,
  "birth defects" → "fetal harm"), or reordering → `fail` (reason
  `mismatch`); warning absent from all images → `fail` (reason
  `missing`).
- **normalization (applied before comparison):** collapse whitespace
  runs and line breaks; rejoin end-of-line hyphenation; normalize curly
  vs. straight apostrophes and quotes. Comparison of the remainder
  (after the "GOVERNMENT WARNING:" lead-in) is **case-insensitive** —
  judgment call: 16.22(a) mandates capitals only for the words
  "GOVERNMENT WARNING"; the remainder's case is unspecified, and
  wording, not case, is what 16.21 fixes. Lead-in case is checked by
  DS-5b; placement/layout is checked by DS-5d.
- **citation:** 27 CFR 16.21 (text); applicability to spirits ≥0.5% ABV
  per 27 CFR 16.20 and 5.71(a)

#### DS-5b — "GOVERNMENT WARNING" capitalization

- **kind:** compliance
- **match_mode:** exact_verbatim (case-sensitive, lead-in only)
- **check:** The words "GOVERNMENT WARNING" appear in capital letters.
  Title case ("Government Warning") or other casing → `fail` (reason
  `format`). This is an autonomous pass/fail check — it is the exact
  rejection scenario agents report catching by eye, and the tool must
  catch it too.
- **note:** decidable in code, but its *input* is subject to the same
  extraction-fidelity risk as DS-5a — a vision model's prior on this
  string is all-caps, so title case on the label is precisely what
  extraction is most likely to silently normalize. The title-case golden
  label is therefore the single highest-value extraction-fidelity probe
  in the test set (see Extraction fidelity).
- **citation:** 27 CFR 16.22(a)(2)

#### DS-5c — Bold formatting

- **kind:** compliance
- **match_mode:** visual
- **check:** "GOVERNMENT WARNING" in bold type; remainder **not** bold.
  Boldness is a visual judgment from an image, not reliably decidable —
  hence `visual` mode (pass/needs_review only).
- **citation:** 27 CFR 16.22(a)(2)

#### DS-5d — Placement and layout

- **kind:** compliance
- **match_mode:** visual
- **check:** The warning appears separate and apart from all other
  information, as a single uninterrupted block (not broken up or
  interleaved with other text). Layout judgments from an image are the
  same epistemic category as boldness — hence `visual` mode
  (pass/needs_review only).
- **citation:** 27 CFR 16.21 ("separate and apart from all other
  information"); 16.22(a)(3) (statement may not be compressed so as to
  be illegible). Note: the word "continuous" does not appear in the
  regulation text — "continuous statement" is TTB guidance phrasing;
  the regulatory basis is 16.21 plus the 16.22(a) legibility provisions.
- **out of scope (whole DS-5 family):** type-size minima (16.22(b)) and
  characters-per-inch limits (16.22(a)(4)) — not measurable from an
  unscaled image; contrasting-background (16.22(a)(1))

### DS-6 — Name and address of bottler/producer

- **kind:** compliance
- **match_mode:** presence
- **check:** A name-and-address statement appears (e.g., "Bottled by ___,
  City, State"). Verifying the named entity against permit records is
  **out of scope**.
- **citation:** 27 CFR 5.66 (domestic), 5.67–5.68 (imported/partly
  foreign); BAM Ch. 1 §4

### DS-7 — Country of origin

- **kind:** compliance
- **match_mode:** presence
- **applies_when:** `imported == true`
- **check:** Country-of-origin statement appears. (CBP rules control the
  form; presence-only check here.)
- **citation:** 27 CFR 5.69; 19 CFR Part 134; BAM Ch. 1 §5

### DS-8 — Proof ↔ ABV internal consistency

- **kind:** internal
- **match_mode:** banded (exact, small float epsilon)
- **applies_when:** a proof statement appears on the label
- **check:** Stated proof equals exactly 2× the stated label ABV
  (e.g., "90 Proof" ⇔ 45% Alc./Vol.). Mismatch → `needs_review` (reason
  `mismatch`), not `fail`: a discrepancy indicates either a genuine
  label defect or an extraction misread, and both warrant a human (or a
  targeted second-pass) look. This rule doubles as a free check on
  extraction quality.
- **citation:** 27 CFR 5.65(b)(1)(i) (optional statement of proof);
  note 5.65(c) is the actual-vs-labeled tolerance, which this rule does
  not rely on

---

## Extraction fidelity

The architecture is **"the AI extracts, the code decides"**: a vision
model converts label images into structured fields; a deterministic rule
engine applies DS-1–DS-8. This section governs the extraction side,
because it has a domain-specific failure mode:

**The vision model knows the canonical government warning.** When
reading a label whose warning is paraphrased, reworded, or differently
cased, the model may transcribe what the warning *should* say rather
than what it *does* say — autocompleting toward the memorized canonical
form. This silently defeats DS-5a and DS-5b in exactly the cases that
matter most. Countermeasures, in order of actual effectiveness:

1. **The golden-set eval is the only real defense.** The test set must
   include near-miss warnings — one word changed, "birth defects" →
   "fetal harm", a dropped "(2)", and the title-case lead-in — built
   specifically to measure whether extraction reproduces deviations
   faithfully. Everything below reduces risk; only this measures it.
2. **Hard constraint: the canonical warning text never appears in the
   extraction prompt.** It lives in exactly one place — the rule engine.
   Putting it in the prompt is maximal priming, and it is the kind of
   thing a future "improve the prompt" pass would innocently violate;
   hence stated here as a constraint, not a tip.
3. **The extraction prompt demands literal transcription** ("transcribe
   exactly as printed, including any errors or unusual casing") and
   forbids correction. This is hygiene: it reduces the risk, it does not
   eliminate it.
4. **Targeted second-pass verification on diffs.** When DS-5a/5b detect
   a discrepancy, one cheap follow-up vision call asks a pointed
   forced-choice question about the specific span ("Does the label say
   'birth defects' or 'fetal harm' here?"). The forced choice is
   deliberate: it makes the non-canonical reading explicitly available,
   countering the prior. **Stated limits:** the verifier is the same
   model with the same priors — correlated evidence, not independent
   evidence; stronger against OCR-noise false fails than against
   hallucinated passes. It is a signal-booster on labels already headed
   for review, never a defense layer, and must never be promoted into
   the first pass (it shows the model the canonical phrasing, which is
   acceptable only *after* the comparison has happened in code). Runs
   only on discrepant labels, so the latency budget for clean labels is
   untouched.

**Eval scoreboard:** golden-set results are recorded with (a) the model
identifier, (b) a hash of the extraction prompt, and (c) a hash/version
of the golden set itself. A bare score is not a reproducible claim;
with those three fields it is. (Eval runs are a deliberate script, not
a blocking CI gate — see docs/decisions.md.)

**Illegibility:** extraction reports per-field confidence; low
confidence routes to `needs_review` / `illegible` per the outcome model.

---

## Wine rules (stub — not yet implemented)

Authority: 27 CFR Part 4; warning statement per Part 16 (unchanged across
commodities). Note: wine under 7% ABV falls under FDA labeling rules, not
TTB COLA — a jurisdictional edge this tool does not handle.

## Malt beverage rules (stub — not yet implemented)

Authority: 27 CFR Part 7; warning statement per Part 16. ABV tolerance is
also ±0.3 pp (27 CFR 7.65(c)) with extra floors for "non-alcoholic" /
"low alcohol" claims. Note: beers made without malted barley may fall
under FDA rules.

---

## Out of scope (deliberately)

- Type size, legibility, contrasting-background rules
  (27 CFR 5.52, 16.22(a)(1), 16.22(a)(4), 16.22(b)) — not verifiable
  from a single unscaled image (warning placement itself is in scope as
  the visual-mode check DS-5d)
- Class/type lawfulness validation (BAM Ch. 4 taxonomy)
- Standards of fill (authorized container sizes)
- Formula, ingredient-declaration, organic, and advertising rules
- COLA system integration and permit verification

## Sources

- Distilled Spirits BAM (TTB P 5110.7, 04/2007):
  https://www.ttb.gov/images/pdfs/spirits_bam/complete-distilled-spirit-beverage-alcohol-manual.pdf
- 27 CFR Part 5 (Distilled Spirits):
  https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5
- 27 CFR Part 16 (Health Warning Statement):
  https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16
- 27 CFR Part 4 (Wine):
  https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-4
- 27 CFR Part 7 (Malt Beverages):
  https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-7
- TTB Labeling Resources hub:
  https://www.ttb.gov/regulated-commodities/labeling/labeling-resources
