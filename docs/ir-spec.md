# DocumentIR Specification (v0.1.0)

DocumentIR is Translayer's open intermediate representation. Every format is
parsed *into* it and rendered *back out* of it. The most valuable asset is not
the text but the metadata surrounding it: semantic role, layout constraints,
precise write-back coordinates, term hits, and in-image text regions.

Export the machine-readable JSON Schema:

```bash
translayer schema -o ir.schema.json
```

## Top level

```jsonc
{
  "schema_version": "0.1.0",
  "meta":      { ... },   // DocMeta
  "resources": { ... },   // fonts + images (with in-image text)
  "blocks":    [ ... ]    // ordered translatable units
}
```

### DocMeta
| field | type | notes |
|---|---|---|
| `source_lang` / `target_lang` | str | BCP-47-ish codes (`en`, `zh`, `de`) |
| `doc_type` | str | `pptx` (more to come) |
| `title` | str? | document title |
| `glossary_ref` | str? | path to a `source,target` CSV |
| `engine_hints` | object | free-form routing hints |

### Block
The unit of translation (paragraph-level).

| field | type | notes |
|---|---|---|
| `id` | str | stable, e.g. `s0-sh3-p1` |
| `type` | enum | `title`/`subtitle`/`body`/`list_item`/`table_cell`/`shape_text`/`image` |
| `semantic_role` | str? | `title`/`body`/`caption`/`footer`/`watermark`… |
| `runs` | Run[] | source rich-text runs (inline formatting) |
| `source_text` | str | flattened source |
| `target_text` | str? | filled by Localize |
| `translatable` | bool | images are `false` |
| `layout` | Layout? | slide/shape, position (EMU), base font |
| `constraints` | Constraints | `max_chars`, `can_shrink_font`, `min_font_size` |
| `term_hits` | TermHit[] | glossary matches the engine must honor |
| `source_ref` | SourceRef | **precise write-back coordinate** |

### SourceRef
Addresses exactly where a block came from, enabling lossless render-back:
`kind` (`shape_text`/`table_cell`/`image_region`), `slide_index`, `shape_id`,
and depending on kind: `paragraph_index`/`run_index`, `row`/`col`, or
`image_id`/`region_id`.

### Resources & in-image text
`resources.images[]` are `ImageResource` with extracted `text_regions[]`
(`ImageTextRegion`): `bbox` (pixels), optional `polygon`, `source_text`,
`target_text`, `font_estimate`, `align`, and `background_kind`
(`solid`/`gradient`/`photo`, which routes the inpaint strategy). After
localization, `localized_data_ref` points to the re-drawn image.

## Pipeline contract

```
Parse    : input file            -> DocumentIR              (ParserPlugin)
Enrich   : DocumentIR            -> DocumentIR (+roles,     (EnricherPlugin)
                                    OCR regions, terms,
                                    max_chars constraints)
Localize : DocumentIR            -> DocumentIR (+target_text,
                                    +localized images)
Render   : DocumentIR + original -> output file             (RendererPlugin)
```

Each stage only reads/writes the IR, so stages and engines are independently
swappable. Renderers receive the original file to guarantee that anything not
modeled by the IR is preserved byte-for-byte.
