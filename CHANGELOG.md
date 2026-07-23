# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-07-23

This release improves long-running job visibility and compatibility with
Moonshot's Kimi reasoning models. It does not change the document IR schema.

### Added

- Live text-localization progress in the web UI, including the current slide,
  completed and total slides, and completed and total text blocks.
- Live approved-image-plan progress, including completed and total images plus
  the active `preparing`, `ocr`, `translating`, `inpainting`, `redrawing`,
  `generating`, `validating`, `reusing`, `preserved`, `failed`, or `completed`
  stage.
- A thread-safe `progress` object in public job responses:

  ```json
  {
    "progress": {
      "text": {
        "completed": 3,
        "total": 12,
        "completed_items": 42,
        "total_items": 134,
        "current": 4,
        "stage": "translating"
      },
      "images": {
        "completed": 8,
        "total": 25,
        "current": "s5-sh24-img",
        "stage": "ocr"
      }
    }
  }
  ```

- English, German, and Simplified Chinese labels for progress details and image
  processing sub-stages.

### Fixed

- Moonshot Kimi K2.5/K2.6 requests no longer send `temperature: 0`, which these
  models reject with HTTP 400. Translayer sends
  `"thinking": {"type": "disabled"}` instead when a Kimi K2.5/K2.6 model is
  used through a Moonshot API base URL.
- OpenAI-compatible HTTP failures now include the provider response body in the
  job error, making invalid parameters, authentication failures, and model
  errors diagnosable from server/job status instead of a generic HTTP code.

### Changed

- Text localization now emits progress after each slide while preserving
  slide-level context and ordering.
- Image execution now reports OCR, translation, local redraw, whole-image
  generation, validation, preservation, and reuse as distinct stages.
- The progress panel remains hidden during phases without measurable totals and
  uses the existing job polling endpoint; no additional polling request is
  introduced.
- Bumped version to `0.2.2`.

### Known limitations

- Parsing, initial image screening, and final rendering still expose named
  states rather than item-level percentages.
- Local OCR quality depends on source resolution, font style, contrast, and
  image complexity. Small or dense Chinese text may be misread; generated or
  locally redrawn images should still be reviewed before export.
- The `mock`/Offline demo translation engine validates the workflow but does
  not perform semantic translation; it prefixes source text with the target
  language code.

## [0.2.1] - 2026-07-23

### Added

- Task-scoped OpenAI-compatible translation settings in the web UI and API: base URL, optional API key, and model name, including support for local and private-network endpoints.
- Task-scoped DeepL API authentication in the web UI and API, with automatic Free/Pro endpoint selection.
- Optional task-scoped Gemini API key and image-model selection, clearly marked as necessary only for whole-image text editing.
- Public, non-secret runtime configuration for displaying the configured per-image planning estimate.
- Up-front and post-screening image cost forecasts showing estimated calls, per-image cost, projected total, and the user-approved hard budget.
- Simplified Chinese and German README editions.

### Changed

- DeepL translation now uses the current JSON `POST /v2/translate` request format and `DeepL-Auth-Key` authorization header.
- Translation and Gemini credentials are kept per job in server memory and are not exposed by public job responses.
- Gemini model selection is included in the generated-image cache key.
- Image cost estimation now consistently uses `TRANSLAYER_IMAGE_ESTIMATED_COST_USD` instead of mismatched hard-coded values.
- Bumped version to `0.2.1`.

## [0.2.0] - 2026-07-19

### Added

- English, Chinese, and German can now each be used as either the source or target language, with language-aware OCR and font handling.
- A redesigned trilingual web interface, defaulting to English, for upload, configuration, image review, progress tracking, and export.
- Local image screening and a human-review workflow that lets users choose which images require AI localization before incurring API costs.
- Gemini whole-image localization with explicit source-to-target text mappings so detected text cannot be silently treated as graphics.
- Pre- and post-generation OCR quality gates that detect untranslated source text and missing target text, reject invalid results, preserve a failure preview, and return the job to review for retry.
- Per-job image cost estimates and configurable cost limits.
- A production Dockerfile with LibreOffice, Poppler, Tesseract, and multilingual fonts.

### Changed

- Gemini output extraction now selects the final non-thought image from model output and invalidates failed cache entries.
- CLI image translation uses the same OCR validation workflow as the web application.
- Bumped version to `0.2.0`.

## [0.1.1] - 2026-06-20

### Fixed

- **PPTX SmartArt write-back corruption**: diagram data XML is now serialized with stable namespace prefixes (`dgm`, `a`, `r`, `dsp`) and the `standalone="yes"` declaration that PowerPoint expects. This prevents SmartArt graphics from disappearing after translation.
- SmartArt text containing line breaks is now written as multiple `<a:p>` paragraphs instead of a single run with newline characters.

### Changed

- Bumped version to `0.1.1`.

## [0.1.0] - 2026-06-20

### Added

- Translayer MVP: PPTX/DOCX/HTML parsers, CLI/API/UI, and pluggable translation/OCR/inpaint engines.
- Local Tesseract OCR engine (`--ocr-engine tesseract`).
- SmartArt text extraction from `ppt/diagrams/dataN.xml` and write-back support.
- PPTX image replacement via `shape.part.related_part(rId)` and `ImagePart._blob`.
