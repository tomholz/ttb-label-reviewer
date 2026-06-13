# Wine & Malt Beverage Expansion — Decision Memo

Research spike output for [docs/wine-malt-research-brief.md](wine-malt-research-brief.md).
**No code is proposed for this spike** — this is a decision-ready memo that
can become an implementation plan.

**Sourcing note.** Regulatory claims cite current eCFR (Part 7 verified
against the post-TTB-188 reorganized numbering; Part 4 verified against the
current, *not*-yet-reorganized numbering — wine modernization remains a
proposed rule, so Part 4 still uses §§ 4.32–4.37). Citations were checked
2026-06-13 via the eCFR text and the Cornell LII mirror. Items labeled
**(inference)** are design recommendations from stakeholder needs, not
regulatory requirements. Facts and recommendations are kept separate within
each section.

---

## 1. Recommendation

**Add partial wine and malt beverage modes, gated behind an explicit
"partial coverage" posture, with zero new extraction-contract fields.**

The single most important finding: **the existing extraction contract
([contracts.md](contracts.md) §3) already supports the entire defensible
80/20 scope for both commodities.** The bourbon-shaped contract — raw
`brand_name`, `class_type`, `alcohol_content`, `net_contents`,
`name_address`, `country_of_origin`, `government_warning` strings — is, with
one DS-only exception (`proof`), commodity-agnostic. Wine and malt labels
carry the same field *vocabulary*; what differs is the *rules applied to
those fields*, which all live in deterministic code. So the expansion is
almost entirely an engine-and-UX change, not a contract or model change.
That is exactly the 80/20 the brief asks for, and it preserves the
correctness story: no new priming surface, no new live-extraction risk.

What genuinely differs by commodity is **alcohol content**, and that is
where the category-specific rules earn their keep:

- **Wine** has a real, decidable, category-specific defect this tool can
  catch and `fail`: a wine over 14% ABV that *omits* the alcohol statement,
  which § 4.36(a) makes mandatory above 14%. Below 14% the same omission is
  *permitted* (the "table wine"/"light wine" allowance), so it routes to
  `needs_review`. One rule, keyed off the application's ABV, expresses both.
- **Malt beverages** make the ABV statement *optional* (§ 7.65(a)), so a
  missing malt ABV can never be a `fail` — it is `needs_review` at most.
  The high-value malt-specific items ("non-alcoholic", "low alcohol",
  "alcohol free") require lab ABV the label cannot supply and are
  deliberately **not evaluated**, visibly.

The government health warning — the project's highest-value, highest-risk
check — is **identical across all three commodities** (27 CFR Part 16 is
commodity-independent). The entire DS-5 family and its extraction-fidelity
defenses transfer unchanged. This is the largest reuse win and the reason
the expansion is cheap.

**The one new outcome value the expansion needs:** `not_evaluated`, distinct
from `not_applicable`. Without it, "this prototype doesn't check wine
appellations" is indistinguishable from a pass — which is precisely the
mis-read the brief forbids.

**Recommended scope:** ship wine and malt modes that reuse the shared rules
(brand, class/type, warning, name/address, origin), add one category-
specific alcohol-content rule each, and emit explicit `not_evaluated` scope
markers for everything past the cut line. Keep the three-valued verdict, but
render it as **"No issue found in checked rules"** (not bare "Pass") for
partial categories, always paired with a partial-coverage banner.

If time-boxed, this is **two phases**: (P1) the outcome model + dispatch +
shared-rule refactor + wine/malt alcohol rules + scope markers + UI notices;
(P2) golden/demo expansion with rendered wine/malt imagery. P1 is the
load-bearing correctness work; P2 is evaluation breadth.

---

## 2. Regulatory scope matrix

Legend for the disposition cell: **impl** = already implemented for DS and
transfers directly; **partial** = supported with a documented narrowing;
**n/a** = does not apply to the commodity; **not-eval** = applies but this
prototype deliberately does not check it (visible scope marker). The
"`fail`-capable?" column states whether the rule may autonomously `fail` or
is capped at `needs_review` / `visual`.

### Mandatory-information rows

