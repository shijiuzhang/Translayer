# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
