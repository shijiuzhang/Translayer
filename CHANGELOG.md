# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
