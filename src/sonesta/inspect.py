from __future__ import annotations

from typing import Any

from sonesta.models import BaseElement, LoadedPresentation, LoadedSlide
from sonesta.project import load_template, load_theme
from sonesta.validation import resolve_asset_path, resolve_element_box


def inspect_presentation(loaded: LoadedPresentation) -> dict[str, Any]:
    theme = load_theme(loaded.project_root, loaded.spec.theme) if loaded.spec.theme else None
    default_template = (
        load_template(loaded.project_root, loaded.spec.default_template)
        if loaded.spec.default_template
        else None
    )
    return {
        "presentation": loaded.spec.model_dump(mode="json"),
        "presentation_path": str(loaded.presentation_path),
        "project_root": str(loaded.project_root),
        "theme": theme.model_dump(mode="json") if theme else None,
        "slides": [
            {
                "path": str(loaded_slide.path),
                "slide": loaded_slide.spec.model_dump(mode="json"),
                "resolved_template": (
                    (load_template(loaded.project_root, loaded_slide.spec.template)).model_dump(mode="json")
                    if loaded_slide.spec.template
                    else (default_template.model_dump(mode="json") if default_template else None)
                ),
                "resolved_elements": [
                    {
                        **element.model_dump(mode="json"),
                        "resolved_box": resolve_element_box(
                            element,
                            load_template(loaded.project_root, loaded_slide.spec.template)
                            if loaded_slide.spec.template
                            else default_template,
                        ),
                    }
                    for element in loaded_slide.spec.elements
                ],
                "assets": [
                    str(resolve_asset_path(loaded.project_root, loaded_slide.path.parent, element.path))
                    for element in loaded_slide.spec.elements
                    if getattr(element, "type", None) == "image"
                ],
                "element_count": len(loaded_slide.spec.elements),
            }
            for loaded_slide in loaded.slides
        ],
    }


def inspect_slide(
    loaded_slide: LoadedSlide,
    project_root,
    theme_ref: str | None = None,
    default_template_ref: str | None = None,
) -> dict[str, Any]:
    theme = load_theme(project_root, theme_ref) if theme_ref else None
    default_template = load_template(project_root, default_template_ref) if default_template_ref else None
    template = (
        load_template(project_root, loaded_slide.spec.template)
        if loaded_slide.spec.template
        else default_template
    )
    notes_text = None
    if loaded_slide.spec.notes_path:
        notes_path = (loaded_slide.path.parent / loaded_slide.spec.notes_path).resolve()
        if notes_path.exists():
            notes_text = notes_path.read_text(encoding="utf-8")
    return {
        "path": str(loaded_slide.path),
        "slide": loaded_slide.spec.model_dump(mode="json"),
        "theme": theme.model_dump(mode="json") if theme else None,
        "resolved_template": template.model_dump(mode="json") if template else None,
        "resolved_elements": [
            {
                **element.model_dump(mode="json"),
                "resolved_box": resolve_element_box(element, template),
            }
            for element in loaded_slide.spec.elements
        ],
        "assets": [
            str(resolve_asset_path(project_root, loaded_slide.path.parent, element.path))
            for element in loaded_slide.spec.elements
            if getattr(element, "type", None) == "image"
        ],
        "notes_text": notes_text,
        "element_count": len(loaded_slide.spec.elements),
    }


def inspect_element(element: BaseElement) -> dict[str, Any]:
    return element.model_dump(mode="json")
