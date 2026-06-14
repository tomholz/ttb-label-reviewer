# Single Result Label Preview Plan

> Working plan for adding uploaded label image previews to the single-item
> review result. This is a UI-only enhancement: it must not change the public
> review-result contract, the rule engine, extraction behavior, or batch output.

## Context

The single-review result currently shows the verdict, counts, coverage, and
per-rule findings, but it does not show the label image the agent just reviewed.
That makes the result less useful as an evidence screen: expected/actual values
are visible, but the original label artwork is one browser scroll/file chooser
interaction away.

The upload path already has the bytes needed for a preview:

- `POST /review` reads uploaded files into `LabelImage` objects in
  `main.py::_read_label_images(...)`.
- `_run_single_review(...)` builds the `ApplicationRecord`, runs extraction, and
  returns only `ReviewResult`.
- `partials/results.html` receives `result` and `beverage_label`; it receives no
  image context.
- The app promises stateless processing: uploads are processed in memory and
  never stored.

The recommended implementation is therefore an inline, template-only preview
model passed only to the HTML result fragment. Do not add image bytes, URLs, or
preview metadata to `ReviewResult`.

## Goals

1. In single-item results, display the uploaded label image(s) near the verdict
   so the reviewer can compare the rule evidence against the source artwork.
2. Preserve the existing privacy/retention story: no uploaded image is written
   to disk, cached in an endpoint, or retained after the response is rendered.
3. Keep `/api/review`, the engine contracts, and batch results unchanged.
4. Keep the result usable with multiple images and on narrow screens.

## Non-Goals

- No image annotation, OCR overlays, zoom viewer, crop tools, or field-to-image
  highlighting.
- No persistent image URLs or downloadable copies of uploaded files.
- No change to the extraction prompt or the rule-evaluation contract.
- No batch-row image previews in this pass. Batch has a different scale and
  privacy/performance profile.

## UX Direction

Render a compact preview section inside `partials/results.html`, after the
application id and before the findings list.

Suggested structure:

- Heading: `Label image` for one image, `Label images` for multiple.
- A thumbnail grid that shows each preview with the uploaded filename.
- Images use `alt="Uploaded label image: {filename}"`.
- For multiple images, preserve upload order. The pipeline treats images as
  order-irrelevant, but preserving the user-provided order is the least
  surprising display behavior.

Visual behavior:

- The preview should feel like part of the result evidence, not a separate card
  inside the result card.
- Thumbnails should have stable dimensions to avoid shifting the findings down
  as images load.
- Use `object-fit: contain` so tall bottle labels and wide back labels remain
  inspectable.
- On mobile, the grid should collapse to one column.

## Implementation

### 1. Add a Preview Data Shape Local to `main.py`

Add a small presentation-only type near the UI helpers in `main.py`.

Candidate shape:

```python
class LabelPreview(BaseModel):
    filename: str
    data_url: str
```

This can also be a `TypedDict` or a tiny dataclass. It should not live in
`engine/types.py` because it is not part of the review contract.

### 2. Build Data URLs from In-Memory Uploads

Add a helper in `main.py`:

```python
def _label_previews(label_images: list[LabelImage]) -> list[LabelPreview]:
    ...
```

Implementation details:

- Use `base64.b64encode(image.data).decode("ascii")`.
- Construct `data:{image.media_type};base64,{encoded}`.
- Keep the original uploaded filename or `"label"` fallback already assigned by
  `_read_label_images(...)`.
- No filesystem writes, no global cache, no endpoint.

The helper only handles media types already accepted by `_read_label_images`.

### 3. Keep Review Execution and Preview Creation Together

The current `_run_single_review(...)` returns only `ReviewResult`, which drops
the `LabelImage` objects before `ui_review(...)` can render them.

Refactor conservatively:

- Keep `_read_label_images(...)` as the upload validation boundary.
- Keep `_review_application(...)` as the shared application-plus-images review
  helper.
- Introduce a UI-only helper for single-review forms, or return a small pair
  from a new helper used by `/review`.

One straightforward path:

```python
def _run_single_review_with_images(...) -> tuple[ReviewResult, list[LabelImage]]:
    label_images = _read_label_images(images)
    application = ApplicationRecord(...)
    result = _review_application(application, label_images, extractor)
    return result, label_images
```

Then:

- `/review` uses the tuple and passes
  `{"result": result, "beverage_label": ..., "label_previews": _label_previews(label_images)}`.
