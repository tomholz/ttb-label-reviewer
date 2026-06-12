"""Upload caps, shared by the single-review endpoints and the batch
parser so both enforce the same per-label-set limits.

Enforced at the upload boundary so an oversized upload is a clear 413
(or a row-level error in batch), never an opaque vision-API failure.
Derivation: the Anthropic API accepts a 32 MB request body and base64
inflates image bytes by 4/3, so 20 MB of raw images encodes to ~27 MB —
under the limit with headroom for prompt and JSON. 8 images is double
the realistic maximum for an untagged label set (front, back, side,
neck). 5 MB/image is our own cap (the direct API allows ~10 MB
base64-encoded per image); it bounds upload time and keeps any single
image well clear of the request limit.
"""

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES_PER_SET = 8
MAX_TOTAL_IMAGE_BYTES = 20 * 1024 * 1024

# Batch caps. The peak-season scenario from the interviews is an importer
# dumping 200-300 applications at once; 500 rows covers it with headroom
# (a bigger batch splits into two zips). The uncompressed cap is a
# zip-bomb guard checked against the central directory before any entry
# is read; it also bounds memory, since a parsed batch holds its image
# bytes until the rows are processed.
MAX_BATCH_ZIP_BYTES = 100 * 1024 * 1024
MAX_BATCH_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_BATCH_ROWS = 500
