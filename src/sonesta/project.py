from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from sonesta.errors import IoError, SchemaError, UsageError
from sonesta.models import (
    BuildConfig,
    LoadedPresentation,
    LoadedSlide,
    PresentationSpec,
    ProjectConfig,
    SlideSpec,
    TemplateSpec,
    ThemeSpec,
)


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".sonesta" / "config.json").exists():
            return candidate
    raise UsageError("could not find Sonesta project root from the provided path")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IoError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaError(f"invalid JSON in {path}: {exc}") from exc


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_project_config(project_root: Path) -> ProjectConfig:
    raw = load_json(project_root / ".sonesta" / "config.json")
    try:
        return ProjectConfig.model_validate(raw)
    except PydanticValidationError as exc:
        raise SchemaError(f"invalid project config: {exc}") from exc


def resolve_theme_path(project_root: Path, theme_ref: str) -> Path:
    candidate = Path(theme_ref)
    if candidate.is_absolute():
        return candidate
    named = project_root / ".sonesta" / "themes" / f"{theme_ref}.json"
    if named.exists():
        return named
    return (project_root / candidate).resolve()


def resolve_template_path(project_root: Path, template_ref: str) -> Path:
    candidate = Path(template_ref)
    if candidate.is_absolute():
        return candidate
    named = project_root / ".sonesta" / "templates" / f"{template_ref}.json"
    if named.exists():
        return named
    return (project_root / candidate).resolve()


def load_theme(project_root: Path, theme_ref: str | None) -> ThemeSpec | None:
    if not theme_ref:
        return None
    raw = load_json(resolve_theme_path(project_root, theme_ref))
    try:
        return ThemeSpec.model_validate(raw)
    except PydanticValidationError as exc:
        raise SchemaError(f"invalid theme spec: {exc}") from exc


def load_template(project_root: Path, template_ref: str | None) -> TemplateSpec | None:
    if not template_ref:
        return None
    raw = load_json(resolve_template_path(project_root, template_ref))
    try:
        return TemplateSpec.model_validate(raw)
    except PydanticValidationError as exc:
        raise SchemaError(f"invalid template spec: {exc}") from exc


def load_presentation(presentation_path: Path) -> LoadedPresentation:
    resolved_presentation = presentation_path.resolve()
    project_root = find_project_root(resolved_presentation)
    raw = load_json(resolved_presentation)
    try:
        spec = PresentationSpec.model_validate(raw)
    except PydanticValidationError as exc:
        raise SchemaError(f"invalid presentation spec: {exc}") from exc

    slides: list[LoadedSlide] = []
    base_dir = resolved_presentation.parent
    for slide_ref in spec.slides:
        slide_path = (base_dir / slide_ref).resolve()
        raw_slide = load_json(slide_path)
        try:
            slide_spec = SlideSpec.model_validate(raw_slide)
        except PydanticValidationError as exc:
            raise SchemaError(f"invalid slide spec {slide_path}: {exc}") from exc
        slides.append(LoadedSlide(path=slide_path, spec=slide_spec))

    return LoadedPresentation(
        project_root=project_root,
        presentation_path=resolved_presentation,
        spec=spec,
        slides=slides,
    )


def load_slide(slide_path: Path) -> LoadedSlide:
    resolved_slide = slide_path.resolve()
    raw_slide = load_json(resolved_slide)
    try:
        slide_spec = SlideSpec.model_validate(raw_slide)
    except PydanticValidationError as exc:
        raise SchemaError(f"invalid slide spec {resolved_slide}: {exc}") from exc
    return LoadedSlide(path=resolved_slide, spec=slide_spec)


def build_single_slide_presentation(presentation_path: Path, slide_id: str, output_path: str | None = None) -> LoadedPresentation:
    loaded = load_presentation(presentation_path)
    target_slide = next((slide for slide in loaded.slides if slide.spec.slide_id == slide_id), None)
    if target_slide is None:
        raise UsageError(f"slide_id not found: {slide_id}")

    presentation_id = f"{loaded.spec.presentation_id}__{slide_id}"
    spec = PresentationSpec(
        version=loaded.spec.version,
        presentation_id=presentation_id,
        title=target_slide.spec.title or loaded.spec.title,
        page_size=loaded.spec.page_size,
        theme=loaded.spec.theme,
        default_template=loaded.spec.default_template,
        slides=[str(target_slide.path)],
        build=BuildConfig(output=output_path or f".sonesta/builds/{presentation_id}/{presentation_id}.pptx"),
    )
    return LoadedPresentation(
        project_root=loaded.project_root,
        presentation_path=loaded.presentation_path,
        spec=spec,
        slides=[target_slide],
    )
