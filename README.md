# Sonesta

Sonesta is an agent-focused Python CLI for creating PowerPoint decks from structured JSON specs.

It is built for deterministic, local-first deck generation:

- create and mutate slide specs through the CLI
- validate presentations or individual slides
- inspect normalized deck state as JSON
- render `.pptx` output without GUI automation

## Current Capabilities

Core project commands:

- `sonesta init`
- `sonesta new presentation <name>`
- `sonesta new slide <presentation.json> <slide-id> [--preset blank|body|title]`
- `sonesta validate <presentation.json-or-slide.json>`
- `sonesta inspect <presentation.json-or-slide.json> --format json`
- `sonesta render <presentation.json>`
- `sonesta render-slide <presentation.json> <slide-id>`

Deck and slide management:

- `sonesta slides list <presentation.json>`
- `sonesta slides add <presentation.json> --slide <slide.json>`
- `sonesta slides remove <presentation.json> <slide-id> [--delete-files]`
- `sonesta slides rename <presentation.json> <slide-id> <new-slide-id>`
- `sonesta slides duplicate <presentation.json> <slide-id> <new-slide-id>`
- `sonesta slides move <presentation.json> <slide-id> --after <slide-id>`
- `sonesta slides elements <presentation.json> <slide-id>`
- `sonesta slides notes <presentation.json> <slide-id>`
- `sonesta slides set-notes <presentation.json> <slide-id> --text "..."`
- `sonesta slides clear-notes <presentation.json> <slide-id>`

Element mutation commands:

- `sonesta slides add-text|update-text`
- `sonesta slides add-image|update-image`
- `sonesta slides add-shape|update-shape`
- `sonesta slides add-table|update-table`
- `sonesta slides add-chart|update-chart`
- `sonesta slides remove-element <presentation.json> <slide-id> <element-id>`

Resource discovery:

- `sonesta themes --project-root <path>`
- `sonesta templates --project-root <path>`
- `sonesta assets list --project-root <path>`
- `sonesta assets inspect <asset-path>`

## Supported Elements

- `text`
- `image`
- `shape`
- `table`
- `chart`

## Current Layout And Rendering Support

- theme loading from `.sonesta/themes/<name>.json`
- template loading from `.sonesta/templates/<name>.json`
- named slot-based placement
- explicit `x/y/w/h` placement
- speaker notes via `notes_path`
- table `column_widths`
- chart `title`, `show_legend`, and `value_format`
- text bullets and paragraph payloads
- image `fit` modes: `contain`, `cover`, `stretch`
- `z_index`-aware render ordering

## Quick Start

```bash
PYTHONPATH=src python3 -m sonesta init .
PYTHONPATH=src python3 -m sonesta new presentation demo
PYTHONPATH=src python3 -m sonesta new slide presentations/demo/presentation.json overview --preset blank
PYTHONPATH=src python3 -m sonesta slides add-text presentations/demo/presentation.json overview headline \
  --text "Lorem Ipsum Overview" --x 1 --y 1 --w 4 --h 0.6 --style headline
PYTHONPATH=src python3 -m sonesta slides add-text presentations/demo/presentation.json overview bullets \
  --bullets-json '["Lorem ipsum dolor sit amet","Sed do eiusmod tempor","Ut enim ad minim veniam"]' \
  --x 1 --y 1.8 --w 5 --h 2.2 --style body
PYTHONPATH=src python3 -m sonesta validate presentations/demo/presentation.json --format json
PYTHONPATH=src python3 -m sonesta render presentations/demo/presentation.json --format json
```

This creates a `.pptx` under `.sonesta/builds/demo/demo.pptx`.

## Example Decks

Basic reference deck:

- [examples/basic](/Users/jjhorton/tools/ep/sonesta/examples/basic)

Lorem ipsum demo deck:

- [presentation.json](/Users/jjhorton/tools/ep/sonesta/examples/presentations/lorem_demo/presentation.json)
- [lorem_demo.pptx](/Users/jjhorton/tools/ep/sonesta/examples/.sonesta/builds/lorem_demo/lorem_demo.pptx)

Useful example commands:

```bash
PYTHONPATH=src python3 -m sonesta validate examples/basic/presentations/demo/presentation.json --format json
PYTHONPATH=src python3 -m sonesta render examples/basic/presentations/demo/presentation.json --format json
PYTHONPATH=src python3 -m sonesta inspect examples/presentations/lorem_demo/presentation.json --format json
PYTHONPATH=src python3 -m sonesta render-slide examples/presentations/lorem_demo/presentation.json overview --format json
```

## Layout

```text
.sonesta/
presentations/
assets/
```

## Development

Run tests with:

```bash
PYTHONPATH=src pytest -q
```
