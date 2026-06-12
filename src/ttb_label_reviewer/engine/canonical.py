"""The canonical government health warning, 27 CFR 16.21.

D-2 (docs/decisions.md): this text lives here and ONLY here. It must never
be imported by — or pasted into — anything that constructs a model prompt.
Priming the extractor with the canonical wording is maximal encouragement
to autocomplete a deviant label toward it, which silently defeats DS-5a and
DS-5b in exactly the cases that matter most. A future "improve the prompt"
pass is the expected way this gets violated; don't be that pass.
"""

CANONICAL_LEAD_IN = "GOVERNMENT WARNING"

CANONICAL_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women "
    "should not drink alcoholic beverages during pregnancy because of "
    "the risk of birth defects. (2) Consumption of alcoholic beverages "
    "impairs your ability to drive a car or operate machinery, and may "
    "cause health problems."
)