| Row | Distilled spirits | Wine | Malt beverage | `fail`-capable? | Evidence the contract provides |
|---|---|---|---|---|---|
| **Brand name** | impl — 27 CFR 5.63/5.64 | impl (shared) — 27 CFR 4.33 | impl (shared) — 27 CFR 7.64 | No (fuzzy → `needs_review` on variance) | `brand_name.raw` |
| **Class/type designation** | impl — 5.63(a) | impl (shared) — 4.34 | impl (shared) — Part 7 Subpart I | Yes (consistency vs application) | `class_type.raw` |
| **Alcohol content** | impl — 5.65 (±0.3 pp band) | **partial** — 4.36 (see §3) | **partial** — 7.65 (see §4) | Wine: yes; Malt: yes when present | `alcohol_content.raw` |
| **Net contents** | impl — 5.63(b)(2)/5.70 | impl (shared) — 4.37 | impl (shared) — 7.70 | No (may be molded in glass → `needs_review`) | `net_contents.raw` |
| **Name/address** | impl — 5.66–5.68 | impl (shared) — 4.35 | impl (shared) — 7.66–7.68 | Yes (missing → `fail`/`missing`) | `name_address.raw` |
| **Country of origin (imports)** | impl — 5.69; 19 CFR 102/134 | impl (shared, `applies_when imported`) — 19 CFR 102/134 (Part 4 adds no separate mandate) | impl (shared) — 19 CFR 102/134 | Yes when imported | `country_of_origin.raw` |

### Health-warning rows (27 CFR Part 16 — commodity-independent)

| Row | DS | Wine | Malt | `fail`-capable? | Notes |
|---|---|---|---|---|---|
| **Warning text verbatim** | impl — 16.21 | impl (shared, byte-identical) | impl (shared) | Yes | Same canonical text; same DS-5a engine |
| **"GOVERNMENT WARNING" caps** | impl — 16.22(a)(2) | impl (shared) | impl (shared) | Yes (`format`) | Same DS-5b |
| **Bold formatting** | impl (`visual`) — 16.22(a)(2) | impl (shared) | impl (shared) | No (`visual`) | Same DS-5c |
| **Placement / "separate and apart"** | impl (`visual`) — 16.21 | impl (shared) | impl (shared) | No (`visual`) | Same DS-5d |

Part 16 applies to any "alcoholic beverage" ≥ 0.5% ABV (16.10, 16.20);
wine < 7% ABV and non-malt "beer" fall to FDA and are a jurisdictional edge
this tool does not handle (carried over from the DS stub).

### Internal-consistency and category-specific rows

| Row | DS | Wine | Malt | `fail`-capable? | Notes |
|---|---|---|---|---|---|
| **Proof ↔ ABV consistency** | impl — 5.65(b) (DS-8) | **n/a** | **n/a** | n/a | "Proof" is a distilled-spirits concept; `proof` field stays `null` for wine/malt → DS-8 reports `not_applicable` |
| **Wine ABV mandatory > 14%** | n/a | **partial** — 4.36(a) | n/a | Yes (`missing` when >14% and absent) | The decidable wine-specific defect; see §3 |
| **Wine "table/light wine" ABV allowance** | n/a | **partial** — 4.36(a), 4.34 | n/a | No (absent ABV ≤14% → `needs_review`) | Class designation carries the allowance |
| **Malt ABV optional** | n/a | n/a | **partial** — 7.65(a) | No (absent → `needs_review`) | Optional unless added-flavor alcohol (undetectable from label) |
| **Malt "non-alcoholic"/"low alcohol"/"alcohol free"** | n/a | n/a | **not-eval** — 7.65(b)(3)–(5) | No | Requires lab ABV the label cannot supply; visible scope marker |
| **Wine appellation / vintage / varietal / semi-generic** | n/a | **not-eval** — 4.25/4.27/4.23/4.24 | n/a | No | Deep taxonomy; visible scope marker |
| **Standards of fill** | not-eval (DS) | **not-eval** — 4.72 | not-eval | No | Carried over; not measurable from image |
| **Sulfite / FD&C Yellow 5 / aspartame / cochineal declarations** | n/a | **not-eval** — 4.32(e) | **not-eval** — 7.63(b) | No | Conditional on facts (ppm, ingredients) not on the label face |
| **Same-field-of-vision** | not-eval — 5.63(a) | not-eval — 4.39(a) | not-eval — 7.61 | No | Carried over; untagged multi-image contract can't verify |

---

## 3. Proposed wine rules

Naming: **WN-** prefix, mirroring **DS-**. Most are the *same helper* as the
DS rule with a wine citation; only WN-3 is genuinely new logic.

- **WN-1 Brand name** — shared brand helper. fuzzy / consistency.
  27 CFR 4.33. (= DS-1 behavior.)
