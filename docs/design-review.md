# Design Review

Review of [build-brief.md](build-brief.md) against the project context in
[project-description.md](project-description.md). This is a product and
design review, not a technical implementation review.

## Overall Assessment

The build brief is well aligned with the project description. It correctly
reads the assignment as more than "use AI on labels": the real product need is
a fast, low-friction decision-support tool for overburdened compliance agents,
with careful handling of trust, batch work, warning-statement exactness, and
government deployment realities.

The brief's strongest design choice is to treat AI as an extraction mechanism,
not as the compliance authority. That choice fits the stakeholder context: the
agents are drowning in routine comparison work, but they still need judgment,
evidence, and confidence that the tool is not inventing regulatory conclusions.

## Alignment With Project Needs

| Project need | Source signal | Build brief response | Assessment |
|---|---|---|---|
| Routine matching should be automated | Sarah describes agents manually comparing application fields to label artwork and spending much of the day on data-entry verification. | Deterministic rule engine after AI extraction; DS-1-DS-8 checks; expected/actual evidence in results. | Strong. This respects the work pattern instead of making the AI the judge. |
| Must be fast enough to use | Prior vendor pilot failed because 30-40 second processing was slower than visual review; Sarah says results need to come back in about 5 seconds. | Single-label target is about 5 seconds; batch uses time-to-first-result streaming. | Strong, with a reasonable documented assumption. Batch "5 seconds" is interpreted pragmatically rather than literally. |
| Must be simple for mixed tech comfort | Sarah asks for something "my mother could figure out" and notes that agents vary widely in comfort with technology. | Single review UI is the polished path; results emphasize verdict, counts, and evidence. | Directionally strong, but the brief could translate this into more concrete UX acceptance criteria. |
| Batch uploads matter | Peak-season importers may submit 200-300 labels at once, and current processing is one-by-one. | Zip plus CSV batch flow, template download, SSE streaming results, and worst-first sorting. | Strong. CSV plus zip is less friendly than direct folder upload, but it is reasonable for a prototype and a government-adjacent workflow. |
| No direct COLA integration | Marcus says the prototype should not integrate directly with COLA and should stand alone. | Standalone deployed app with application form and CSV manifest input. | Strong. Avoids overbuilding and fits the proof-of-concept scope. |
| Federal/security constraints matter | Marcus notes Azure/FedRAMP context, future PII and retention concerns, and network blocks on many outbound domains. | Model adapter, single OCI container, vendored static assets, no runtime outbound dependency except the model API, and stateless upload handling. | Very strong for a prototype. The federal transition story is one of the brief's best decisions. |
| Nuance and human judgment are required | Dave gives the STONE'S THROW example and says some apparent mismatches need judgment. | Fuzzy matching, `needs_review`, visual rules that cannot fail, and evidence-first UI. | Strong. Directly addresses the concern that automation could make agents' work harder. |
| Warning text exactness is critical | Jenny says the health warning must be exact and calls out title-case "Government Warning" as a real rejection scenario. | DS-5 subchecks, canonical warning excluded from prompts, title-case golden case, and character diff on DS-5a. | Excellent. The brief identifies the subtle AI failure mode where a model may normalize bad warning text toward the canonical text. |
| Imperfect label images are common | Jenny mentions weird angles, poor lighting, and glare. | Golden degraded/skewed image, illegibility threshold, and `needs_review` rather than `fail` for unreadable evidence. | Good. The brief does not overpromise image rescue, which is appropriate. |
| Complete core beats ambitious incompleteness | The project description explicitly says a working core application with clean code is preferred over ambitious but incomplete features. | Deployable milestones, pre-agreed cut order, and done criteria tied to single plus batch review. | Strong. The sequencing is disciplined. |

## Strengths

### Decision-Support, Not Decision-Making

The "AI extracts, code decides" model is a trust strategy as much as an
architecture strategy. It lets skeptical agents see what was read, what was
expected, and why the tool reached a result. That fits the stakeholder reality:
agents need acceleration, not an opaque replacement for their judgment.

### Three-Valued Outcomes

The `pass` / `fail` / `needs_review` model matches the real workflow better
than a binary approval model. It protects the prototype from pretending
certainty when the interviews clearly call for judgment, especially around
fuzzy text differences, visual layout, and illegible images.

### Strong Handling of the Warning Statement

The build brief gives the government warning the right level of attention. It
does not merely ask the model whether the warning is correct; it anticipates
the more dangerous failure mode that the model may silently "correct" the
warning while transcribing it. Keeping the canonical warning text out of the
prompt and measuring extraction fidelity with targeted golden cases is a
thoughtful response to Jenny's exactness requirement.

### Operationally Useful Batch Flow

Sorting batch results by severity and showing row-level errors turns batch
upload from a bulk-processing checkbox into a real queue-management aid. This
is well matched to Sarah's peak-season importer scenario.

### Credible Federal Transition Story

The brief does not pretend that Fly.io plus a commercial model API is the final
government deployment shape. The adapter boundary, vendored assets, stateless
processing, and containerized deployment give the prototype a plausible path
to a future federal environment without forcing that complexity into the
take-home build.

## Gaps and Risks

| Gap or risk | Why it matters | Suggested adjustment |
|---|---|---|
| The UI requirement is still abstract. | "Sarah's mother test" is named, but not translated into concrete interface constraints. | Add 5-7 UX acceptance criteria: one primary action per screen, plain-language verdicts, no regulatory jargon in table headers, visible upload status, obvious retry path, and a printable or shareable result. |
| Batch input may feel technical. | Zip plus CSV is efficient, but agents with lower technical comfort may find it intimidating. | Keep the contract, but make the template central. The UI should show an example row, validate early, and explain row-level errors in plain language. |
| Distilled-spirits-only scope may surprise evaluators. | The project description mentions beer, wine, and spirits generally, even though the sample label is bourbon. | The README should make the tradeoff prominent: the prototype implements distilled spirits first because correctness is more valuable than shallow coverage. |
| "Fail" could sound like final agency rejection. | The stated design is decision support, not autonomous decision-making. | Consider user-facing labels such as "Likely issue," "Needs agent review," and "No issue found," while keeping internal outcomes precise. |
| Warning validation could dominate the demo. | DS-5 is important, but the original workflow also values brand, ABV, net contents, and routine match checks. | Ensure the golden set and demo path include mundane passes, simple mismatches, imported labels, and batch triage, not only adversarial warning cases. |
| There is no explicit agent correction loop. | If extraction is wrong, agents need a graceful way to understand or challenge the result. | At minimum, show extracted evidence clearly. As a later enhancement, allow users to mark "AI read this wrong" for feedback, even if the prototype does not persist corrections. |

## Recommendation

Proceed with the build brief as the implementation guide. It captures the most
important stated and unstated requirements: speed, simplicity, batch handling,
human judgment, exact warning validation, and future federal constraints.

Before implementation, add a short UX acceptance section to the build brief or
README plan. The current design is rigorous about rules, contracts, and
architecture; the main remaining risk is that the app could become technically
correct but visually dense or intimidating for the intended agents.
