from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from PIL import Image

from sonesta.errors import IoError, SonestaError, ValidationError
from sonesta.inspect import inspect_presentation, inspect_slide
from sonesta.project import build_single_slide_presentation, dump_json, find_project_root, load_json, load_presentation, load_slide
from sonesta.render import render_presentation
from sonesta.validation import validate_presentation, validate_slide

app = typer.Typer(help="Agent-focused CLI for deterministic PowerPoint generation.")
new_app = typer.Typer(help="Create new Sonesta resources.")
slides_app = typer.Typer(help="Manage slides in a presentation.")
assets_app = typer.Typer(help="Inspect project assets.")
app.add_typer(new_app, name="new")
app.add_typer(slides_app, name="slides")
app.add_typer(assets_app, name="assets")


def _emit(payload: object, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(payload, indent=2))
        return
    if isinstance(payload, dict):
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(str(payload))


def _handle_error(exc: SonestaError, output_format: str) -> None:
    payload = {"ok": False, "error": {"code": exc.code, "message": exc.message, "details": []}}
    _emit(payload, output_format)
    raise typer.Exit(code=1)


def _normalize_slide_ref(presentation_path: Path, slide_path: Path) -> str:
    return str(slide_path.resolve().relative_to(presentation_path.parent.resolve()))


def _next_slide_path(presentation_path: Path, slug: str) -> Path:
    raw = load_json(presentation_path)
    count = len(raw["slides"]) + 1
    slides_dir = presentation_path.parent / "slides"
    return slides_dir / f"{count:03d}-{slug}.json"


def _next_slide_number(presentation_path: Path) -> int:
    raw = load_json(presentation_path)
    return len(raw["slides"]) + 1


def _load_slide_for_update(presentation_path: Path, slide_id: str) -> tuple[Path, dict[str, object]]:
    loaded = load_presentation(presentation_path)
    for loaded_slide in loaded.slides:
        if loaded_slide.spec.slide_id == slide_id:
            return loaded_slide.path, load_json(loaded_slide.path)
    raise ValidationError(f"slide_id not found: {slide_id}")


def _load_presentation_pairs(presentation_path: Path) -> tuple[dict[str, object], list[tuple[str, object]]]:
    raw = load_json(presentation_path)
    loaded = load_presentation(presentation_path)
    return raw, list(zip(raw["slides"], loaded.slides, strict=True))


def _resolve_notes_path(slide_path: Path, raw_slide: dict[str, object]) -> Path:
    notes_ref = raw_slide.get("notes_path")
    if isinstance(notes_ref, str) and notes_ref:
        return (slide_path.parent / notes_ref).resolve()
    default_name = f"{slide_path.stem}.md"
    notes_dir = slide_path.parent.parent / "notes"
    return (notes_dir / default_name).resolve()


def _append_element(
    presentation_path: Path,
    slide_id: str,
    element: dict[str, object],
) -> tuple[Path, dict[str, object]]:
    slide_path, raw_slide = _load_slide_for_update(presentation_path, slide_id)
    elements = list(raw_slide.get("elements", []))
    element_ids = {entry["element_id"] for entry in elements}
    if element["element_id"] in element_ids:
        raise ValidationError(f"element_id already exists: {element['element_id']}")
    elements.append(element)
    raw_slide["elements"] = elements
    dump_json(slide_path, raw_slide)
    return slide_path, raw_slide


def _find_element_index(elements: list[dict[str, object]], element_id: str) -> int:
    for index, element in enumerate(elements):
        if element.get("element_id") == element_id:
            return index
    raise ValidationError(f"element_id not found: {element_id}")


def _update_element(
    presentation_path: Path,
    slide_id: str,
    element_id: str,
    updater,
) -> tuple[Path, dict[str, object], dict[str, object]]:
    slide_path, raw_slide = _load_slide_for_update(presentation_path, slide_id)
    elements = list(raw_slide.get("elements", []))
    index = _find_element_index(elements, element_id)
    updated = updater(dict(elements[index]))
    elements[index] = updated
    raw_slide["elements"] = elements
    dump_json(slide_path, raw_slide)
    return slide_path, raw_slide, updated


def _apply_position(
    element: dict[str, object],
    slot: str | None,
    x: float | None,
    y: float | None,
    w: float | None,
    h: float | None,
) -> dict[str, object]:
    if slot is not None:
        element["slot"] = slot
        return element
    if None not in (x, y, w, h):
        element["x"] = x
        element["y"] = y
        element["w"] = w
        element["h"] = h
        return element
    raise ValidationError("provide either --slot or all of --x --y --w --h")


