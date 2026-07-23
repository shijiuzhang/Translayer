# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-07-23

### Added

- Live text-localization progress with completed slides, text blocks, and the current slide.
- Live image-plan progress with completed image counts and OCR, translation, inpainting, redrawing, generation, reuse, and quality-validation stages.
- English, German, and Simplified Chinese progress labels in the web interface.

### Fixed

- Moonshot Kimi K2.5/K2.6 compatibility by disabling thinking and omitting the unsupported zero-temperature parameter.
- OpenAI-compatible HTTP errors now include the provider response body for actionable diagnostics.

### Changed

- Bumped version to `0.2.2`.

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
