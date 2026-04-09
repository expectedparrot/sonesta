# Sonesta v1 Specification

## 1. Purpose

Sonesta is a local, agent-facing Python CLI for creating and updating PowerPoint presentations programmatically.

It is designed for workflows where an external agent or script is responsible for reasoning about slide content, while Sonesta provides durable, deterministic primitives for:

- creating `.pptx` presentations
- defining slides in a structured intermediate format
- placing text, tables, charts, images, and simple shapes
- applying templates and theme defaults consistently
- inspecting and validating presentation state

Sonesta is not a GUI slide editor. It is a build tool for presentations.

For v1, Sonesta targets `.pptx` generation only.

## 2. Design Principles

1. Filesystem first

- Projects and source definitions live on disk.
- Derived artifacts can be rebuilt from source files.
- No database or background service is required.

2. Agent-facing interface

- Every read command must support JSON output.
- Mutating commands should accept structured files rather than only ad hoc flags.
- Errors must be machine-readable and actionable.

3. Deterministic rendering

- The same input should produce the same slide structure and output bytes whenever practical.
- Object placement should be explicit or driven by deterministic layout rules.
- Sonesta should avoid hidden editor state.

4. PowerPoint-native output

- The primary artifact is a standard `.pptx` file usable in Microsoft PowerPoint, Keynote, and Google Slides import flows.
- Sonesta should preserve compatibility over exotic rendering features.

5. Clear separation of content and layout

- Slide content is represented as structured data.
- Templates, themes, and layout rules are represented separately.
- Agents can change content without rewriting low-level placement logic.

6. Inspectable intermediate representation

- Sonesta should expose a canonical presentation spec that can be linted, diffed, and regenerated.
- Users should not need to reverse-engineer `.pptx` internals to understand generated output.

## 3. Goals

### 3.1 Functional goals

- Initialize a Sonesta project.
- Create presentations from a structured spec.
- Add, remove, reorder, and update slides.
- Place text blocks, images, tables, charts, and simple vector shapes.
- Support speaker notes.
- Support themes, slide masters, and reusable layout templates at a practical v1 level.
- Allow asset references by file path.
- Export `.pptx`.
- Validate a presentation spec before rendering.
- Inspect presentations and slide specs in JSON form.

### 3.2 Non-goals for v1

- Full fidelity round-trip editing of arbitrary existing `.pptx` files.
- Pixel-perfect parity with every PowerPoint desktop feature.
- Real-time collaborative editing.
- Embedded video authoring.
- Complex SmartArt generation.
- VBA/macros.
- Full chart-editing parity with PowerPoint's internal workbook model.
- Browser-based presentation editing.

## 4. Terminology

- Project: A directory containing Sonesta source files and a `.sonesta/` metadata directory.
- Presentation: A logical deck with stable identity inside a project.
- Presentation spec: Canonical structured source describing slides, theme references, assets, and metadata.
- Slide: One page of the presentation.
- Element: A single object placed on a slide, such as a text box or image.
- Template: A reusable slide-level layout and styling definition.
- Theme: Shared presentation-level defaults such as fonts, colors, and page size.
- Asset: An external file referenced by the presentation, such as an image.
- Render: The act of compiling a presentation spec into a `.pptx` artifact.

## 5. Project Layout

Running `sonesta init` creates:

```text
.sonesta/
  config.json
  templates/
  themes/
  builds/
  cache/
  logs/
presentations/
assets/
```

Recommended layout for one presentation:

```text
presentations/
  q2_review/
    presentation.json
    slides/
      001-title.json
      002-market-size.json
      003-roadmap.json
    notes/
      001-title.md
      002-market-size.md
assets/
  logos/
  charts/
  photos/
.sonesta/
  config.json
  templates/
    default.json
  themes/
    brand-light.json
  builds/
    q2_review/
      q2_review.pptx
      manifest.json
  cache/
  logs/
```

## 6. Source of Truth

The source of truth is the presentation spec and referenced local assets.

For v1:

