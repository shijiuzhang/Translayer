<div align="center">

# Translayer

**Any format in, any language out — layout and in-image text intact.**

Translate documents into any language without breaking layout — even the text inside images.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
![Status](https://img.shields.io/badge/status-early%20development-orange.svg)

</div>

---

## Why Translayer

Existing translation tools treat localization as a pure NLP problem. But the real pain is **document engineering + translation**:

- **Layout breaks.** Translated text overflows boxes; uploading a `.pptx` errors out; converting to PDF shatters the structure.
- **In-image text is ignored.** Every mainstream tool leaves the text *inside images* untranslated.
- **One engine for every language pair.** Quality that's great for EN→DE collapses for EN→ZH.

Translayer is an **AI-native document localization middle layer**: any format is parsed into a unified intermediate representation (**DocumentIR**), enriched, localized through pluggable engines, and rendered back **losslessly** — including redrawing the text inside images with real fonts.

## What it does

- 🖼️ **Translates text inside images** — OCR → erase → re-typeset with real fonts (the sharpest differentiator).
- 🧩 **Lossless layout** — semantic layout modeling with constraints, not a black-box skeleton, so text boxes don't overflow.
- 🔌 **Pluggable everything** — formats (parsers/renderers), engines (translation/OCR/inpaint) and enrichment are all adapters.
- 🧠 **AI-native pipeline** — whole-document context, multi-engine routing, glossary injection, VLM quality loop.
- 📐 **Open IR standard** — the DocumentIR JSON Schema is the interoperable, future-proof core.

## How it works

```
input.pptx ──Parse──▶ DocumentIR ──Enrich──▶ ──Localize──▶ ──Render──▶ output.pptx
              (format)              (semantics)  (engines)    (format)
```

Four pluggable stages flow around a single intermediate representation:

1. **Parse** — format plugin extracts text, layout, and images into `DocumentIR`.
2. **Enrich** — semantic roles, in-image OCR, glossary/TM matching, context grouping.
3. **Localize** — multi-engine translation with context/term/length constraints + the in-image text sub-pipeline.
4. **Render** — precise, lossless write-back via `source_ref`; localized images swapped in.

![Architecture](docs/architecture.png)

## Status

Early development. The MVP is a narrow slice: **English PPTX → Chinese**, with in-image text translated and layout intact.

## Quickstart

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"

# Translate a deck
translayer translate input.pptx --from en --to zh -o output.pptx

# Or run the review UI
translayer serve
```

## Roadmap

- [x] DocumentIR + pluggable four-stage pipeline
- [ ] PPTX parser/renderer with lossless write-back
- [ ] In-image text pipeline (OCR → erase → real-font re-typeset)
- [ ] Review web UI (human-in-the-loop)
- [ ] More formats (DOCX/HTML/MD), TM/glossary, private deployment
- [ ] XLIFF interop

## Contributing

Adding a format or engine is a single adapter. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache 2.0](LICENSE).
