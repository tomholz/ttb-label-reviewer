"""DS-1–DS-8 as pure functions over (application record, extraction
result). docs/ttb-requirements.md is the source of truth for outcomes,
reasons, and citations; no I/O and no model calls happen here (D-1).

Outcome routing the requirements leave open, decided here:

- Missing mandatory fields (DS-1, DS-2, DS-3, DS-6, DS-7-when-imported)
  → fail/missing. DS-4 is the explicit exception (needs_review — net
  contents may be blown into the glass) and DS-5c/5d are visual-mode
  (fail unavailable by construction).
- Unparseable statement strings → needs_review/illegible: the field was
  found but can't be compared, which is the illegible situation even if
  the pixels were crisp.
"""

import re
from collections.abc import Callable

from .canonical import CANONICAL_LEAD_IN, CANONICAL_WARNING
from .diff import char_diff
from .normalize import normalize_fuzzy, normalize_warning
from .parsers import parse_abv_statement, parse_net_contents, parse_proof
from .types import (
    ApplicationRecord,
    BeverageType,
    EngineConfig,
    ExtractedField,
    ExtractionResult,
    Finding,
    Outcome,
    Reason,
    TriState,
)

RuleFn = Callable[[ApplicationRecord, ExtractionResult, EngineConfig], Finding]

_LEAD_IN = re.compile(r"government\s+warning", re.IGNORECASE)
# "alc" then "vol" in either order covers "45% Alc./Vol.", "ALC. 45% BY
# VOL.", and "45% alcohol by volume"; "ABV" is deliberately not matched
# (not a permitted abbreviation under 5.65(a)).
_ABV_FORM = re.compile(r"alc.*vol|vol.*alc", re.IGNORECASE | re.DOTALL)
_FLOAT_EPSILON = 1e-6


def _builder(rule_id: str, rule_name: str, citation: str):
    def build(
        outcome: Outcome,
        explanation: str,
        *,
        reason: Reason | None = None,
        expected: str | None = None,
        actual: str | None = None,
        diff=None,
    ) -> Finding:
        return Finding(
            rule_id=rule_id,
            rule_name=rule_name,
            citation=citation,
            outcome=outcome,
            reason=reason,
            expected=expected,
            actual=actual,
            explanation=explanation,
            diff=diff,
        )

    return build


def _illegible(build, label: str, field: ExtractedField, expected: str | None):
    return build(
        Outcome.NEEDS_REVIEW,
        f"{label} was located but extraction confidence "
        f"({field.confidence:.2f}) is too low to compare.",
        reason=Reason.ILLEGIBLE,
        expected=expected,
        actual=field.raw,
    )


def _fuzzy_consistency(
    build,
    label: str,
    expected_value: str,
    field: ExtractedField | None,
    config: EngineConfig,
) -> Finding:
    """Shared body of DS-1 and DS-2 (consistency, fuzzy match_mode)."""
    if field is None:
        return build(
            Outcome.FAIL,
            f"{label} not found on any provided label image.",
            reason=Reason.MISSING,
            expected=expected_value,
        )
    if field.confidence < config.illegibility_threshold:
        return _illegible(build, label, field, expected_value)
    if field.raw == expected_value:
        return build(
            Outcome.PASS,
            f"{label} matches the application exactly.",
            expected=expected_value,
            actual=field.raw,
        )
    if normalize_fuzzy(field.raw) == normalize_fuzzy(expected_value):
        return build(
            Outcome.NEEDS_REVIEW,
            f"{label} matches the application except for case or punctuation "
            "— likely the same thing, but that is a human call.",
            reason=Reason.MISMATCH,
            expected=expected_value,
            actual=field.raw,
        )
    return build(
        Outcome.FAIL,
        f"{label} disagrees with the application.",
        reason=Reason.MISMATCH,
        expected=expected_value,
        actual=field.raw,
    )