- `presentation.json` is canonical for presentation metadata and slide ordering
- per-slide JSON files are canonical for slide content
- generated `.pptx` files under `.sonesta/builds/` are derived artifacts
- caches and manifests are disposable

## 7. Core Invariants

### 7.1 Identity invariants

- `presentation_id` is the stable identity of a presentation.
- `slide_id` is the stable identity of a slide within a presentation.
- `element_id` is the stable identity of a slide element.
- Ordering is separate from identity.

### 7.2 Build invariants

- A successful render must be reproducible from source files and assets alone.
- Validation must run before final write of the output artifact.
- Derived build manifests may be deleted and regenerated.

### 7.3 Path invariants

- Asset references must be project-relative or absolute.
- Relative paths are resolved from the project root unless explicitly documented otherwise.
- Mutating commands should normalize stored paths.

### 7.4 Interface invariants

- Read commands support `--format json`.
- Errors from CLI commands should have stable machine-readable codes.
- Commands should exit non-zero on validation or render failure.

## 8. User Model

Sonesta assumes two primary users:

- Human developers who define templates, themes, and project conventions.
- Agents that generate or modify presentation specs through the CLI.

The agent is responsible for deciding what belongs on a slide.
Sonesta is responsible for making that decision executable and consistent.

## 9. Presentation Model

## 9.1 Presentation metadata

Example `presentation.json`:

```json
{
  "version": 1,
  "presentation_id": "deck_q2_review",
  "title": "Q2 Review",
  "page_size": "widescreen",
  "theme": "brand-light",
  "default_template": "default",
  "slides": [
    "slides/001-title.json",
    "slides/002-market-size.json",
    "slides/003-roadmap.json"
  ],
  "build": {
    "output": ".sonesta/builds/q2_review/q2_review.pptx"
  }
}
```

Fields:

- `version`: Sonesta schema version
- `presentation_id`: stable logical id
- `title`: human-readable title
- `page_size`: `standard`, `widescreen`, or explicit dimensions
- `theme`: theme name or path
- `default_template`: fallback slide template
- `slides`: ordered list of slide spec file paths
- `build.output`: preferred output path

## 9.2 Slide model

Example slide file:

```json
{
  "slide_id": "market_size",
  "kind": "content",
  "title": "Market Size",
  "template": "two-column-chart",
  "notes_path": "notes/002-market-size.md",
  "elements": [
    {
      "element_id": "headline",
      "type": "text",
      "text": "A large and growing market",
      "style": "headline"
    },
    {
      "element_id": "chart",
      "type": "chart",
      "chart_type": "bar",
      "data_path": "data/market_size.csv",
      "x": 6.4,
      "y": 1.4,
      "w": 6.2,
      "h": 4.8
    }
  ]
}
```

Fields:

- `slide_id`: stable id
- `kind`: semantic category such as `title`, `content`, `section`, `appendix`
- `title`: optional logical title
- `template`: optional slide template override
- `notes_path`: optional speaker notes path
- `elements`: ordered element definitions

## 9.3 Element model

Supported v1 element types:

- `text`
- `image`
- `table`
- `chart`
- `shape`
- `group`

Common fields:

- `element_id`
- `type`
- `x`, `y`, `w`, `h` in inches
- `style` optional style token
- `z_index` optional explicit stacking order
- `visible` optional boolean, default `true`

Element-specific rules:

- `text` supports plain text and limited paragraph/runs structure
- `image` references an asset path and optional crop/fit behavior
- `table` supports rows, columns, cell text, and basic cell styling
- `chart` supports structured series data or a data file reference
- `shape` supports simple shapes such as rect, line, ellipse, arrow
- `group` contains child elements with coordinates relative to the group frame

## 10. Layout System

Sonesta supports two placement modes in v1:

1. Absolute placement

- Every element supplies explicit `x`, `y`, `w`, `h`.
- This is the lowest-level and most deterministic mode.

2. Template slot placement

- A slide references a named template.
- Elements may target named slots such as `title`, `body_left`, `body_right`, `footer`.
- The template resolves slot geometry and default styling.

