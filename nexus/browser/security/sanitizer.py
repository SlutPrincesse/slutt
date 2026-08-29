from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RawElement:
    tag: str
    role: str
    text: str
    placeholder: str | None
    in_shadow_dom: bool
    cx: int
    cy: int
    computed_display: str
    computed_visibility: str
    computed_opacity: str
    aria_hidden: bool
    width: int
    height: int
    href: str | None = None
    handle: str = ""
    disabled: bool = False
    required: bool = False
    checked: bool | None = None
    selected: bool | None = None
    value: str | None = None
    canvas_width: int | None = None
    canvas_height: int | None = None
    is_combobox: bool = False
    combobox_expanded: bool | None = None
    combobox_options: list[str] | None = None
    closed_shadow_unreadable: bool = False