def ds1_brand_name(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("DS-1", "Brand name", "27 CFR 5.63, 5.64")
    return _fuzzy_consistency(
        build, "Brand name", app.brand_name, ext.brand_name, config
    )


def ds2_class_type(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("DS-2", "Class/type designation", "27 CFR 5.63(a)")
    return _fuzzy_consistency(
        build, "Class/type designation", app.class_type, ext.class_type, config
    )


def ds3_alcohol_content(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("DS-3", "Alcohol content", "27 CFR 5.65(a)–(c)")
    expected = f"{app.abv_percent:g}% alcohol by volume"
    field = ext.alcohol_content
    if field is None:
        return build(
            Outcome.FAIL,
            "No alcohol content statement found on any provided label image.",
            reason=Reason.MISSING,
            expected=expected,
        )
    if field.confidence < config.illegibility_threshold:
        return _illegible(build, "Alcohol content statement", field, expected)
    value = parse_abv_statement(field.raw)
    if value is None:
        return build(
            Outcome.NEEDS_REVIEW,
            "An alcohol content statement was found but no percentage could "
            "be parsed from it.",
            reason=Reason.ILLEGIBLE,
            expected=expected,
            actual=field.raw,
        )
    # Design caveat (ttb-requirements.md DS-3): the ±0.3 pp tolerance in
    # 27 CFR 5.65(c) governs label vs. product *as analyzed* — a production
    # tolerance, not a paperwork tolerance. Application and label should
    # state the same number, so pass requires an exact match; the 0.3 pp
    # figure is borrowed purely as the design-chosen boundary between
    # "human judgment" (needs_review) and "clear mismatch" (fail).
    delta = abs(value - app.abv_percent)
    if delta < _FLOAT_EPSILON:
        # Required form is "__% alcohol by volume" (abbreviations alc, %,
        # /, vol permitted — 5.65(a)). A matching number without that
        # language (bare "45%", "45% ABV") routes to needs_review, not
        # fail: absent words in an extracted span may be extraction
        # truncation rather than a label defect, while the matched number
        # is robust evidence.
        if not _ABV_FORM.search(field.raw):
            return build(
                Outcome.NEEDS_REVIEW,
                "Label ABV matches the application, but the statement does "
                'not appear to use the required "% alcohol by volume" form '
                "(or a permitted abbreviation such as Alc./Vol.).",
                reason=Reason.FORMAT,
                expected=expected,
                actual=field.raw,
            )
        return build(
            Outcome.PASS,
            "Label ABV matches the application.",
            expected=expected,
            actual=field.raw,
        )
    if delta <= 0.3 + _FLOAT_EPSILON:
        return build(
            Outcome.NEEDS_REVIEW,
            f"Label ABV ({value:g}%) differs from the application "
            f"({app.abv_percent:g}%) by {delta:.1f} points — within 0.3, "
            "so it gets a human look rather than an automatic fail.",
            reason=Reason.MISMATCH,
            expected=expected,
            actual=field.raw,
        )
    return build(
        Outcome.FAIL,
        f"Label ABV ({value:g}%) differs from the application "
        f"({app.abv_percent:g}%) by {delta:.1f} points.",
        reason=Reason.MISMATCH,
        expected=expected,
        actual=field.raw,
    )


def ds4_net_contents(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("DS-4", "Net contents", "27 CFR 5.63(b)(2), 5.70")
    return _net_contents_check(build, app.net_contents, ext.net_contents, config)


def _net_contents_check(
    build,
    app_value: str,
    field: ExtractedField | None,
    config: EngineConfig,
) -> Finding:
    if field is None:
        # Never fail on missing: 5.63(b)(2) permits net contents blown,
        # embossed, or molded into the container, which a label-image-only
        # review cannot see.
        return build(
            Outcome.NEEDS_REVIEW,
            "Net contents not found on any label image — but it may be "
            "blown, embossed, or molded into the container itself, which "
            "this review cannot see.",
            reason=Reason.MISSING,
            expected=app_value,
        )
    if field.confidence < config.illegibility_threshold:
        return _illegible(build, "Net contents", field, app_value)
    expected_parsed = parse_net_contents(app_value)
    actual_parsed = parse_net_contents(field.raw)
    if expected_parsed is not None and actual_parsed is not None:
        (exp_value, exp_unit), (act_value, act_unit) = expected_parsed, actual_parsed
        if exp_unit == act_unit and abs(exp_value - act_value) < _FLOAT_EPSILON:
            return build(
                Outcome.PASS,
                "Net contents matches the application.",
                expected=app_value,
                actual=field.raw,
            )
        return build(
            Outcome.FAIL,
            "Net contents disagrees with the application.",
            reason=Reason.MISMATCH,
            expected=app_value,
            actual=field.raw,
        )
    # One side didn't parse: fall back to fuzzy string comparison and
    # never fail on a comparison the parser didn't understand.
    if normalize_fuzzy(field.raw) == normalize_fuzzy(app_value):
        return build(
            Outcome.PASS,
            "Net contents matches the application.",
            expected=app_value,
            actual=field.raw,
        )
    return build(
        Outcome.NEEDS_REVIEW,
        "Net contents could not be parsed for numeric comparison and the "
        "strings differ — needs a human look.",
        reason=Reason.MISMATCH,
        expected=app_value,
        actual=field.raw,
    )


def ds5a_warning_text(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("DS-5a", "Government warning text", "27 CFR 16.21")
    return _warning_text_check(build, ext, config)


def _warning_text_check(build, ext: ExtractionResult, config: EngineConfig) -> Finding:
    canonical = normalize_warning(CANONICAL_WARNING)
    warning = ext.government_warning
    if warning is None:
        return build(
            Outcome.FAIL,
            "No government health warning found on any provided label image.",
            reason=Reason.MISSING,
            expected=canonical,
        )
    if warning.confidence < config.illegibility_threshold:
        return build(
            Outcome.NEEDS_REVIEW,
            "A government warning was located but extraction confidence "
            f"({warning.confidence:.2f}) is too low for a verbatim comparison.",
            reason=Reason.ILLEGIBLE,
            expected=canonical,
            actual=warning.raw_text,
        )
    actual = normalize_warning(warning.raw_text)
    # Case-insensitive comparison: 16.22(a) mandates capitals only for the
    # lead-in words, which DS-5b checks case-sensitively.
    if actual.lower() == canonical.lower():
        return build(
            Outcome.PASS,
            "Warning text matches the required statement word for word.",
            expected=canonical,
            actual=actual,
        )
    return build(
        Outcome.FAIL,
        "Warning text deviates from the required statement.",
        reason=Reason.MISMATCH,
        expected=canonical,
        actual=actual,
        diff=char_diff(canonical, actual),
    )


def ds5b_lead_in_caps(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("DS-5b", "GOVERNMENT WARNING capitalization", "27 CFR 16.22(a)(2)")
    return _lead_in_caps_check(build, ext, config)


def _lead_in_caps_check(build, ext: ExtractionResult, config: EngineConfig) -> Finding:
    warning = ext.government_warning
    if warning is None:
        return build(
            Outcome.FAIL,
            "No government health warning found on any provided label image.",
            reason=Reason.MISSING,
            expected=CANONICAL_LEAD_IN,
        )
    if warning.confidence < config.illegibility_threshold:
        return build(
            Outcome.NEEDS_REVIEW,
            "Warning located but extraction confidence "
            f"({warning.confidence:.2f}) is too low to judge capitalization.",
            reason=Reason.ILLEGIBLE,
            expected=CANONICAL_LEAD_IN,
        )
    match = _LEAD_IN.search(warning.raw_text)
    if match is None:
        return build(
            Outcome.FAIL,
            'The words "GOVERNMENT WARNING" do not appear in the warning text.',
            reason=Reason.MISSING,
            expected=CANONICAL_LEAD_IN,
            actual=warning.raw_text,
        )
    found = re.sub(r"\s+", " ", match.group(0))
    if found == CANONICAL_LEAD_IN:
        return build(
            Outcome.PASS,
            '"GOVERNMENT WARNING" appears in capital letters as required.',
            expected=CANONICAL_LEAD_IN,
            actual=found,
        )
    return build(
        Outcome.FAIL,
        'The warning lead-in must read "GOVERNMENT WARNING" in capital '
        f'letters; the label uses "{found}".',
        reason=Reason.FORMAT,
        expected=CANONICAL_LEAD_IN,
        actual=found,
    )


def ds5c_bold(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    # visual match_mode: outcomes restricted to pass/needs_review by
    # construction — no path to fail exists in this function.
    build = _builder(
        "DS-5c", "GOVERNMENT WARNING bold formatting", "27 CFR 16.22(a)(2)"
    )
    return _warning_bold_check(build, ext, config)


def _warning_bold_check(build, ext: ExtractionResult, config: EngineConfig) -> Finding:
    # visual match_mode: outcomes restricted to pass/needs_review by
    # construction — no path to fail exists in this function.
    expected = '"GOVERNMENT WARNING" in bold type; remainder not bold'
    warning = ext.government_warning
    if warning is None:
        return build(
            Outcome.NEEDS_REVIEW,
            "No warning was found, so bold formatting could not be assessed.",
            reason=Reason.MISSING,
            expected=expected,
        )
    actual = (
        f"lead-in bold: {warning.lead_in_bold}; "
        f"remainder bold: {warning.remainder_bold}"
    )
    if warning.confidence < config.illegibility_threshold:
        return build(
            Outcome.NEEDS_REVIEW,
            "Warning located but extraction confidence is too low to judge "
            "bold formatting.",
            reason=Reason.ILLEGIBLE,
            expected=expected,
            actual=actual,
        )
    if warning.lead_in_bold is TriState.YES and warning.remainder_bold is TriState.NO:
        return build(
            Outcome.PASS,
            'The label shows "GOVERNMENT WARNING" in bold with the remainder not bold.',
            expected=expected,
            actual=actual,
        )
    if TriState.UNCERTAIN in (warning.lead_in_bold, warning.remainder_bold):
        return build(
            Outcome.NEEDS_REVIEW,
            "Bold formatting could not be determined confidently from the image.",
            reason=Reason.ILLEGIBLE,
            expected=expected,
            actual=actual,
        )
    return build(
        Outcome.NEEDS_REVIEW,
        "Bold formatting appears not to meet the requirement — boldness is a "
        "visual judgment, so this routes to a human rather than failing.",
        reason=Reason.FORMAT,
        expected=expected,
        actual=actual,
    )


def ds5d_placement(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    # visual match_mode: pass/needs_review only, same construction as DS-5c.
    build = _builder(
        "DS-5d", "Warning placement and layout", "27 CFR 16.21, 16.22(a)(3)"
    )
    return _warning_placement_check(build, ext, config)


def _warning_placement_check(
    build, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    # visual match_mode: pass/needs_review only, same construction as DS-5c.
    expected = "warning separate and apart from all other information"
    warning = ext.government_warning
    if warning is None:
        return build(
            Outcome.NEEDS_REVIEW,
            "No warning was found, so placement could not be assessed.",
            reason=Reason.MISSING,
            expected=expected,
        )
    actual = f"separate and apart: {warning.separate_and_apart}"
    if warning.confidence < config.illegibility_threshold:
        return build(
            Outcome.NEEDS_REVIEW,
            "Warning located but extraction confidence is too low to judge placement.",
            reason=Reason.ILLEGIBLE,
            expected=expected,
            actual=actual,
        )
    if warning.separate_and_apart is TriState.YES:
        return build(
            Outcome.PASS,
            "The warning appears as its own uninterrupted block, separate "
            "from other label text.",
            expected=expected,
            actual=actual,
        )
    reason = (
        Reason.ILLEGIBLE
        if warning.separate_and_apart is TriState.UNCERTAIN
        else Reason.FORMAT
    )
    return build(
        Outcome.NEEDS_REVIEW,
        "Warning placement could not be confirmed as separate and apart — "
        "layout is a visual judgment, so this routes to a human.",
        reason=reason,
        expected=expected,
        actual=actual,
    )


def _presence(
    build, label: str, field: ExtractedField | None, config: EngineConfig
) -> Finding:
    expected = f"{label} present on the label"
    if field is None:
        return build(
            Outcome.FAIL,
            f"{label} not found on any provided label image.",
            reason=Reason.MISSING,
            expected=expected,
        )
    if field.confidence < config.illegibility_threshold:
        return _illegible(build, label, field, expected)
    return build(
        Outcome.PASS,
        f"{label} is present.",
        expected=expected,
        actual=field.raw,
    )


def ds6_name_address(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("DS-6", "Name and address", "27 CFR 5.66–5.68")
    return _presence(build, "Name and address statement", ext.name_address, config)


def ds7_country_of_origin(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("DS-7", "Country of origin", "27 CFR 5.69")
    if not app.imported:
        return build(
            Outcome.NOT_APPLICABLE,
            "Product is not imported; no country-of-origin statement is required.",
        )
    return _presence(
        build, "Country-of-origin statement", ext.country_of_origin, config
    )


def ds8_proof_abv(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("DS-8", "Proof ↔ ABV consistency", "27 CFR 5.65(b)(1)(i)")
    proof_field = ext.proof
    if proof_field is None:
        return build(
            Outcome.NOT_APPLICABLE,
            "No proof statement appears on the label; nothing to cross-check.",
        )
    abv_field = ext.alcohol_content
    if proof_field.confidence < config.illegibility_threshold or (
        abv_field is not None and abv_field.confidence < config.illegibility_threshold
    ):
        return build(
            Outcome.NEEDS_REVIEW,
            "Proof or ABV extraction confidence is too low for the cross-check.",
            reason=Reason.ILLEGIBLE,
            actual=proof_field.raw,
        )
    if abv_field is None:
        return build(
            Outcome.NEEDS_REVIEW,
            "The label states a proof but no ABV statement was found to "
            "check it against.",
            reason=Reason.MISSING,
            actual=proof_field.raw,
        )
    proof_value = parse_proof(proof_field.raw)
    abv_value = parse_abv_statement(abv_field.raw)
    if proof_value is None or abv_value is None:
        return build(
            Outcome.NEEDS_REVIEW,
            "Proof or ABV statement could not be parsed for the cross-check.",
            reason=Reason.ILLEGIBLE,
            expected=abv_field.raw,
            actual=proof_field.raw,
        )
    expected = f"{2 * abv_value:g} proof (2 × {abv_value:g}% ABV)"
    if abs(proof_value - 2 * abv_value) < _FLOAT_EPSILON:
        return build(
            Outcome.PASS,
            "Stated proof is exactly twice the stated ABV.",
            expected=expected,
            actual=proof_field.raw,
        )
    # Never fail: a discrepancy is either a genuine label defect or an
    # extraction misread, and both warrant a human look. This rule doubles
    # as a free check on extraction quality.
    return build(
        Outcome.NEEDS_REVIEW,
        f"Stated proof ({proof_value:g}) is not twice the stated ABV "
        f"({abv_value:g}%) — either a label defect or an extraction misread; "
        "a human should look.",
        reason=Reason.MISMATCH,
        expected=expected,
        actual=proof_field.raw,
    )


def _abv_band_check(
    build,
    app: ApplicationRecord,
    field: ExtractedField,
    config: EngineConfig,
    *,
    tolerance: float,
    category_label: str,
) -> Finding:
    expected = f"{app.abv_percent:g}% alcohol by volume"
    if field.confidence < config.illegibility_threshold:
        return _illegible(build, "Alcohol content statement", field, expected)
    value = parse_abv_statement(field.raw)
    if value is None:
        return build(
            Outcome.NEEDS_REVIEW,
            "An alcohol content statement was found but no percentage could "
            "be parsed from it.",
            reason=Reason.ILLEGIBLE,
            expected=expected,
            actual=field.raw,
        )
    delta = abs(value - app.abv_percent)
    if delta < _FLOAT_EPSILON:
        # Same form check as DS-3: the number matches, but if the statement
        # lacks the prescribed "% alcohol by volume" wording (a bare "12%",
        # or "12% ABV"), route to needs_review/format rather than pass. The
        # wording is required for wine (4.36) and malt (7.65(b)) just as for
        # distilled spirits (5.65(a)), and absent words may be extraction
        # truncation rather than a label defect — so a human look, not a fail.
        if not _ABV_FORM.search(field.raw):
            return build(
                Outcome.NEEDS_REVIEW,
                f"Label ABV matches the application for this {category_label}, "
                "but the statement does not appear to use the required "
                '"% alcohol by volume" form (or a permitted abbreviation such '
                "as Alc./Vol.).",
                reason=Reason.FORMAT,
                expected=expected,
                actual=field.raw,
            )
        return build(
            Outcome.PASS,
            f"Label ABV matches the application for this {category_label}.",
            expected=expected,
            actual=field.raw,
        )
    if delta <= tolerance + _FLOAT_EPSILON:
        return build(
            Outcome.NEEDS_REVIEW,
            f"Label ABV ({value:g}%) differs from the application "
            f"({app.abv_percent:g}%) by {delta:.1f} points — within "
            f"{tolerance:g}, so it gets a human look rather than an automatic fail.",
            reason=Reason.MISMATCH,
            expected=expected,
            actual=field.raw,
        )
    return build(
        Outcome.FAIL,
        f"Label ABV ({value:g}%) differs from the application "
        f"({app.abv_percent:g}%) by {delta:.1f} points.",
        reason=Reason.MISMATCH,
        expected=expected,
        actual=field.raw,
    )


def _has_qualifying_wine_designation(class_type: str) -> bool:
    normalized = normalize_fuzzy(class_type)
    return any(
        normalize_fuzzy(designation) in normalized
        for designation in ("table wine", "light wine")
    )


def wn1_brand_name(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("WN-1", "Brand name", "27 CFR 4.33")
    return _fuzzy_consistency(
        build, "Brand name", app.brand_name, ext.brand_name, config
    )


def wn2_class_type(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("WN-2", "Class/type designation", "27 CFR 4.34")
    return _fuzzy_consistency(
        build, "Class/type designation", app.class_type, ext.class_type, config
    )


def wn3_alcohol_content(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("WN-3", "Alcohol content", "27 CFR 4.36")
    field = ext.alcohol_content
    expected = f"{app.abv_percent:g}% alcohol by volume"
    if field is None:
        if app.abv_percent > 14.0 + _FLOAT_EPSILON:
            return build(
                Outcome.FAIL,
                "No alcohol content statement found; wine above 14% ABV must "
                "state alcohol content.",
                reason=Reason.MISSING,
                expected=expected,
            )
        if _has_qualifying_wine_designation(app.class_type):
            return build(
                Outcome.PASS,
                "No alcohol content statement found, but the application class "
                "type uses a table/light wine designation for wine at or below "
                "14% ABV.",
            )
        return build(
            Outcome.NEEDS_REVIEW,
            "No alcohol content statement found; wine at or below 14% ABV may "
            "omit the statement only when a qualifying designation applies.",
            reason=Reason.MISSING,
            expected=expected,
        )
    tolerance = 1.0 if app.abv_percent > 14.0 + _FLOAT_EPSILON else 1.5
    return _abv_band_check(
        build,
        app,
        field,
        config,
        tolerance=tolerance,
        category_label="wine",
    )


def wn4_net_contents(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("WN-4", "Net contents", "27 CFR 4.37")
    return _net_contents_check(build, app.net_contents, ext.net_contents, config)


def wn5a_warning_text(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("WN-5a", "Government warning text", "27 CFR 16.21")
    return _warning_text_check(build, ext, config)


def wn5b_lead_in_caps(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("WN-5b", "GOVERNMENT WARNING capitalization", "27 CFR 16.22(a)(2)")
    return _lead_in_caps_check(build, ext, config)


def wn5c_bold(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder(
        "WN-5c", "GOVERNMENT WARNING bold formatting", "27 CFR 16.22(a)(2)"
    )
    return _warning_bold_check(build, ext, config)


def wn5d_placement(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder(
        "WN-5d", "Warning placement and layout", "27 CFR 16.21, 16.22(a)(3)"
    )
    return _warning_placement_check(build, ext, config)


def wn6_name_address(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("WN-6", "Name and address", "27 CFR 4.35")
    return _presence(build, "Name and address statement", ext.name_address, config)


def wn7_country_of_origin(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("WN-7", "Country of origin", "19 CFR 102, 19 CFR 134")
    if not app.imported:
        return build(
            Outcome.NOT_APPLICABLE,
            "Product is not imported; no country-of-origin statement is required.",
        )
    return _presence(
        build, "Country-of-origin statement", ext.country_of_origin, config
    )


def wn_scope(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder(
        "WN-SCOPE",
        "Wine checks outside automated scope",
        "27 CFR 4.23, 4.24, 4.25, 4.27, 4.32(e), 4.72",
    )
    return build(
        Outcome.NOT_EVALUATED,
        "This prototype does not evaluate wine appellation, vintage, varietal, "
        "semi-generic/geographic-name, standards-of-fill, or conditional "
        "ingredient/declaration requirements because they require taxonomy, "
        "formula, ingredient, or container facts outside the extracted label fields.",
    )


def mb1_brand_name(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("MB-1", "Brand name", "27 CFR 7.64")
    return _fuzzy_consistency(
        build, "Brand name", app.brand_name, ext.brand_name, config
    )


def mb2_class_type(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("MB-2", "Class/type designation", "27 CFR Part 7 Subpart I")
    return _fuzzy_consistency(
        build, "Class/type designation", app.class_type, ext.class_type, config
    )


def mb3_alcohol_content(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("MB-3", "Alcohol content", "27 CFR 7.65")
    field = ext.alcohol_content
    expected = f"{app.abv_percent:g}% alcohol by volume"
    if field is None:
        return build(
            Outcome.NEEDS_REVIEW,
            "No alcohol content statement found; malt beverage alcohol content "
            "is generally optional, with exceptions this label-only review cannot "
            "determine.",
            reason=Reason.MISSING,
            expected=expected,
        )
    return _abv_band_check(
        build,
        app,
        field,
        config,
        tolerance=0.3,
        category_label="malt beverage",
    )


def mb4_net_contents(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("MB-4", "Net contents", "27 CFR 7.70")
    return _net_contents_check(build, app.net_contents, ext.net_contents, config)


def mb5a_warning_text(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("MB-5a", "Government warning text", "27 CFR 16.21")
    return _warning_text_check(build, ext, config)


def mb5b_lead_in_caps(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("MB-5b", "GOVERNMENT WARNING capitalization", "27 CFR 16.22(a)(2)")
    return _lead_in_caps_check(build, ext, config)


def mb5c_bold(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder(
        "MB-5c", "GOVERNMENT WARNING bold formatting", "27 CFR 16.22(a)(2)"
    )
    return _warning_bold_check(build, ext, config)


def mb5d_placement(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder(
        "MB-5d", "Warning placement and layout", "27 CFR 16.21, 16.22(a)(3)"
    )
    return _warning_placement_check(build, ext, config)


def mb6_name_address(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("MB-6", "Name and address", "27 CFR 7.66-7.68")
    return _presence(build, "Name and address statement", ext.name_address, config)


def mb7_country_of_origin(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder("MB-7", "Country of origin", "19 CFR 102, 19 CFR 134")
    if not app.imported:
        return build(
            Outcome.NOT_APPLICABLE,
            "Product is not imported; no country-of-origin statement is required.",
        )
    return _presence(
        build, "Country-of-origin statement", ext.country_of_origin, config
    )


def mb_scope(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder(
        "MB-SCOPE",
        "Malt beverage checks outside automated scope",
        "27 CFR 7.63(b), 7.65(a), 7.65(b)(3)-(5)",
    )
    return build(
        Outcome.NOT_EVALUATED,
        "This prototype does not evaluate non-alcoholic, low-alcohol, alcohol-free, "
        "or added-flavor alcohol-content triggers; conditional ingredient/declaration "
        "requirements; or standards-of-fill questions because they require lab, "
        "formula, ingredient, or container facts outside the extracted label fields.",
    )


def ds_scope(
    app: ApplicationRecord, ext: ExtractionResult, config: EngineConfig
) -> Finding:
    build = _builder(
        "DS-SCOPE",
        "Distilled spirits checks outside automated scope",
        "27 CFR 5.63(a), 5.70",
    )
    return build(
        Outcome.NOT_EVALUATED,
        "This prototype does not evaluate same-field-of-vision, type-size, or "
        "standards-of-fill requirements because they require layout, measurement, "
        "or container facts outside the extracted label fields.",
    )


DS_RULES: list[RuleFn] = [
    ds1_brand_name,
    ds2_class_type,
    ds3_alcohol_content,
    ds4_net_contents,
    ds5a_warning_text,
    ds5b_lead_in_caps,
    ds5c_bold,
    ds5d_placement,
    ds6_name_address,
    ds7_country_of_origin,
    ds8_proof_abv,
    ds_scope,
]

WINE_RULES: list[RuleFn] = [
    wn1_brand_name,
    wn2_class_type,
    wn3_alcohol_content,
    wn4_net_contents,
    wn5a_warning_text,
    wn5b_lead_in_caps,
    wn5c_bold,
    wn5d_placement,
    wn6_name_address,
    wn7_country_of_origin,
    wn_scope,
]

MALT_RULES: list[RuleFn] = [
    mb1_brand_name,
    mb2_class_type,
    mb3_alcohol_content,
    mb4_net_contents,
    mb5a_warning_text,
    mb5b_lead_in_caps,
    mb5c_bold,
    mb5d_placement,
    mb6_name_address,
    mb7_country_of_origin,
    mb_scope,
]

RULES_BY_TYPE: dict[BeverageType, list[RuleFn]] = {
    BeverageType.DISTILLED_SPIRITS: DS_RULES,
    BeverageType.WINE: WINE_RULES,
    BeverageType.MALT_BEVERAGE: MALT_RULES,
}