Template slots should compile to explicit coordinates before rendering.

## 11. Theme and Style Model

Themes live under `.sonesta/themes/`.

Example:

```json
{
  "name": "brand-light",
  "page_size": "widescreen",
  "colors": {
    "background": "#F7F2E8",
    "text": "#1E1E1E",
    "accent": "#B45309",
    "muted": "#6B7280"
  },
  "fonts": {
    "heading": "Aptos Display",
    "body": "Aptos"
  },
  "styles": {
    "headline": {
      "font_family": "Aptos Display",
      "font_size": 26,
      "bold": true,
      "color": "#1E1E1E"
    },
    "body": {
      "font_family": "Aptos",
      "font_size": 16,
      "color": "#1E1E1E"
    }
  }
}
```

Theme responsibilities:

- page dimensions
- default fonts
- color palette
- named text and shape styles
- default slide background

Theme non-goals in v1:

- full PowerPoint master editing parity
- complete OOXML theme serialization coverage

## 12. Templates

Templates live under `.sonesta/templates/`.

Example template responsibilities:

- define slots and their geometry
- define allowed element types per slot
- define slot-level defaults
- optionally require certain slots

Example slot names:

- `title`
- `subtitle`
- `hero`
- `body`
- `body_left`
- `body_right`
- `chart`
- `footer`

Validation should fail if:

- a required slot is missing required content
- an element targets an unknown slot
- a slot forbids the element type provided

## 13. Data and Chart Model

Charts should be specified in Sonesta's canonical structured form, not only as opaque external chart images.

v1 chart support:

- bar
- column
- line
- pie

Accepted chart inputs:

- inline structured data
- CSV file path
- JSON file path

Canonical chart fields:

- `chart_type`
- `series`
- `categories`
- `title` optional
- `legend` optional
- `value_format` optional

If the backend library cannot represent a requested chart feature natively, Sonesta should fail clearly rather than silently degrading layout.

## 14. Notes Model

Speaker notes are optional and stored outside the slide JSON by default.

Rules:

- `notes_path` references a UTF-8 Markdown or plain text file
- Sonesta inserts the note content into the slide's speaker notes section
- Sonesta should not parse note Markdown semantically in v1; plain text extraction is sufficient

## 15. Asset Handling

Supported v1 assets:

- PNG
- JPEG
- SVG only if converted explicitly before placement or supported by the chosen backend

Asset rules:

- missing assets are validation errors
- asset dimensions should be inspectable through CLI
- Sonesta should not mutate source assets
- optional caching of normalized images is allowed under `.sonesta/cache/`

## 16. CLI Surface

Primary commands:

```text
sonesta init
sonesta new presentation <name>
sonesta validate <presentation-or-slide-path>
sonesta render <presentation-path>
sonesta inspect <presentation-or-slide-path>
sonesta slides list <presentation-path>
sonesta slides add <presentation-path> --slide <slide-path> [--after <slide-id>]
sonesta slides remove <presentation-path> <slide-id>
sonesta slides move <presentation-path> <slide-id> --after <slide-id>
sonesta assets inspect <asset-path>
sonesta templates list
sonesta themes list
```

Interface expectations:

- commands default to human-readable output
- `--format json` produces stable structured output for agents
- mutating commands should support `--dry-run` when practical

## 17. Validation

`sonesta validate` should check:

- schema validity
- duplicate `slide_id` or `element_id` violations
- missing template or theme references
- missing assets
- out-of-bounds element geometry
- invalid chart definitions
- unsupported fonts or page sizes when detectable
- slot/type mismatches

Validation output should include:

- severity: `error` or `warning`
- code: stable string identifier
- message
- file path
- JSON pointer or field path when available

Example:

```json
{
  "ok": false,
  "issues": [
    {
      "severity": "error",
      "code": "missing_asset",
      "path": "presentations/q2_review/slides/003-roadmap.json",
      "field": "/elements/1/path",
      "message": "Referenced asset does not exist: assets/logos/new_logo.png"
    }
  ]
}
```