def _apply_optional_position(
    element: dict[str, object],
    slot: str | None,
    x: float | None,
    y: float | None,
    w: float | None,
    h: float | None,
) -> dict[str, object]:
    if slot is None and all(value is None for value in (x, y, w, h)):
        return element
    for key in ("slot", "x", "y", "w", "h"):
        element.pop(key, None)
    return _apply_position(element, slot, x, y, w, h)


def _parse_json_option(raw: str, label: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON for {label}: {exc}") from exc


def _build_slide_elements_for_preset(preset: str) -> list[dict[str, object]]:
    if preset == "blank":
        return []
    if preset == "body":
        return [
            {
                "element_id": "body",
                "type": "text",
                "slot": "body",
                "text": "",
                "style": "body",
            }
        ]
    if preset == "title":
        return [
            {
                "element_id": "subtitle",
                "type": "text",
                "slot": "body",
                "text": "",
                "style": "body",
                "font_size": 18,
            }
        ]
    raise ValidationError(f"unknown preset: {preset}")


def _list_json_names(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob("*.json") if path.is_file())


def _list_asset_entries(root: Path) -> list[dict[str, object]]:
    if not root.exists():
        return []
    entries: list[dict[str, object]] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        entries.append(
            {
                "path": str(path),
                "relative_path": str(path.relative_to(root)),
                "suffix": path.suffix.lower(),
                "byte_size": path.stat().st_size,
            }
        )
    return entries


@app.command("init")
def init_command(
    path: Path = typer.Argument(Path("."), exists=False, file_okay=False, dir_okay=True),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    try:
        root = path.resolve()
        (root / ".sonesta" / "templates").mkdir(parents=True, exist_ok=True)
        (root / ".sonesta" / "themes").mkdir(parents=True, exist_ok=True)
        (root / ".sonesta" / "builds").mkdir(parents=True, exist_ok=True)
        (root / ".sonesta" / "cache").mkdir(parents=True, exist_ok=True)
        (root / ".sonesta" / "logs").mkdir(parents=True, exist_ok=True)
        (root / "presentations").mkdir(parents=True, exist_ok=True)
        (root / "assets").mkdir(parents=True, exist_ok=True)

        dump_json(
            root / ".sonesta" / "config.json",
            {"version": 1, "default_output_format": "text", "default_page_size": "widescreen"},
        )
        dump_json(
            root / ".sonesta" / "themes" / "default.json",
            {
                "name": "default",
                "page_size": "widescreen",
                "colors": {"background": "#FFFFFF", "text": "#111111", "accent": "#1F5AA6"},
                "fonts": {"heading": "Aptos", "body": "Aptos"},
                "styles": {
                    "headline": {"font_family": "Aptos", "font_size": 22, "bold": True, "color": "#111111"},
                    "body": {"font_family": "Aptos", "font_size": 16, "bold": False, "color": "#111111"},
                },
            },
        )
        dump_json(
            root / ".sonesta" / "templates" / "default.json",
            {
                "name": "default",
                "slots": {
                    "hero": {"x": 0.8, "y": 1.4, "w": 5.8, "h": 4.8},
                    "body": {"x": 0.8, "y": 1.4, "w": 11.8, "h": 4.8},
                    "sidebar": {"x": 8.9, "y": 1.4, "w": 3.4, "h": 4.8},
                    "footer": {"x": 0.8, "y": 6.5, "w": 11.8, "h": 0.4},
                },
            },
        )
        _emit({"ok": True, "project_root": str(root)}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@new_app.command("presentation")
def new_presentation_command(
    name: str = typer.Argument(...),
    project_root: Path = typer.Option(Path("."), "--project-root", file_okay=False, dir_okay=True),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    try:
        root = project_root.resolve()
        presentation_dir = root / "presentations" / name
        slides_dir = presentation_dir / "slides"
        slides_dir.mkdir(parents=True, exist_ok=True)

        dump_json(
            slides_dir / "001-title.json",
            {
                "slide_id": "title",
                "kind": "title",
                "title": name.replace("-", " ").replace("_", " ").title(),
                "elements": [
                    {
                        "element_id": "subtitle",
                        "type": "text",
                        "slot": "body",
                        "text": "Generated by Sonesta",
                        "style": "body",
                        "font_size": 18,
                    }
                ],
            },
        )
        dump_json(
            presentation_dir / "presentation.json",
            {
                "version": 1,
                "presentation_id": name,
                "title": name.replace("-", " ").replace("_", " ").title(),
                "page_size": "widescreen",
                "theme": "default",
                "default_template": "default",
                "slides": ["slides/001-title.json"],
                "build": {"output": f".sonesta/builds/{name}/{name}.pptx"},
            },
        )
        _emit(
            {
                "ok": True,
                "presentation_path": str(presentation_dir / "presentation.json"),
                "slide_path": str(slides_dir / "001-title.json"),
            },
            output_format,
        )
    except SonestaError as exc:
        _handle_error(exc, output_format)


@new_app.command("slide")
def new_slide_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    title: str | None = typer.Option(None, "--title"),
    kind: str = typer.Option("content", "--kind"),
    template: str | None = typer.Option(None, "--template"),
    preset: str = typer.Option("blank", "--preset"),
    add: bool = typer.Option(True, "--add/--no-add"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        loaded = load_presentation(presentation_path)
        if slide_id in {loaded_slide.spec.slide_id for loaded_slide in loaded.slides}:
            raise ValidationError(f"slide_id already exists: {slide_id}")
        slug = slide_id.replace("_", "-")
        slide_path = _next_slide_path(presentation_path, slug)
        slide_title = title if title is not None else slide_id.replace("-", " ").replace("_", " ").title()
        dump_json(
            slide_path,
            {
                "slide_id": slide_id,
                "kind": kind,
                "title": slide_title,
                "template": template,
                "elements": _build_slide_elements_for_preset(preset),
            },
        )
        if add:
            raw = load_json(presentation_path)
            slide_ref = _normalize_slide_ref(presentation_path, slide_path)
            raw["slides"] = [*raw["slides"], slide_ref]
            dump_json(presentation_path, raw)
        _emit({"ok": True, "slide_path": str(slide_path), "added": add, "preset": preset}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("list")
def slides_list_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        loaded = load_presentation(presentation_path)
        payload = {
            "ok": True,
            "slides": [
                {"index": index, "slide_id": loaded_slide.spec.slide_id, "path": str(loaded_slide.path)}
                for index, loaded_slide in enumerate(loaded.slides)
            ],
        }
        _emit(payload, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("add")
def slides_add_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_path: Path = typer.Option(..., "--slide", exists=True, dir_okay=False),
    after: str | None = typer.Option(None, "--after"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        raw = load_json(presentation_path)
        slide_ref = _normalize_slide_ref(presentation_path, slide_path)
        slides = list(raw["slides"])
        if slide_ref in slides:
            _emit({"ok": True, "slides": slides}, output_format)
            return
        if after is None:
            slides.append(slide_ref)
        else:
            loaded = load_presentation(presentation_path)
            slide_ids = [slide.spec.slide_id for slide in loaded.slides]
            if after not in slide_ids:
                raise ValidationError(f"slide_id not found: {after}")
            insert_at = slide_ids.index(after) + 1
            slides.insert(insert_at, slide_ref)
        raw["slides"] = slides
        dump_json(presentation_path, raw)
        _emit({"ok": True, "slides": slides}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("remove")
def slides_remove_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    delete_files: bool = typer.Option(False, "--delete-files"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        raw, paired = _load_presentation_pairs(presentation_path)
        target_slide_path: Path | None = None
        remaining: list[str] = []
        for slide_ref, loaded_slide in paired:
            if loaded_slide.spec.slide_id == slide_id:
                target_slide_path = loaded_slide.path
            else:
                remaining.append(slide_ref)
        if target_slide_path is None:
            raise ValidationError(f"slide_id not found: {slide_id}")
        raw["slides"] = remaining
        dump_json(presentation_path, raw)
        removed_notes_path = None
        if delete_files and target_slide_path is not None:
            raw_slide = load_json(target_slide_path)
            notes_path = _resolve_notes_path(target_slide_path, raw_slide)
            if target_slide_path.exists():
                target_slide_path.unlink()
            if notes_path.exists():
                notes_path.unlink()
                removed_notes_path = str(notes_path)
        _emit({"ok": True, "slides": remaining, "deleted_slide_path": str(target_slide_path) if delete_files and target_slide_path else None, "deleted_notes_path": removed_notes_path}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("rename")
def slides_rename_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    new_slide_id: str = typer.Argument(...),
    title: str | None = typer.Option(None, "--title"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        loaded = load_presentation(presentation_path)
        existing_ids = {loaded_slide.spec.slide_id for loaded_slide in loaded.slides}
        if new_slide_id in existing_ids:
            raise ValidationError(f"slide_id already exists: {new_slide_id}")
        slide_path, raw_slide = _load_slide_for_update(presentation_path, slide_id)
        old_notes_path = _resolve_notes_path(slide_path, raw_slide) if raw_slide.get("notes_path") is not None else None
        new_name = f"{slide_path.stem.split('-', 1)[0]}-{new_slide_id.replace('_', '-')}.json"
        new_slide_path = slide_path.with_name(new_name)
        raw_slide["slide_id"] = new_slide_id
        if title is not None:
            raw_slide["title"] = title
        if old_notes_path is not None and old_notes_path.exists():
            new_notes_path = slide_path.parent.parent / "notes" / f"{new_slide_path.stem}.md"
            new_notes_path.parent.mkdir(parents=True, exist_ok=True)
            new_notes_path.write_text(old_notes_path.read_text(encoding="utf-8"), encoding="utf-8")
            raw_slide["notes_path"] = os.path.relpath(new_notes_path, start=new_slide_path.parent)
        dump_json(new_slide_path, raw_slide)
        if new_slide_path != slide_path and slide_path.exists():
            slide_path.unlink()
        if old_notes_path is not None and old_notes_path.exists():
            old_notes_path.unlink()

        raw_presentation = load_json(presentation_path)
        old_ref = _normalize_slide_ref(presentation_path, slide_path)
        new_ref = _normalize_slide_ref(presentation_path, new_slide_path)
        raw_presentation["slides"] = [new_ref if ref == old_ref else ref for ref in raw_presentation["slides"]]
        dump_json(presentation_path, raw_presentation)
        _emit({"ok": True, "old_slide_id": slide_id, "new_slide_id": new_slide_id, "slide_path": str(new_slide_path)}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("duplicate")
def slides_duplicate_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    new_slide_id: str = typer.Argument(...),
    after: str | None = typer.Option(None, "--after"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        loaded = load_presentation(presentation_path)
        if new_slide_id in {loaded_slide.spec.slide_id for loaded_slide in loaded.slides}:
            raise ValidationError(f"slide_id already exists: {new_slide_id}")
        source_slide_path, raw_slide = _load_slide_for_update(presentation_path, slide_id)
        next_number = _next_slide_number(presentation_path)
        new_slide_path = source_slide_path.parent / f"{next_number:03d}-{new_slide_id.replace('_', '-')}.json"
        duplicate_slide = json.loads(json.dumps(raw_slide))
        duplicate_slide["slide_id"] = new_slide_id

        source_notes_path = _resolve_notes_path(source_slide_path, raw_slide)
        if source_notes_path.exists():
            duplicate_notes_path = source_slide_path.parent.parent / "notes" / f"{new_slide_path.stem}.md"
            duplicate_notes_path.parent.mkdir(parents=True, exist_ok=True)
            duplicate_notes_path.write_text(source_notes_path.read_text(encoding="utf-8"), encoding="utf-8")
            duplicate_slide["notes_path"] = os.path.relpath(duplicate_notes_path, start=new_slide_path.parent)

        dump_json(new_slide_path, duplicate_slide)

        raw_presentation = load_json(presentation_path)
        new_ref = _normalize_slide_ref(presentation_path, new_slide_path)
        if after is None:
            raw_presentation["slides"].append(new_ref)
        else:
            slide_ids = [loaded_slide.spec.slide_id for loaded_slide in loaded.slides]
            if after not in slide_ids:
                raise ValidationError(f"slide_id not found: {after}")
            insert_at = slide_ids.index(after) + 1
            raw_presentation["slides"].insert(insert_at, new_ref)
        dump_json(presentation_path, raw_presentation)
        _emit({"ok": True, "source_slide_id": slide_id, "new_slide_id": new_slide_id, "slide_path": str(new_slide_path)}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("move")
def slides_move_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    after: str = typer.Option(..., "--after"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        raw = load_json(presentation_path)
        loaded = load_presentation(presentation_path)
        paired = list(zip(raw["slides"], loaded.slides, strict=True))
        source_index = next((idx for idx, (_, slide) in enumerate(paired) if slide.spec.slide_id == slide_id), None)
        target_index = next((idx for idx, (_, slide) in enumerate(paired) if slide.spec.slide_id == after), None)
        if source_index is None:
            raise ValidationError(f"slide_id not found: {slide_id}")
        if target_index is None:
            raise ValidationError(f"slide_id not found: {after}")
        item = raw["slides"].pop(source_index)
        if source_index < target_index:
            target_index -= 1
        raw["slides"].insert(target_index + 1, item)
        dump_json(presentation_path, raw)
        _emit({"ok": True, "slides": raw["slides"]}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("elements")
def slides_elements_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        _, raw_slide = _load_slide_for_update(presentation_path, slide_id)
        payload = {
            "ok": True,
            "slide_id": slide_id,
            "elements": raw_slide.get("elements", []),
        }
        _emit(payload, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("notes")
def slides_notes_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        slide_path, raw_slide = _load_slide_for_update(presentation_path, slide_id)
        notes_path = _resolve_notes_path(slide_path, raw_slide)
        notes_text = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
        _emit(
            {
                "ok": True,
                "slide_id": slide_id,
                "notes_path": str(notes_path),
                "notes_text": notes_text,
            },
            output_format,
        )
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("set-notes")
def slides_set_notes_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    text: str = typer.Option(..., "--text"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        slide_path, raw_slide = _load_slide_for_update(presentation_path, slide_id)
        notes_path = _resolve_notes_path(slide_path, raw_slide)
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(text, encoding="utf-8")
        if raw_slide.get("notes_path") is None:
            raw_slide["notes_path"] = os.path.relpath(notes_path, start=slide_path.parent)
            dump_json(slide_path, raw_slide)
        _emit(
            {
                "ok": True,
                "slide_id": slide_id,
                "notes_path": str(notes_path),
                "notes_text": text,
            },
            output_format,
        )
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("clear-notes")
def slides_clear_notes_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        slide_path, raw_slide = _load_slide_for_update(presentation_path, slide_id)
        notes_path = _resolve_notes_path(slide_path, raw_slide)
        if notes_path.exists():
            notes_path.unlink()
        if raw_slide.get("notes_path") is not None:
            raw_slide["notes_path"] = None
            dump_json(slide_path, raw_slide)
        _emit({"ok": True, "slide_id": slide_id, "notes_path": str(notes_path)}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("remove-element")
def slides_remove_element_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        slide_path, raw_slide = _load_slide_for_update(presentation_path, slide_id)
        elements = list(raw_slide.get("elements", []))
        index = _find_element_index(elements, element_id)
        removed = elements.pop(index)
        raw_slide["elements"] = elements
        dump_json(slide_path, raw_slide)
        _emit(
            {
                "ok": True,
                "slide_path": str(slide_path),
                "removed": removed,
                "element_count": len(elements),
            },
            output_format,
        )
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("add-text")
def slides_add_text_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    text: str = typer.Option("", "--text"),
    bullets_json: str | None = typer.Option(None, "--bullets-json"),
    paragraphs_json: str | None = typer.Option(None, "--paragraphs-json"),
    slot: str | None = typer.Option(None, "--slot"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    w: float | None = typer.Option(None, "--w"),
    h: float | None = typer.Option(None, "--h"),
    style: str | None = typer.Option(None, "--style"),
    font_size: int | None = typer.Option(None, "--font-size"),
    bold: bool | None = typer.Option(None, "--bold/--no-bold"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        element: dict[str, object] = {"element_id": element_id, "type": "text", "text": text}
        if bullets_json is not None:
            bullets = _parse_json_option(bullets_json, "bullets_json")
            element["paragraphs"] = [{"text": item, "bullet": True, "level": 0} for item in bullets]
            element["text"] = ""
        if paragraphs_json is not None:
            element["paragraphs"] = _parse_json_option(paragraphs_json, "paragraphs_json")
            element["text"] = ""
        _apply_position(element, slot, x, y, w, h)
        if style is not None:
            element["style"] = style
        if font_size is not None:
            element["font_size"] = font_size
        if bold is not None:
            element["bold"] = bold
        slide_path, raw_slide = _append_element(presentation_path, slide_id, element)
        _emit({"ok": True, "slide_path": str(slide_path), "element_count": len(raw_slide["elements"])}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("update-text")
def slides_update_text_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    text: str | None = typer.Option(None, "--text"),
    bullets_json: str | None = typer.Option(None, "--bullets-json"),
    paragraphs_json: str | None = typer.Option(None, "--paragraphs-json"),
    slot: str | None = typer.Option(None, "--slot"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    w: float | None = typer.Option(None, "--w"),
    h: float | None = typer.Option(None, "--h"),
    style: str | None = typer.Option(None, "--style"),
    font_size: int | None = typer.Option(None, "--font-size"),
    bold: bool | None = typer.Option(None, "--bold/--no-bold"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        def updater(element: dict[str, object]) -> dict[str, object]:
            if element.get("type") != "text":
                raise ValidationError(f"element {element_id} is not a text element")
            if text is not None:
                element["text"] = text
                element.pop("paragraphs", None)
            if bullets_json is not None:
                bullets = _parse_json_option(bullets_json, "bullets_json")
                element["paragraphs"] = [{"text": item, "bullet": True, "level": 0} for item in bullets]
                element["text"] = ""
            if paragraphs_json is not None:
                element["paragraphs"] = _parse_json_option(paragraphs_json, "paragraphs_json")
                element["text"] = ""
            _apply_optional_position(element, slot, x, y, w, h)
            if style is not None:
                element["style"] = style
            if font_size is not None:
                element["font_size"] = font_size
            if bold is not None:
                element["bold"] = bold
            return element

        slide_path, raw_slide, updated = _update_element(presentation_path, slide_id, element_id, updater)
        _emit({"ok": True, "slide_path": str(slide_path), "updated": updated, "element_count": len(raw_slide["elements"])}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("add-image")
def slides_add_image_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    path: str = typer.Option(..., "--path"),
    slot: str | None = typer.Option(None, "--slot"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    w: float | None = typer.Option(None, "--w"),
    h: float | None = typer.Option(None, "--h"),
    fit: str = typer.Option("contain", "--fit"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        element: dict[str, object] = {"element_id": element_id, "type": "image", "path": path, "fit": fit}
        _apply_position(element, slot, x, y, w, h)
        slide_path, raw_slide = _append_element(presentation_path, slide_id, element)
        _emit({"ok": True, "slide_path": str(slide_path), "element_count": len(raw_slide["elements"])}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("update-image")
def slides_update_image_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    path: str | None = typer.Option(None, "--path"),
    slot: str | None = typer.Option(None, "--slot"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    w: float | None = typer.Option(None, "--w"),
    h: float | None = typer.Option(None, "--h"),
    fit: str | None = typer.Option(None, "--fit"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        def updater(element: dict[str, object]) -> dict[str, object]:
            if element.get("type") != "image":
                raise ValidationError(f"element {element_id} is not an image element")
            if path is not None:
                element["path"] = path
            _apply_optional_position(element, slot, x, y, w, h)
            if fit is not None:
                element["fit"] = fit
            return element

        slide_path, raw_slide, updated = _update_element(presentation_path, slide_id, element_id, updater)
        _emit({"ok": True, "slide_path": str(slide_path), "updated": updated, "element_count": len(raw_slide["elements"])}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("add-shape")
def slides_add_shape_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    shape: str = typer.Option("rect", "--shape"),
    text: str | None = typer.Option(None, "--text"),
    slot: str | None = typer.Option(None, "--slot"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    w: float | None = typer.Option(None, "--w"),
    h: float | None = typer.Option(None, "--h"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        element: dict[str, object] = {"element_id": element_id, "type": "shape", "shape": shape}
        _apply_position(element, slot, x, y, w, h)
        if text is not None:
            element["text"] = text
        slide_path, raw_slide = _append_element(presentation_path, slide_id, element)
        _emit({"ok": True, "slide_path": str(slide_path), "element_count": len(raw_slide["elements"])}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("update-shape")
def slides_update_shape_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    shape: str | None = typer.Option(None, "--shape"),
    text: str | None = typer.Option(None, "--text"),
    slot: str | None = typer.Option(None, "--slot"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    w: float | None = typer.Option(None, "--w"),
    h: float | None = typer.Option(None, "--h"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        def updater(element: dict[str, object]) -> dict[str, object]:
            if element.get("type") != "shape":
                raise ValidationError(f"element {element_id} is not a shape element")
            if shape is not None:
                element["shape"] = shape
            if text is not None:
                element["text"] = text
            _apply_optional_position(element, slot, x, y, w, h)
            return element

        slide_path, raw_slide, updated = _update_element(presentation_path, slide_id, element_id, updater)
        _emit({"ok": True, "slide_path": str(slide_path), "updated": updated, "element_count": len(raw_slide["elements"])}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("add-table")
def slides_add_table_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    rows_json: str = typer.Option(..., "--rows-json"),
    slot: str | None = typer.Option(None, "--slot"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    w: float | None = typer.Option(None, "--w"),
    h: float | None = typer.Option(None, "--h"),
    column_widths_json: str | None = typer.Option(None, "--column-widths-json"),
    first_row_header: bool = typer.Option(True, "--first-row-header/--no-first-row-header"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        element: dict[str, object] = {
            "element_id": element_id,
            "type": "table",
            "rows": _parse_json_option(rows_json, "rows_json"),
            "first_row_header": first_row_header,
        }
        _apply_position(element, slot, x, y, w, h)
        if column_widths_json is not None:
            element["column_widths"] = _parse_json_option(column_widths_json, "column_widths_json")
        slide_path, raw_slide = _append_element(presentation_path, slide_id, element)
        _emit({"ok": True, "slide_path": str(slide_path), "element_count": len(raw_slide["elements"])}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("update-table")
def slides_update_table_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    rows_json: str | None = typer.Option(None, "--rows-json"),
    slot: str | None = typer.Option(None, "--slot"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    w: float | None = typer.Option(None, "--w"),
    h: float | None = typer.Option(None, "--h"),
    column_widths_json: str | None = typer.Option(None, "--column-widths-json"),
    first_row_header: bool | None = typer.Option(None, "--first-row-header/--no-first-row-header"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        def updater(element: dict[str, object]) -> dict[str, object]:
            if element.get("type") != "table":
                raise ValidationError(f"element {element_id} is not a table element")
            if rows_json is not None:
                element["rows"] = _parse_json_option(rows_json, "rows_json")
            _apply_optional_position(element, slot, x, y, w, h)
            if column_widths_json is not None:
                element["column_widths"] = _parse_json_option(column_widths_json, "column_widths_json")
            if first_row_header is not None:
                element["first_row_header"] = first_row_header
            return element

        slide_path, raw_slide, updated = _update_element(presentation_path, slide_id, element_id, updater)
        _emit({"ok": True, "slide_path": str(slide_path), "updated": updated, "element_count": len(raw_slide["elements"])}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("add-chart")
def slides_add_chart_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    chart_type: str = typer.Option(..., "--chart-type"),
    categories_json: str = typer.Option(..., "--categories-json"),
    series_json: str = typer.Option(..., "--series-json"),
    slot: str | None = typer.Option(None, "--slot"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    w: float | None = typer.Option(None, "--w"),
    h: float | None = typer.Option(None, "--h"),
    title: str | None = typer.Option(None, "--title"),
    show_legend: bool = typer.Option(True, "--show-legend/--hide-legend"),
    value_format: str | None = typer.Option(None, "--value-format"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        element: dict[str, object] = {
            "element_id": element_id,
            "type": "chart",
            "chart_type": chart_type,
            "categories": _parse_json_option(categories_json, "categories_json"),
            "series": _parse_json_option(series_json, "series_json"),
            "show_legend": show_legend,
        }
        _apply_position(element, slot, x, y, w, h)
        if title is not None:
            element["title"] = title
        if value_format is not None:
            element["value_format"] = value_format
        slide_path, raw_slide = _append_element(presentation_path, slide_id, element)
        _emit({"ok": True, "slide_path": str(slide_path), "element_count": len(raw_slide["elements"])}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@slides_app.command("update-chart")
def slides_update_chart_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    element_id: str = typer.Argument(...),
    chart_type: str | None = typer.Option(None, "--chart-type"),
    categories_json: str | None = typer.Option(None, "--categories-json"),
    series_json: str | None = typer.Option(None, "--series-json"),
    slot: str | None = typer.Option(None, "--slot"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    w: float | None = typer.Option(None, "--w"),
    h: float | None = typer.Option(None, "--h"),
    title: str | None = typer.Option(None, "--title"),
    show_legend: bool | None = typer.Option(None, "--show-legend/--hide-legend"),
    value_format: str | None = typer.Option(None, "--value-format"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        def updater(element: dict[str, object]) -> dict[str, object]:
            if element.get("type") != "chart":
                raise ValidationError(f"element {element_id} is not a chart element")
            if chart_type is not None:
                element["chart_type"] = chart_type
            if categories_json is not None:
                element["categories"] = _parse_json_option(categories_json, "categories_json")
            if series_json is not None:
                element["series"] = _parse_json_option(series_json, "series_json")
            _apply_optional_position(element, slot, x, y, w, h)
            if title is not None:
                element["title"] = title
            if show_legend is not None:
                element["show_legend"] = show_legend
            if value_format is not None:
                element["value_format"] = value_format
            return element

        slide_path, raw_slide, updated = _update_element(presentation_path, slide_id, element_id, updater)
        _emit({"ok": True, "slide_path": str(slide_path), "updated": updated, "element_count": len(raw_slide["elements"])}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@app.command("themes")
def themes_list_command(
    project_root: Path = typer.Option(Path("."), "--project-root", file_okay=False, dir_okay=True),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    root = project_root.resolve()
    payload = {
        "ok": True,
        "themes": _list_json_names(root / ".sonesta" / "themes"),
    }
    _emit(payload, output_format)


@app.command("templates")
def templates_list_command(
    project_root: Path = typer.Option(Path("."), "--project-root", file_okay=False, dir_okay=True),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    root = project_root.resolve()
    payload = {
        "ok": True,
        "templates": _list_json_names(root / ".sonesta" / "templates"),
    }
    _emit(payload, output_format)


@assets_app.command("list")
def assets_list_command(
    project_root: Path = typer.Option(Path("."), "--project-root", file_okay=False, dir_okay=True),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    root = project_root.resolve()
    assets_root = root / "assets"
    payload = {
        "ok": True,
        "assets_root": str(assets_root),
        "assets": _list_asset_entries(assets_root),
    }
    _emit(payload, output_format)


@assets_app.command("inspect")
def assets_inspect_command(
    asset_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        payload = {
            "ok": True,
            "path": str(asset_path.resolve()),
            "byte_size": asset_path.stat().st_size,
            "suffix": asset_path.suffix.lower(),
        }
        try:
            with Image.open(asset_path) as image:
                payload["image"] = {
                    "width_px": image.width,
                    "height_px": image.height,
                    "mode": image.mode,
                    "format": image.format,
                }
        except Exception:
            payload["image"] = None
        _emit(payload, output_format)
    except FileNotFoundError as exc:
        _handle_error(IoError(f"file not found: {asset_path}"), output_format)


@app.command("validate")
def validate_command(
    source_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    theme: str | None = typer.Option(None, "--theme"),
    default_template: str | None = typer.Option(None, "--default-template"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    try:
        if source_path.name == "presentation.json":
            loaded = load_presentation(source_path)
            result = validate_presentation(loaded)
        else:
            loaded_slide = load_slide(source_path)
            project_root = find_project_root(source_path)
            result = validate_slide(loaded_slide, project_root, theme_ref=theme, default_template_ref=default_template)
        if not result["ok"]:
            _emit(result, output_format)
            raise typer.Exit(code=1)
        _emit(result, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@app.command("inspect")
def inspect_command(
    source_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    theme: str | None = typer.Option(None, "--theme"),
    default_template: str | None = typer.Option(None, "--default-template"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    try:
        if source_path.name == "presentation.json":
            loaded = load_presentation(source_path)
            _emit(inspect_presentation(loaded), output_format)
        else:
            loaded_slide = load_slide(source_path)
            project_root = find_project_root(source_path)
            _emit(
                inspect_slide(
                    loaded_slide,
                    project_root,
                    theme_ref=theme,
                    default_template_ref=default_template,
                ),
                output_format,
            )
    except SonestaError as exc:
        _handle_error(exc, output_format)


@app.command("render")
def render_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    try:
        loaded = load_presentation(presentation_path)
        validation = validate_presentation(loaded)
        if not validation["ok"]:
            raise ValidationError("presentation contains validation errors")
        manifest = render_presentation(loaded)
        _emit({"ok": True, "manifest": manifest}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)


@app.command("render-slide")
def render_slide_command(
    presentation_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    slide_id: str = typer.Argument(...),
    output_path: str | None = typer.Option(None, "--output"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    try:
        loaded = build_single_slide_presentation(presentation_path, slide_id, output_path=output_path)
        validation = validate_presentation(loaded)
        if not validation["ok"]:
            raise ValidationError("slide contains validation errors")
        manifest = render_presentation(loaded)
        _emit({"ok": True, "manifest": manifest}, output_format)
    except SonestaError as exc:
        _handle_error(exc, output_format)
