"""The extraction prompt and its hash (the hash feeds the milestone-5
eval scoreboard, D-5).

Standing constraint (D-2): the canonical government warning text must
never appear here — not the statement body, and not even its capitalized
lead-in phrase, since the model's prior on that string is all-caps and
priming it is exactly what makes title-case labels get silently
"corrected" during extraction. This module must never import from
engine.canonical. The prose below therefore refers to the warning only
in lowercase, generic terms. tests/test_extraction_prompt.py enforces
all of this; if you are editing this prompt to "improve" it, read
docs/ttb-requirements.md → Extraction fidelity first.
"""

import hashlib

EXTRACTION_PROMPT = """\
You are transcribing alcohol beverage label images for a compliance
review system. You will receive one or more images that together form a
single label set (the front, back, side, and/or neck labels of one
product). A field may appear on any image in the set.

Transcription rules — these override everything else:

1. Transcribe text exactly as printed. Preserve capitalization, line
   breaks (use \\n where the label breaks a line), hyphenation,
   apostrophes, punctuation, spelling errors, and unusual casing.
2. Never correct, complete, normalize, or paraphrase. If the printed
   text differs from what you would expect a label of this kind to say,
   transcribe the printed text, not the expected text.
3. Do not judge compliance and do not compare anything against legal
   requirements. Your only job is to read.

For each field, report the raw printed text and a confidence score from
0 to 1 reflecting how certain you are that your transcription matches
what is printed (glare, skew, blur, and low resolution lower
confidence). Use null for a field that does not appear on any image:
null means "not present anywhere", while low confidence means "present
but hard to read".

Fields:

- brand_name: the product's brand name.
- class_type: the class/type designation (the kind of product, e.g. the
  style of whiskey).
- alcohol_content: the alcohol-content statement as one string, exactly
  as printed — not just the number.
- proof: the proof statement, if one appears.
- net_contents: the net-contents statement.
- name_address: the bottler/producer/importer name-and-address
  statement.
- country_of_origin: the country-of-origin statement, if one appears.
- government_warning: the label's government health warning statement,
  if one appears.
  - raw_text: the complete warning verbatim as printed, from its opening
    words to its end, with \\n at printed line breaks. Rules 1 and 2
    apply with full force here: reproduce the exact wording, casing, and
    punctuation even if it looks wrong, incomplete, or unusual to you.
  - lead_in_bold: "yes", "no", or "uncertain" — are the warning's
    opening words (the lead-in phrase before the body text) printed in
    bold type?
  - remainder_bold: "yes", "no", or "uncertain" — is the body text after
    the lead-in printed in bold type?
  - separate_and_apart: "yes", "no", or "uncertain" — does the warning
    stand as its own uninterrupted block, separate from all other label
    text, rather than being broken up by or interleaved with unrelated
    text?
"""


def prompt_sha256() -> str:
    """Hash recorded next to every eval score (D-5): a bare score is not
    a reproducible claim; (model ID, prompt hash, golden-set version) is."""
    return hashlib.sha256(EXTRACTION_PROMPT.encode("utf-8")).hexdigest()