- **WN-2 Class/type designation** — shared class/type helper. fuzzy /
  consistency. 27 CFR 4.34. Lawfulness of the designation (varietal,
  appellation, semi-generic) is **out of scope** → see WN-SCOPE.
- **WN-3 Alcohol content** — *the one wine-specific rule.* consistency +
  conditional presence. 27 CFR 4.36.
  - **When the label states an ABV:** compare parsed numeric label value to
    the application value, exactly as DS-3. Band is a **design choice**
    (inference) borrowing the regulatory production tolerance as the
    human-judgment boundary: exact match → `pass`; within tolerance →
    `needs_review`; beyond → `fail`. Wine tolerance is **±1.5 pp for ≤14%
    ABV and ±1.0 pp for >14% ABV** (§ 4.36(b)(1)) — wider than the DS/malt
    0.3 pp, so the band is a per-category parameter, not a constant.
  - **When the label omits the ABV:** branch on the *application's* stated
    ABV (which the COLA record always has):
    - application ABV **> 14%** → § 4.36(a) makes the statement **mandatory**
      → `fail` / `missing`. *This is the decidable, category-specific wine
      defect worth shipping.*
    - application ABV **≤ 14%** → the "table wine"/"light wine" allowance
      may apply (§ 4.36(a)); the omission may be lawful → `needs_review` /
      `missing`, never `fail` (same epistemic posture as DS-4 net contents).
- **WN-4 Net contents** — shared net-contents helper. 27 CFR 4.37. Missing →
  `needs_review` (same molded-in-glass caveat as DS-4). Standards of fill
  (§ 4.72) out of scope.
- **WN-5 Government warning (a/b/c/d)** — the **entire DS-5 family, unchanged**.
  27 CFR Part 16. Same canonical text, same normalization, same `visual`
  caps on 5c/5d, same extraction-fidelity defenses.
- **WN-6 Name/address** — shared presence helper. 27 CFR 4.35.
- **WN-7 Country of origin** — shared presence helper, `applies_when imported`.
  19 CFR 102/134.
- **WN-SCOPE Not-evaluated scope marker** — a single rule that always
  reports `not_evaluated` enumerating the wine-specific checks this prototype
  does not perform (appellation of origin § 4.25, vintage § 4.27, varietal
  § 4.23, semi-generic/geographic names § 4.24, standards of fill § 4.72,
  sulfite declaration § 4.32(e)), each with a one-line plain-language reason
  and citation. See §6 for why this is a rule and not just README prose.

