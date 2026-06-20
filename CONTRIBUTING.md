# Contributing to Translayer

Thanks for helping build an open standard for document localization. The whole
architecture is designed so that **adding a format or an engine is a single
adapter** — no core changes required.

## Project layout

```
src/translayer/
  ir/          DocumentIR — the open intermediate representation
  plugins/     plugin Protocols + registry
  parsers/     format -> IR        (ParserPlugin)
  renderers/   IR -> format        (RendererPlugin)
  enrich/      semantic roles, in-image OCR, glossary, grouping
  localize/    text + image pipelines, layout fitting
  engines/     translation / ocr / inpaint adapters
  fonts/       target-language font selection + real-font re-typesetting
  api/         FastAPI job API + review UI
```

## Setup

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
pytest -q
ruff check src/translayer tests
```

## Adding a translation engine

1. Create `src/translayer/engines/translation/<name>_engine.py`.
2. Subclass `BaseTranslationEngine` and implement `translate(...)` with the
   signature from `plugins/base.py::TranslationEngine`.
3. Register it: `@registry.register("translation", "<key>")` and set `name`.
4. Import your module in `engines/translation/__init__.py` so registration fires.
5. Add a test (use the `mock` engine pattern — **no network in tests**).

The same recipe applies to `ocr` and `inpaint` engines, and to `parser` /
`renderer` format plugins. Third-party packages can also register via the
`translayer.plugins` entry-point group.

## Conventions

- `from __future__ import annotations`, full type hints.
- `ruff` clean (rules E, F, I, UP, B).
- Tests must run offline. Never call a network engine in CI.
- Keep the IR backward compatible; bump `SCHEMA_VERSION` for breaking changes.

## License

By contributing you agree your contributions are licensed under Apache 2.0.