## 18. Render Semantics

`sonesta render` behavior:

1. Load project config.
2. Load presentation spec and referenced slide specs.
3. Resolve theme and template references.
4. Validate the full presentation.
5. Materialize a new `.pptx` in a temporary path.
6. Write a build manifest.
7. Atomically move the final artifact into place.

Render should fail without replacing the previous build artifact if validation or write fails.

## 19. Build Manifest

Each successful render should write a manifest such as:

```json
{
  "presentation_id": "deck_q2_review",
  "source_path": "presentations/q2_review/presentation.json",
  "output_path": ".sonesta/builds/q2_review/q2_review.pptx",
  "rendered_at": "2026-04-09T17:00:00Z",
  "slide_count": 12,
  "asset_count": 8,
  "theme": "brand-light",
  "template_set": [
    "default",
    "two-column-chart"
  ]
}
```

The manifest is derived and disposable.

## 20. Inspection Commands

`sonesta inspect` should expose normalized JSON for:

- project config
- presentation metadata
- slide list and order
- resolved slide geometry
- element inventory
- referenced assets

The normalized inspection form is the main machine interface for agents that need to reason about current state.

## 21. Existing `.pptx` Support

v1 support for existing presentations is intentionally limited.

Allowed scope:

- use an existing `.pptx` as a source template only if Sonesta can safely load named layout information from it
- optionally append generated slides to a base deck in a constrained workflow

Not guaranteed in v1:

- preserving arbitrary animations
- preserving comments
- preserving hidden application-specific metadata
- lossless edit-in-place of any third-party deck

## 22. Python Implementation Constraints

The implementation should be a Python package with a console entry point.

Recommended v1 stack:

- CLI: `typer` or `click`
- schema validation: `pydantic`
- `.pptx` generation: `python-pptx`
- image probing: `Pillow`
- chart preprocessing: stdlib `csv` and `json`, optionally `pandas` only if justified

Design constraint:

- Sonesta's internal spec should not mirror `python-pptx` too closely
- backend-specific details should be isolated behind a renderer layer

This allows future replacement or augmentation of the rendering backend without rewriting the CLI contract.

## 23. Error Model

CLI failures should map to stable categories:

- `usage_error`
- `schema_error`
- `validation_error`
- `asset_error`
- `render_error`
- `io_error`

JSON error shape:

```json
{
  "ok": false,
  "error": {
    "code": "validation_error",
    "message": "Presentation contains 3 validation errors",
    "details": []
  }
}
```

## 24. Testing Requirements

v1 should include:

- schema validation tests
- CLI command tests
- fixture-based render tests
- regression tests for element geometry
- golden-file tests for normalized inspection output

PowerPoint binary diffs are often noisy, so tests should prefer:

- normalized manifest assertions
- XML-part assertions for selected slide content
- slide count and element count checks

## 25. Security and Safety

Sonesta is a local tool, but it still must:

- avoid executing code from presentation specs
- treat file references as data only
- reject path traversal where project-local paths are required
- avoid shelling out implicitly except for clearly documented optional converters

## 26. Open Questions

The following are intentionally unresolved and should be decided before implementation:

1. Should the canonical slide source format be JSON only, or JSON plus YAML?
2. Should templates be purely Sonesta-native, or may they reference an existing `.pptx` master deck?
3. How much chart functionality should be delegated to PowerPoint-native charts versus rasterized chart images?
4. Should `render` support partial builds of a slide subset for fast iteration?
5. Should Sonesta support a higher-level declarative layout engine beyond named slots in v1?

## 27. Recommended v1 Scope Cut

To keep v1 tractable, Sonesta should ship with:

- project init
- presentation creation
- JSON slide specs
- text, image, table, chart, and shape elements
- theme files
- basic template slotting
- validation
- JSON inspection
- deterministic `.pptx` rendering

The first version should not attempt rich round-trip editing. The agent-facing value comes from reliable generation, validation, and inspection.