**Recommendation (inference):** ship WN-1, WN-2, WN-3, WN-4, WN-5, WN-6,
WN-7, WN-SCOPE. That is full reuse of the shared checks plus exactly one new
piece of category logic (WN-3's mandatory-above-14% branch), which is common
on labels, trivially explainable, and `fail`-decidable from existing fields.

---

## 4. Proposed malt beverage rules

Naming: **MB-** prefix.

- **MB-1 Brand name** — shared helper. 27 CFR 7.64.
- **MB-2 Class/type designation** — shared helper. Part 7 Subpart I.
- **MB-3 Alcohol content** — *the malt-specific rule.* 27 CFR 7.65.
  - **When stated:** consistency compare vs application; band **±0.3 pp**
    (§ 7.65(b)) — here the band number coincides with DS, but for malt it is
    the *actual regulatory tolerance*, not a borrowed one. Beyond band →
    `fail`; within → `needs_review`; exact → `pass`.
  - **When omitted:** § 7.65(a) makes the statement **optional** (mandatory
    only when alcohol derives from added nonbeverage flavors/ingredients,
    which the label face does not reveal). Therefore a missing malt ABV →
    `needs_review` / `missing`, **never `fail`.** The added-flavor trigger is
    explicitly past the cut line (§10).
- **MB-4 Net contents** — shared helper. 27 CFR 7.70. (Same missing →
  `needs_review` posture.)
- **MB-5 Government warning (a/b/c/d)** — the DS-5 family unchanged.
  27 CFR Part 16.
- **MB-6 Name/address** — shared presence helper. 27 CFR 7.66–7.68.
- **MB-7 Country of origin** — shared presence helper, `applies_when imported`.
  19 CFR 102/134.
- **MB-SCOPE Not-evaluated scope marker** — always `not_evaluated`,
  enumerating: "non-alcoholic" / "low alcohol" / "alcohol free" claim
  verification (§ 7.65(b)(3)–(5)), added-flavor ABV-mandatory trigger
  (§ 7.65(a)), sulfite/FD&C Yellow 5/aspartame/cochineal disclosures
  (§ 7.63(b)), standards of fill.

**Stretch candidate, flagged not recommended for the 80/20 (inference):** a
deterministic *internal-consistency* claims check — if `class_type` contains
"low alcohol"/"reduced alcohol" but the application ABV ≥ 2.5%, that is a
self-contradiction detectable without lab data → `needs_review`. It is
cheap and real, but it requires parsing marketing claims out of the
class/type string, which edges toward the "claim analysis" the brief tells
us to be skeptical of. Recommend listing it under MB-SCOPE as `not_evaluated`
for now and revisiting only if evaluators ask.

---

## 5. Extraction contract impact

**Recommendation: no new extraction fields. The contract is sufficient as-is.**

Walking the brief's per-field justification test for every field a wine/malt
rule consumes:

| Field a rule needs | Already in contract? | Verdict |
|---|---|---|
| brand, class/type, net contents, name/address, country, warning | yes | reuse unchanged |
| `alcohol_content.raw` (wine & malt ABV) | yes | reuse; code parses + bands per commodity |
| `proof` | yes (DS-only) | stays `null` for wine/malt; DS-8 → `not_applicable` |
| wine "table wine"/"light wine" designation | **yes — it *is* the `class_type`** | no new field; WN-3 reads `class_type` |
| malt "non-alcoholic"/"low alcohol" claim text | would be new | **do not add** — the check is `not_evaluated` anyway (needs lab ABV) |

The "table wine" allowance deserves emphasis because it looks like it needs a
new field and does not: the designation that triggers the allowance is the
class/type designation itself (§ 4.34), which is already transcribed. WN-3
inspects the already-extracted `class_type` plus the application ABV; no new
extraction surface.

**Prompt-risk analysis.** Adding any field that asks the model "is this a low-
alcohol product?" or "does this wine carry the mandatory ABV?" would prime the
model toward a *legal conclusion* rather than transcription — the exact
failure mode D-2 guards against for the warning. Holding the contract to raw
strings keeps the model a transcriber. The one field that already carries
priming risk — `government_warning` — is unchanged, so the existing fidelity
defenses (canonical text never in prompt; literal-transcription instruction;
golden-set near-misses) cover wine/malt with no new exposure, because the
warning text is byte-identical across commodities.

**Golden cases needed to test extraction fidelity (not new rules, new
*coverage*):** the warning-fidelity probes do **not** need per-commodity
duplication — the string is identical, so a wine-rendered title-case probe
would measure nothing the DS probe doesn't. What the live eval *does* need is
proof that extraction reads the same fields off visually different (wine/malt)
labels — see §8.

**Net:** if a category-specific rule could not be supported without expanding
the contract, the brief says mark it `not_evaluated`. Exactly one wanted-but-
unsupported check hits that bar — malt low-alcohol claim verification — and it
is `not_evaluated` for an independent reason (no lab ABV) regardless. So the
contract holds with zero additions.

---

## 6. UX vocabulary and notices

The governing requirement (brief §4): *a reviewer must never mistake partial
wine/malt review for full category compliance.*

**Verdict vocabulary — keep the enum, remap the wine/malt labels (inference).**
Keep `pass` / `needs_review` / `fail` as the internal three-valued model and
as the *rendered* labels for distilled spirits (full coverage). For wine and
malt, render the same underlying verdict with partial-aware top-line text:

| Internal verdict | DS render | Wine/malt render |
|---|---|---|
| `pass` | **Pass** | **No issue found in checked rules** |
| `needs_review` | **Needs review** | **Needs agent review** |
| `fail` | **Fail** | **Issue found** |

This is a presentation-layer mapping, not a contract change — the API still
returns `pass`/`needs_review`/`fail`. The wine/malt phrasing removes the word
"Pass," which is the word that could be misread as "compliant."

**Distinguishing full from partial coverage.** A persistent **coverage badge**
on every result: `Full coverage` (distilled spirits) vs `Partial coverage`
(wine, malt). The badge is not dismissible and appears in both single and
batch views.

**Notice next to the beverage-type control (exact copy, inference):**
> Wine and malt beverage review is **partial**. This prototype checks the
> brand name, class/type, alcohol statement, net contents, name/address,
> country of origin, and the government health warning. Category-specific
> rules (appellations, standards of fill, ingredient declarations, low-
> alcohol claims) are **not evaluated** — they are listed in the results, not
> silently skipped. Distilled spirits review is the fully built-out path.

**Result-banner notice for wine/malt (exact copy, inference):**
> Partial coverage — wine. No issue was found in the N rules this prototype
> checks. M category-specific rules were **not evaluated** (see below). This
> is not a finding of full label compliance.

**Per-rule `not_evaluated` rendering.** A distinct neutral (grey) row, never
green: `Not evaluated — [plain-language reason]. [citation].` Example:
`Not evaluated — wine appellation-of-origin requirements are outside this
prototype's scope. 27 CFR 4.25.` Rendering these as engine *findings* (via
the WN-SCOPE / MB-SCOPE rules) rather than static page text is deliberate:
they then flow through the same `findings[]` channel into the API, the batch
rows, and the expandable detail — impossible to show one surface and forget
another.

**`not_evaluated` vs `not_applicable` — count them separately. Yes.** They
mean different things and must read differently:

- `not_applicable` = the rule does not apply to *this label* (DS-7 not
  imported; DS-8 no proof; WN-3's table-wine branch is *evaluated*, so not
  this). Quiet, expected, folded into a small "n/a" tally.
- `not_evaluated` = the rule *applies to this commodity* but this prototype
  does not perform it. Loud, must be visible, counted on its own.

Counts line becomes, e.g.: `0 fail · 0 review · 5 pass · 4 not evaluated`
(with `n/a` shown small or on hover). This requires adding `not_evaluated` to
the `Outcome` enum and `Counts` (§9).

---

## 7. Batch compatibility

- **Accepted `beverage_type` values:** `distilled_spirits`, `wine`,
  `malt_beverage`. Internal category name is `malt_beverage` everywhere
  (regs, code, CSV, contract); UI may show "Beer / malt beverage" in the
  human-facing control only (per brief).
- **Manifest template changes:** the template's example rows expand to one
  per category so the accepted values are self-documenting. `abv_percent`
  stays required in the manifest (the COLA application still records intended
  ABV even when the *label* may omit it — that asymmetry is what WN-3/MB-3
  exploit). No new columns: the existing schema already carries everything.
- **Row validation for unknown/unsupported types:** currently
  `batch.py` rejects any non-`distilled_spirits` value as a **row error**
  (operational, outside the verdict model). After expansion, `wine` and
  `malt_beverage` become *valid*; an unknown string (e.g. `cider`,
  `seltzer`) stays a row error with a clear message listing the three
  accepted values. Row errors remain reported and counted separately, above
  verdicts (contracts.md §2 unchanged).
- **Demo batch mixing categories: yes.** The demo batch should include
  distilled spirits, wine, and malt rows together — it is the most honest
  single artifact for showing partial coverage side-by-side with full
  coverage (see §8).
- **Partial-coverage notice in streamed rows:** each wine/malt row carries
  the `Partial coverage` badge inline in the results table, and its expanded
  detail shows the `not_evaluated` scope rows. The live counts line is
  per-batch; a row's own counts show its `not_evaluated` tally.
- **Sorting:** `not_evaluated`, like `not_applicable`, is **excluded from the
  worst-of aggregation** — it is not a finding *against* the label. So a wine
  row with all-passes-plus-not-evaluated sorts into the **pass tier**, not
  demoted. Demoting partial-coverage labels below clean DS passes would
  punish wine for the prototype's scope, not for any label defect. The badge,
  not the sort order, carries the partial-coverage signal. (Confirmed
  consistent with the existing `fail > needs_review > pass` ordering;
  `not_evaluated` joins `not_applicable` as aggregation-neutral.)

---

## 8. Golden / demo expansion

Each case states: purpose · application fields · label fields · expected
findings · target layer. **Target layer** is one of: **CI** (deterministic
faithful-extraction test in `golden/faithful_extractions.json` — proves the
engine maps fields → outcomes), **eval** (live vision-model run — proves
extraction reads non-bourbon imagery), **demo** (shipped sample asset).
Most wine/malt cases are engine-and-dispatch logic, so they belong primarily
in **CI**; a thin slice goes to **eval** to prove extraction generalizes off
the bourbon label; the mixed batch goes to **demo**.

1. **`wine-compliant-table`** — *no issue in checked rules.*
   - Purpose: shared rules pass on a wine label; WN-SCOPE emits visible
     `not_evaluated` rows.
   - Application: `beverage_type=wine`, brand "VALLEY CREST", class "California
     Table Wine", `abv_percent=12.5`, net "750 mL", imported false.
   - Label: brand + "Table Wine" designation, **no numeric ABV** (lawful
     ≤14%), net contents, name/address, full correct warning.
   - Expected: WN-1/2/4/5/6 pass; WN-3 `pass` (omission lawful at ≤14% with
     table-wine designation — *not* a `needs_review`, because the designation
     is present); WN-7 `not_applicable`; WN-SCOPE `not_evaluated`.
   - Layer: **CI + eval + demo.**

2. **`wine-high-abv-missing-statement`** — *category-specific wine issue
   (`fail`).*
   - Purpose: prove WN-3's mandatory-above-14% branch can autonomously `fail`.
   - Application: `beverage_type=wine`, brand "VALLEY CREST", class "Napa
     Valley Cabernet Sauvignon", `abv_percent=15.5`, net "750 mL".
   - Label: brand, varietal designation, net, name/address, full warning,
     **no alcohol statement.**
   - Expected: WN-3 `fail` / `missing` (>14% ⇒ statement mandatory, § 4.36(a));
     other shared rules pass; WN-SCOPE `not_evaluated`.
   - Layer: **CI + eval.** (The decidable wine defect; worth a live read.)

3. **`malt-compliant`** — *no issue in checked rules.*
   - Purpose: shared rules pass on a malt label; MB-3 handles a *present*
     optional ABV.
   - Application: `beverage_type=malt_beverage`, brand "NORTHGATE", class
     "India Pale Ale", `abv_percent=6.8`, net "12 FL OZ".
   - Label: brand, "India Pale Ale", "6.8% ALC/VOL", net, name/address,
     full warning.
   - Expected: all shared rules pass; MB-3 `pass`; MB-SCOPE `not_evaluated`.
   - Layer: **CI + eval + demo.**

4. **`malt-abv-mismatch`** — *category-specific malt issue (`fail`).*
   - Purpose: prove MB-3 consistency band (`±0.3 pp`) can `fail` when the
     label ABV disagrees with the application beyond tolerance.
   - Application: `beverage_type=malt_beverage`, `abv_percent=5.0`, brand
     "NORTHGATE", class "Lager", net "12 FL OZ".
   - Label: identical except "7.5% ALC/VOL" (2.5 pp off).
   - Expected: MB-3 `fail` / `mismatch`; shared rules pass.
   - Layer: **CI.** (Pure band logic; faithful extraction suffices.)

5. **`malt-abv-omitted`** — *proves optional-ABV is `needs_review`, never
   `fail`.*
   - Purpose: the malt counterpart to the wine ≤14% allowance — a missing
     malt ABV must not `fail`.
   - Application: `beverage_type=malt_beverage`, `abv_percent=4.5`, net
     "12 FL OZ".
   - Label: brand, "Lager", net, name/address, full warning, **no ABV.**
   - Expected: MB-3 `needs_review` / `missing` (optional per § 7.65(a));
     shared rules pass.
   - Layer: **CI.**

6. **`wine-not-evaluated-visible`** — *proves `not_evaluated` rows render.*
   - This is an assertion overlaid on case 1, not a separate label: the
     `wine-compliant-table` manifest entry explicitly expects
     `WN-SCOPE: { outcome: not_evaluated }`, and `tests/test_demo.py` /
     the golden integrity test assert at least one `not_evaluated` finding
     surfaces in the rendered result. (The brief's "at least one case that
     proves not-evaluated rows are visible" is satisfied without a bespoke
     label.)
   - Layer: **CI + demo.**

7. **`mixed-category-batch`** — *batch mixing all three commodities.*
   - Purpose: one zip with distilled-spirits rows (reuse existing goldens),
     `wine-compliant-table`, `wine-high-abv-missing-statement`,
     `malt-compliant`, `malt-abv-mismatch`, plus one **unknown-type row**
     (`beverage_type=cider`) to show the row-error path. Demonstrates full vs
     partial coverage badges, mixed verdicts, and `not_evaluated` counts in
     one streamed table.
   - Layer: **demo** (and a CI batch-parser test for the cider row error).

**Honesty note on imagery (inference):** rendering convincing wine and malt
label images is real work — the existing `golden/generate.py` renders a
bourbon-shaped label. Minimum viable: one wine and one malt live-eval case
each (cases 1–3 above), so the eval proves extraction generalizes; the rest
can be CI-only with hand-written `faithful_extractions.json` entries that
need no imagery. This keeps P2 bounded.

---

## 9. Architecture impact

Direction confirmed: **separate rule lists per category, composed from shared
helpers.** Concrete touch-points:

- **Engine types (`engine/types.py`):**
  - `BeverageType`: add `WINE = "wine"`, `MALT_BEVERAGE = "malt_beverage"`.
  - `Outcome`: add `NOT_EVALUATED = "not_evaluated"` (distinct from
    `NOT_APPLICABLE`). Aggregation in `engine.py` must treat it like
    `not_applicable` — skipped in the worst-of verdict.
  - `Counts`: add `not_evaluated: int`.
  - No change to `ExtractionResult` (the §5 finding — zero new fields).
- **Parser functions (`engine/parsers.py`):** `parse_abv_statement` is reused
  as-is. The only new logic is per-commodity *bands*, which belong in the
  rule, not the parser. No new parser unless the MB low-alcohol claims check
  is later adopted.
- **Rules (`engine/rules.py`):** refactor the implicit DS helpers into
  commodity-parameterized shared functions (brand, class/type, net contents,
  name/address, origin, and the whole warning family take a `citation`/scope
  argument). Build three lists — `DS_RULES`, `WINE_RULES`, `MALT_RULES` — and
  add `WN-3`, `MB-3`, `WN-SCOPE`, `MB-SCOPE`. Replace the single `ALL_RULES`
  with a `RULES_BY_TYPE: dict[BeverageType, list[RuleFn]]`.
- **Review dispatch (`engine/engine.py`):** `review()` selects the rule list
  via `RULES_BY_TYPE[application.beverage_type]`; aggregation skips
  `not_evaluated` alongside `not_applicable`. The single-vs-batch pipeline
  (`pipeline.py`) is untouched — both already route through `review()`.
- **API & UI forms (`main.py`, templates):** add a beverage-type selector to
  the single-review form (default distilled spirits); add the coverage badge,
  banner notices, and `not_evaluated` row rendering to
  `templates/partials/{results,findings,batch_row}.html`.
- **Batch parser (`batch.py`):** accept `wine`/`malt_beverage`; keep unknown
  types as row errors; expand the template example rows.
- **Demo builder (`golden/build_demo.py`):** add the wine/malt single-review
  assets and the mixed-category demo batch; update the "what you should see"
  copy.
- **Golden manifest & faithful extractions (`golden/manifest.json`,
  `golden/faithful_extractions.json`):** add cases 1–7; bump
  `MANIFEST_VERSION` (forces a demo rebuild via `tests/test_demo.py`).
- **Docs:** promote the Part 4 / Part 7 stubs in
  [ttb-requirements.md](ttb-requirements.md) into full rule sections (WN-/MB-
  with citations and outcome dispositions); add `not_evaluated` to the
  outcome model and `wine`/`malt_beverage` to the contract enum in
  [contracts.md](contracts.md); record the decisions below in
  [decisions.md](decisions.md); update README scope + known-limitations from
  "distilled spirits only" to "distilled spirits (full) + wine/malt
  (partial)."

**New decisions to record (D-12…D-15, inference):**
- D-12 — Partial coverage is a first-class, visible posture (badge + scope-
  marker rules), not a README footnote.
- D-13 — `not_evaluated` is a distinct outcome from `not_applicable`;
  aggregation-neutral but separately counted and rendered.
- D-14 — Zero new extraction fields; wine/malt are an engine+UX expansion.
- D-15 — Per-category rule lists composed from shared helpers; alcohol-content
  band is the per-commodity parameter.

---

## 10. Cut line

Out of scope for this expansion, even though nearby. Each becomes a visible
`not_evaluated` finding (via WN-SCOPE / MB-SCOPE) with plain language +
citation — never a silent omission.

- **Wine:** appellation of origin (§ 4.25), vintage date (§ 4.27), varietal/
  grape-type designations (§ 4.23), semi-generic and geographic names
  (§ 4.24), standards of fill (§ 4.72), sulfite declaration (§ 4.32(e) — its
  ≥ 10 ppm trigger is a lab fact, not on the label face), class/type
  *lawfulness* validation.
- **Malt:** "non-alcoholic" / "low alcohol" / "alcohol free" claim
  verification (§ 7.65(b)(3)–(5) — needs lab ABV), the added-flavor trigger
  that makes ABV mandatory (§ 7.65(a) — needs ingredient knowledge),
  sulfite/FD&C Yellow 5/aspartame/cochineal disclosures (§ 7.63(b)),
  standards of fill, class/type lawfulness.
- **Both / carried over:** type-size, legibility, contrasting-background
  (not measurable from an unscaled image); same-field-of-vision (§ 4.39(a) /
  § 7.61 — untagged multi-image contract can't verify); FDA-jurisdiction
  edges (wine < 7% ABV; "beer" without malted barley/hops); COLA integration
  and permit verification.

The cut line's job (per the brief): keep this from becoming broad-but-
unverified compliance software. The discipline is "narrow and decidable,
loudly honest about the rest" — every cut item is a labeled `not_evaluated`
row, so partial coverage is self-documenting in the product, not just the
docs.

---

## 11. Implementation plan candidates

Two phases, matching the project's "complete core over ambitious sprawl"
posture (D-9). P1 is shippable on its own and is the load-bearing correctness
work; P2 is evaluation breadth.

**Phase 1 — engine, dispatch, and UI (the 80/20 core).**
1. Types: `BeverageType` wine/malt; `Outcome.NOT_EVALUATED`; `Counts.not_evaluated`.
2. Refactor DS rules into shared commodity-parameterized helpers; build
   `RULES_BY_TYPE`; add WN-3, MB-3, WN-SCOPE, MB-SCOPE.
3. `engine.review()` dispatch by beverage type; aggregation skips
   `not_evaluated`.
4. Rule-engine unit tests over the new band/branch boundaries (wine >14 vs
   ≤14 missing-ABV; malt present/omitted/mismatch) — deterministic, no API.
5. Single-review form selector; coverage badge; banner + scope-row rendering;
   wine/malt verdict relabeling.
6. Batch parser accepts wine/malt; unknown → row error; template example rows.
7. Docs: promote requirement stubs, update contract enum + outcome model,
   record D-12…D-15, update README scope.

**Phase 2 — golden / demo / eval breadth.**
8. Author `faithful_extractions.json` entries for cases 1–7 (CI-deterministic).
9. Render wine + malt label imagery for the live-eval cases (1–3);
   `golden/generate.py` extension.
10. Mixed-category demo batch via `build_demo.py`; update "what you should
    see" copy; bump `MANIFEST_VERSION`.
11. Run the live eval on the new wine/malt images; record a fresh scoreboard
    row (the warning-fidelity probes are unchanged — same canonical string —
    so the fidelity claim transfers without re-measuring).

**Pre-agreed cut order within this expansion (inference, mirrors D-9):** if
time-boxed, cut P2 imagery first (ship CI-only wine/malt with the engine and
UI fully built and honest scope markers visible), then the mixed demo batch,
then the live-eval rows. **Never cut:** the `not_evaluated` outcome and scope-
marker rules (they are the honesty mechanism), the per-category dispatch, and
the partial-coverage UI badge — without those, partial coverage becomes the
silent-omission failure the brief explicitly forbids.

---

## Sources

Primary (verified 2026-06-13, eCFR text + Cornell LII mirror):

- 27 CFR Part 4 (Wine): §§ 4.32 (mandatory info), 4.33 (brand), 4.34
  (class/type), 4.35 (name/address), 4.36 (alcohol content — 1% / 1.5%
  tolerances; mandatory > 14%; table/light wine allowance), 4.37 (net
  contents), 4.72 (standards of fill).
  <https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-4>
- 27 CFR Part 7 (Malt Beverages, post-TTB-188): §§ 7.63 (mandatory info),
  7.64 (brand), 7.65 (alcohol content — optional unless added-flavor alcohol;
  ±0.3 pp; low/non/free-alcohol claims), 7.66–7.68 (name/address), 7.70 (net
  contents), Subpart I (designations).
  <https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-7>
- 27 CFR Part 16 (Health Warning Statement) — commodity-independent; applies
  ≥ 0.5% ABV (16.10, 16.20); 16.21 text; 16.22 format.
  <https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16>
- 19 CFR Parts 102 & 134 (country-of-origin marking for imports).
- TTB malt-beverage labeling guidance (mandatory-info and alcohol-content
  checklists): <https://www.ttb.gov/regulated-commodities/beverage-alcohol/beer/labeling>

Internal: [project-description.md](project-description.md),
[ttb-requirements.md](ttb-requirements.md), [contracts.md](contracts.md),
[decisions.md](decisions.md), [../README.md](../README.md),
[wine-malt-research-brief.md](wine-malt-research-brief.md).
