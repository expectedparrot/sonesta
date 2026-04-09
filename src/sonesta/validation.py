from __future__ import annotations

from pathlib import Path
from typing import Any

from sonesta.models import BaseElement, ChartElement, ImageElement, LoadedPresentation, LoadedSlide
from sonesta.project import load_template, load_theme


def _issue(
    severity: str,
    code: str,
    message: str,
    path: Path,
    field: str | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "path": str(path),
        "message": message,
    }
    if field is not None:
        issue["field"] = field
    return issue


def validate_presentation(loaded: LoadedPresentation) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    slide_ids: set[str] = set()
    if loaded.spec.theme:
        try:
            load_theme(loaded.project_root, loaded.spec.theme)
        except Exception:
            issues.append(
                _issue(
                    "error",
                    "missing_theme",
                    f"theme could not be loaded: {loaded.spec.theme}",
                    loaded.presentation_path,
                    "/theme",
                )
            )

    default_template = None
    if loaded.spec.default_template:
        try:
            default_template = load_template(loaded.project_root, loaded.spec.default_template)
        except Exception:
            issues.append(
                _issue(
                    "error",
                    "missing_template",
                    f"default template could not be loaded: {loaded.spec.default_template}",
                    loaded.presentation_path,
                    "/default_template",
                )
            )

    for slide_index, loaded_slide in enumerate(loaded.slides):
        slide = loaded_slide.spec
        if slide.slide_id in slide_ids:
            issues.append(
                _issue(
                    "error",
                    "duplicate_slide_id",
                    f"duplicate slide_id: {slide.slide_id}",
                    loaded_slide.path,
                    "/slide_id",
                )
            )
        slide_ids.add(slide.slide_id)

        template = default_template
        if slide.template:
            try:
                template = load_template(loaded.project_root, slide.template)
            except Exception:
                issues.append(
                    _issue(
                        "error",
                        "missing_template",
                        f"template could not be loaded: {slide.template}",
                        loaded_slide.path,
                        "/template",
                    )
                )
                template = None

        for element_index, element in enumerate(slide.elements):
            resolved_box = resolve_element_box(element, template)
            if resolved_box is None:
                issues.append(
                    _issue(
                        "error",
                        "missing_geometry",
                        f"element {element.element_id} has no resolved geometry",
                        loaded_slide.path,
                        f"/elements/{element_index}",
                    )
                )
            else:
                x, y, w, h = resolved_box
                if x < 0 or y < 0 or w <= 0 or h <= 0:
                    issues.append(
                        _issue(
                            "error",
                            "invalid_geometry",
                            f"invalid geometry for element {element.element_id}",
                            loaded_slide.path,
                            f"/elements/{element_index}",
                        )
                    )

            if isinstance(element, ImageElement):
                asset_path = resolve_asset_path(
                    loaded.project_root,
                    loaded_slide.path.parent,
                    element.path,
                )
                if not asset_path.exists():
                    issues.append(
                        _issue(
                            "error",
                            "missing_asset",
                            f"referenced asset does not exist: {element.path}",
                            loaded_slide.path,
                            f"/elements/{element_index}/path",
                        )
                    )
            if isinstance(element, ChartElement) and element.chart_type == "pie" and len(element.series) != 1:
                issues.append(
                    _issue(
                        "error",
                        "invalid_chart",
                        "pie charts must include exactly one series",
                        loaded_slide.path,
                        f"/elements/{element_index}/series",
                    )
                )

        if slide_index == 0 and slide.title is None and not slide.elements:
            issues.append(
                _issue(
                    "warning",
                    "empty_first_slide",
                    "first slide has neither title nor elements",
                    loaded_slide.path,
                )
            )

    return {"ok": not any(issue["severity"] == "error" for issue in issues), "issues": issues}


def validate_slide(
    loaded_slide: LoadedSlide,
    project_root: Path,
    theme_ref: str | None = None,
    default_template_ref: str | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if theme_ref:
        try:
            load_theme(project_root, theme_ref)
        except Exception:
            issues.append(
                _issue(
                    "error",
                    "missing_theme",
                    f"theme could not be loaded: {theme_ref}",
                    loaded_slide.path,
                )
            )

    default_template = None
    if default_template_ref:
        try:
            default_template = load_template(project_root, default_template_ref)
        except Exception:
            issues.append(
                _issue(
                    "error",
                    "missing_template",
                    f"default template could not be loaded: {default_template_ref}",
                    loaded_slide.path,
                )
            )

    template = default_template
    if loaded_slide.spec.template:
        try:
            template = load_template(project_root, loaded_slide.spec.template)
        except Exception:
            issues.append(
                _issue(
                    "error",
                    "missing_template",
                    f"template could not be loaded: {loaded_slide.spec.template}",
                    loaded_slide.path,
                    "/template",
                )
            )
            template = None

    for element_index, element in enumerate(loaded_slide.spec.elements):
        resolved_box = resolve_element_box(element, template)
        if resolved_box is None:
            issues.append(
                _issue(
                    "error",
                    "missing_geometry",
                    f"element {element.element_id} has no resolved geometry",
                    loaded_slide.path,
                    f"/elements/{element_index}",
                )
            )
        else:
            x, y, w, h = resolved_box
            if x < 0 or y < 0 or w <= 0 or h <= 0:
                issues.append(
                    _issue(
                        "error",
                        "invalid_geometry",
                        f"invalid geometry for element {element.element_id}",
                        loaded_slide.path,
                        f"/elements/{element_index}",
                    )
                )
        if isinstance(element, ImageElement):
            asset_path = resolve_asset_path(project_root, loaded_slide.path.parent, element.path)
            if not asset_path.exists():
                issues.append(
                    _issue(
                        "error",
                        "missing_asset",
                        f"referenced asset does not exist: {element.path}",
                        loaded_slide.path,
                        f"/elements/{element_index}/path",
                    )
                )
        if isinstance(element, ChartElement) and element.chart_type == "pie" and len(element.series) != 1:
            issues.append(
                _issue(
                    "error",
                    "invalid_chart",
                    "pie charts must include exactly one series",
                    loaded_slide.path,
                    f"/elements/{element_index}/series",
                )
            )

    return {"ok": not any(issue["severity"] == "error" for issue in issues), "issues": issues}


def resolve_asset_path(project_root: Path, slide_dir: Path, raw_path: str) -> Path:
    asset_path = Path(raw_path)
    if asset_path.is_absolute():
        return asset_path

    project_relative = (project_root / asset_path).resolve()
    if project_relative.exists():
        return project_relative

    return (slide_dir / asset_path).resolve()


def resolve_element_box(
    element: BaseElement,
    template,
) -> tuple[float, float, float, float] | None:
    if all(value is not None for value in (element.x, element.y, element.w, element.h)):
        return (element.x, element.y, element.w, element.h)
    if element.slot and template is not None:
        slot = template.slots.get(element.slot)
        if slot is not None:
            return (slot.x, slot.y, slot.w, slot.h)
    return None
