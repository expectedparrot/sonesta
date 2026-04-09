# Sonesta Evaluation

## Decks Created

The current CLI was used to create and render three decks under `evaluation/presentations/`:

- `briefing`: text-heavy executive briefing with notes and a decision table
- `portfolio`: image grid plus chart-and-table metrics slide
- `process`: simple process diagram built from shapes and line segments

Rendered artifacts were produced under `evaluation/.sonesta/builds/`:

- `briefing/briefing.pptx`
- `portfolio/portfolio.pptx`
- `process/process.pptx`

All three validated and rendered successfully.

## What Worked

- The CLI is now strong enough to build multi-slide decks end to end without hand-editing JSON.
- Core mutation flows are usable: create slide, add elements, update elements, add notes, duplicate slide, render.
- Text, image, table, chart, and shape elements all worked in the test decks.
- Slide-local inspect/validate is useful when iterating on one slide.
- Notes round-trip cleanly through the CLI and render path.

## Findings

### 1. Empty scaffold elements create slide clutter

Every `new slide` starts with a default empty `body` text element. In practice, most real slides either:

- replace that element immediately, or
- forget to remove it and carry a meaningless empty text box in the source and rendered deck

This showed up in all three evaluation decks. It is a source of noise for agents and users.

Recommendation:

- add `new slide --blank`
- or make scaffold presets explicit, e.g. `--preset title`, `--preset body`, `--preset two-column`

### 2. Rich text and bullets are a major gap

The briefing deck needed bullets, but the current text model is only a plain string with optional font fields. That forces awkward workarounds:

- manual numbering inside one string
- shell-quoting friction for multiline content
- no paragraph-level bullets, indentation, or mixed emphasis

Recommendation:

- add paragraph/runs structure to text elements
- add a simpler CLI shortcut for bullets, e.g. `--bullets-json`

### 3. Diagram authoring is too low-level

The process deck worked, but only by manually placing four boxes and three line segments with hand-picked coordinates. This is fragile and slow.

Missing capabilities:

- connectors or arrows between shapes
- alignment/distribution helpers
- equal-spacing helpers
- grouped movement or higher-level node/edge diagrams

Recommendation:

- add connector shapes first
- then add small layout helpers before attempting a full diagram DSL

### 4. Image layout support is underspecified and partially unimplemented

The image workflow is usable, but still weak.

Observed and inferred issues:

- image grids required manual coordinates
- there is no image crop/focal-point control
- `fit` exists in the schema but is not actually used during rendering; images are always passed directly to `add_picture(...)` with the requested box

That last point is an implementation bug inferred from [render.py](/Users/jjhorton/tools/ep/sonesta/src/sonesta/render.py).

Recommendation:

- implement actual `contain`/`cover`/`stretch` behavior
- add row/column helpers for common image gallery layouts

### 5. Table and chart styling are too shallow

The metrics deck renders, but the output surface for tables/charts is still thin:

- no per-series colors
- no axis title control
- no gridline control
- no cell fill/border styling
- no number-format support beyond the chart value axis shortcut

Recommendation:

- add a small styling layer instead of trying to expose all of `python-pptx`
- focus on common business-chart/table controls first

### 6. No visual feedback loop inside the tool

This is the biggest workflow weakness. The CLI can validate structure, but it cannot preview slides or export slide thumbnails. That means evaluation still depends on opening the `.pptx` externally.

Recommendation:

- add `render-slide --png` or `preview` support if feasible
- or add a lightweight HTML/debug rendering path for layout inspection

### 7. Default-template usage is not surfaced clearly

The decks inherit the default template, and inspection resolves it correctly, but render manifests report an empty `template_set` when no slide explicitly sets `template`.

That is misleading for downstream tooling because the deck did use a template in practice.

Recommendation:

- manifest generation should include inherited template usage, not only explicit slide-level template references

### 8. Command ergonomics are getting better, but payload-heavy commands are still awkward

`add-table` and `add-chart` require JSON strings on the command line. That works, but it is brittle and annoying in real agent/human usage.

Recommendation:

- add `--rows-file`, `--series-file`, `--categories-file`
- or add stdin support for structured payloads

### 9. Layering controls are still nominal

The schema includes `z_index`, but render order is still effectively insertion order. This was not a visible blocker in the test decks, but it is a likely problem for more complex layouts.

This is an implementation finding inferred from [render.py](/Users/jjhorton/tools/ep/sonesta/src/sonesta/render.py).

Recommendation:

- sort visible elements by `z_index` before rendering

## Priority Next Steps

Suggested order:

1. Fix image `fit` rendering semantics.
2. Replace implicit empty slide scaffolds with explicit presets or blank mode.
3. Add rich text/bullets.
4. Add connector/alignment helpers for diagrams.
5. Add file/stdin payload options for chart/table commands.
6. Improve preview/visual inspection.

## Bottom Line

The current approach is working for deterministic generation, which is the right foundation. The main weaknesses are no longer about basic feasibility; they are about authoring ergonomics and visual iteration.

That is a good sign. The next version should focus less on adding more primitive element types and more on:

- better composition helpers
- better text semantics
- better preview/debug loops