- `/api/review` should continue to return only `ReviewResult`. It can call the
  existing `_run_single_review(...)`, or `_run_single_review(...)` can wrap the
  new helper and discard images.
- `/review/sample` should also pass previews. It already builds a `LabelImage`
  from the bundled demo image.

Do not alter `ReviewResult`, `ApplicationRecord`, or `review_label_set(...)`.

### 4. Update `partials/results.html`

Add a guarded preview block:

```jinja
{% if label_previews %}
<section class="label-preview" aria-labelledby="label-preview-heading">
  <h3 id="label-preview-heading">
    Label image{% if label_previews | length != 1 %}s{% endif %}
  </h3>
  <ul class="label-preview-list">
    {% for preview in label_previews %}
    <li class="label-preview-item">
      <img src="{{ preview.data_url }}"
           alt="Uploaded label image: {{ preview.filename }}">
      <span>{{ preview.filename }}</span>
    </li>
    {% endfor %}
  </ul>
</section>
{% endif %}
```

Use normal Jinja escaping for filenames. The `data_url` is generated server-side
from validated media types and base64 bytes.

### 5. Add CSS

Add styles near the results section in `static/style.css`.

Suggested classes:

- `.label-preview`
- `.label-preview h3`
- `.label-preview-list`
- `.label-preview-item`
- `.label-preview-item img`
- `.label-preview-item span`

Implementation notes:

- Use the existing `--bg`, `--line`, `--muted`, and `--card` variables.
- Do not create a nested card. Use a bordered evidence panel or unframed section
  inside the existing result card.
- Give images a fixed thumbnail box, for example `height: 14rem`, `width: 100%`,
  `object-fit: contain`, and a neutral background.
- Ensure filenames wrap with `overflow-wrap: anywhere`.

## Tests

Update `tests/test_ui.py`.

### Single Upload Preview

Extend `test_review_renders_verdict_counts_and_evidence(...)` or add a focused
test:

- Post `/review` with one PNG upload and the fake extractor.
- Assert the result contains:
  - `class="label-preview"`
  - `Label image`
  - `Uploaded label image: front.png`
  - `data:image/png;base64,`
  - the base64 encoding of the uploaded bytes, if the fixture remains small.

### Multiple Upload Preview

Add or extend coverage for two uploaded images:

- Post `front.png` and `back.png`.
- Assert both filenames appear in the preview.
- Assert the heading pluralizes to `Label images`.

### Sample Preview

Extend `test_sample_review_renders_normal_results_fragment(...)`:

- Assert the sample result includes the preview section.
- Assert the sample filename appears.
- Assert `data:image/png;base64,` appears.

### API Contract Stays Clean

Add or extend an API test if needed:

- `POST /api/review` still returns JSON with `application_id`, `verdict`,
  `counts`, `coverage`, and `findings`.
- Assert it does not include `label_previews`, `data_url`, or base64 image data.

### Static Asset / Privacy Checks

No new external assets should be introduced. Existing tests already assert the
page has no CDN URLs; keep that invariant.

## Manual Verification

Run:

```bash
uv run pytest tests/test_ui.py tests/test_api.py
```

If time allows, run the full suite:

```bash
uv run pytest
```

Browser check:

```bash
uv run uvicorn ttb_label_reviewer.main:app --port 8099
```

Then open `/` and verify:

1. Upload one label image and submit a single review.
2. The result scrolls/focuses as before.
3. The uploaded image appears between the application id and findings.
4. Multiple uploaded images appear in a stable grid.
5. A one-click sample review also shows the bundled label image.
6. Refreshing the page does not leave any uploaded image retrievable by URL.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Large uploads make the result HTML heavy. | Current upload limits already cap one review at 20 MB total. If this feels slow in manual testing, cap rendered previews to the first 4 images and show a count note. |
| Data URLs bloat memory temporarily. | This is bounded by existing upload limits and request lifetime; no persistent cache is introduced. |
| GIF previews animate or render inconsistently. | Accept as browser-native behavior for now; media type validation already allows GIF. |
| The preview could be mistaken as part of the API result. | Keep the data shape local to `main.py`, pass it only into `TemplateResponse`, and add an API test excluding it. |

## Acceptance Criteria

- Single-review HTML results show uploaded label image previews.
- Sample-review HTML results show the bundled sample image preview.
- `/api/review` response schema is unchanged.
- Batch UI is unchanged.
- No uploaded image is written to disk or exposed through a new URL.
- UI tests cover one image, multiple images, and sample previews.
- Existing privacy language remains true: uploads are processed in memory and
  never stored.
