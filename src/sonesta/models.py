from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ElementType = Literal["text", "image", "shape", "table", "chart"]
ShapeKind = Literal["rect", "ellipse", "line"]
PageSize = Literal["standard", "widescreen"]
ChartType = Literal["bar", "column", "line", "pie"]


class BuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: str | None = None


class BaseElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_id: str
    type: ElementType
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    slot: str | None = None
    style: str | None = None
    z_index: int | None = None
    visible: bool = True

    @model_validator(mode="after")
    def ensure_geometry_or_slot(self) -> "BaseElement":
        has_box = all(value is not None for value in (self.x, self.y, self.w, self.h))
        if not has_box and self.slot is None:
            raise ValueError("element must define x/y/w/h or a slot")
        return self


class TextElement(BaseElement):
    type: Literal["text"]
    text: str = ""
    paragraphs: list["TextParagraph"] = Field(default_factory=list)
    font_size: int | None = None
    bold: bool | None = None
    line_spacing: float | None = None  # multiplier, e.g. 1.3 for 130%


class TextParagraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    bullet: bool = False
    level: int = 0
    bold: bool | None = None
    space_before: int | None = None  # points
    space_after: int | None = None   # points
    url: str | None = None           # hyperlink URL for this paragraph's text


class ImageElement(BaseElement):
    type: Literal["image"]
    path: str
    fit: Literal["contain", "cover", "stretch"] = "contain"


class ShapeElement(BaseElement):
    type: Literal["shape"]
    shape: ShapeKind = "rect"
    text: str | None = None


class TableCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class TableElement(BaseElement):
    type: Literal["table"]
    rows: list[list[str]]
    first_row_header: bool = True
    column_widths: list[float] | None = None

    @model_validator(mode="after")
    def nonempty_rows(self) -> "TableElement":
        if not self.rows:
            raise ValueError("table must include at least one row")
        widths = {len(row) for row in self.rows}
        if len(widths) != 1:
            raise ValueError("table rows must have consistent column counts")
        if self.column_widths is not None and len(self.column_widths) != len(self.rows[0]):
            raise ValueError("column_widths length must match table column count")
        return self


class ChartSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    values: list[float]


class ChartElement(BaseElement):
    type: Literal["chart"]
    chart_type: ChartType
    categories: list[str]
    series: list[ChartSeries]
    title: str | None = None
    show_legend: bool = True
    value_format: str | None = None

    @model_validator(mode="after")
    def series_lengths_match(self) -> "ChartElement":
        category_count = len(self.categories)
        if category_count == 0:
            raise ValueError("chart must include at least one category")
        if not self.series:
            raise ValueError("chart must include at least one series")
        for series in self.series:
            if len(series.values) != category_count:
                raise ValueError(f"series {series.name} length does not match categories")
        return self


Element = TextElement | ImageElement | ShapeElement | TableElement | ChartElement


class SlideSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slide_id: str
    kind: str = "content"
    title: str | None = None
    template: str | None = None
    notes_path: str | None = None
    elements: list[Element] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_element_ids(self) -> "SlideSpec":
        seen: set[str] = set()
        for element in self.elements:
            if element.element_id in seen:
                raise ValueError(f"duplicate element_id: {element.element_id}")
            seen.add(element.element_id)
        return self


class PresentationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    presentation_id: str
    title: str | None = None
    page_size: PageSize = "widescreen"
    theme: str | None = None
    default_template: str | None = None
    slides: list[str]
    build: BuildConfig = Field(default_factory=BuildConfig)

    @model_validator(mode="after")
    def nonempty_slides(self) -> "PresentationSpec":
        if not self.slides:
            raise ValueError("presentation must include at least one slide")
        return self


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    default_output_format: Literal["text", "json"] = "text"
    default_page_size: PageSize = "widescreen"


class LoadedSlide(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    spec: SlideSpec


class LoadedPresentation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_root: Path
    presentation_path: Path
    spec: PresentationSpec
    slides: list[LoadedSlide]


class ThemeFonts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = "Plus Jakarta Sans"
    body: str = "Plus Jakarta Sans"


class TextStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    font_family: str | None = None
    font_size: int | None = None
    bold: bool | None = None
    color: str | None = None


class ThemeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    page_size: PageSize = "widescreen"
    colors: dict[str, str] = Field(default_factory=dict)
    fonts: ThemeFonts = Field(default_factory=ThemeFonts)
    styles: dict[str, TextStyle] = Field(default_factory=dict)


class TemplateSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    w: float
    h: float


class TemplateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    slots: dict[str, TemplateSlot] = Field(default_factory=dict)
