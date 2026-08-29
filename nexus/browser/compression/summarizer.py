from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from nexus.browser.security.sanitizer import RawElement

if TYPE_CHECKING:
    from nexus.browser.errors.types import BrowserError

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:
        return len(_ENC.encode(text))
except Exception:
    def _count_tokens(text: str) -> int:
        return len(text) // 4


_TAG_ABBREV = {
    "button": "btn",
    "input": "inp",
    "a": "lnk",
    "select": "sel",
    "textarea": "inp",
}


@dataclass
class Element:
    index: int
    tag: str
    role: str
    text: str
    placeholder: str | None
    in_shadow_dom: bool
    cx: int
    cy: int
    ref: str = ""
    handle: str = ""
    href: str | None = None
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


@dataclass
class PageSnapshot:
    version: int
    url: str
    title: str
    elements: list[Element]
    text_content: str
    tokens_estimated: int
    changed_from_previous: bool = True
    page_error: BrowserError | None = None
    prompt_injection: bool = False
    scroll_top: int = 0
    scroll_left: int = 0
    scroll_height: int = 0
    client_height: int = 0

    @property
    def links(self) -> list[tuple[str, str]]:
        return [(el.text, el.href) for el in self.elements if el.href]


class Summarizer:
    def build(
        self,
        version: int,
        url: str,
        title: str,
        raw_elements: list[RawElement],
        page_text: str,
    ) -> PageSnapshot:
        elements = [
            Element(
                index=i,
                tag=el.tag,
                role=el.role,
                text=el.text,
                placeholder=el.placeholder,
                in_shadow_dom=el.in_shadow_dom,
                cx=el.cx,
                cy=el.cy,
                handle=el.handle,
                href=el.href,
                disabled=getattr(el, "disabled", False),
                required=getattr(el, "required", False),
                checked=getattr(el, "checked", None),
                selected=getattr(el, "selected", None),
                value=getattr(el, "value", None),
                canvas_width=getattr(el, "canvas_width", None),
                canvas_height=getattr(el, "canvas_height", None),
                is_combobox=getattr(el, "is_combobox", False),
                combobox_expanded=getattr(el, "combobox_expanded", None),
                combobox_options=getattr(el, "combobox_options", None),
                closed_shadow_unreadable=getattr(el, "closed_shadow_unreadable", False),
            )
            for i, el in enumerate(raw_elements)
        ]
        text_content = page_text.strip()
        return PageSnapshot(
            version=version,
            url=url,
            title=title,
            elements=elements,
            text_content=text_content,
            tokens_estimated=0,
        )

    def format(self, snapshot: PageSnapshot) -> str:
        leading: list[str] = []
        if snapshot.page_error is not None:
            leading.append(self._format_status_line(snapshot.page_error))
        if snapshot.prompt_injection:
            leading.append(
                "WARNING: this page attempted a prompt injection; the "
                "offending text was elided before this snapshot was built."
            )
        body = self._build_format_str(
            snapshot.url,
            snapshot.title,
            snapshot.elements,
            snapshot.text_content,
            snapshot.scroll_top,
            snapshot.scroll_left,
            snapshot.scroll_height,
        )
        return "\n".join([*leading, body]) if leading else body

    def count_tokens(self, text: str) -> int:
        return _count_tokens(text)

    @staticmethod
    def _format_status_line(error: BrowserError) -> str:
        recovery = ", ".join(action.value for action in error.recovery)
        suffix = f" (recovery: {recovery})" if recovery else ""
        return f"STATUS: {error.type.value}{suffix}"

    @staticmethod
    def _format_viewport_line(scroll_top: int, scroll_left: int, scroll_height: int) -> str:
        if scroll_height <= 0:
            return ""
        line = f"VIEWPORT: y={scroll_top}/{scroll_height}"
        if scroll_left:
            line += f" x={scroll_left}"
        return line

    @staticmethod
    def _element_state_suffix(el: Element) -> str:
        suffix = f' ="{el.value}"' if el.value else ""
        flags = [
            name
            for name, active in (
                ("disabled", el.disabled),
                ("required", el.required),
                ("checked", el.checked),
                ("selected", el.selected),
                ("combobox" + (", expanded" if el.combobox_expanded else ""), el.is_combobox),
                ("hidden content, unreadable", el.closed_shadow_unreadable),
            )
            if active
        ]
        if flags:
            suffix += " (" + ", ".join(flags) + ")"
        if el.tag == "canvas" and el.canvas_width is not None and el.canvas_height is not None:
            suffix += f" [{el.canvas_width}x{el.canvas_height}]"
        if el.is_combobox and el.combobox_options:
            preview = ", ".join(el.combobox_options[:5])
            more = len(el.combobox_options) - 5
            if more > 0:
                preview += f", +{more} more"
            suffix += f" options=[{preview}]"
        return suffix

    def _build_format_str(
        self,
        url: str,
        title: str,
        elements: list[Element],
        text: str,
        scroll_top: int,
        scroll_left: int,
        scroll_height: int,
    ) -> str:
        lines = [f"PAGE: {title}", f"URL: {url}"]
        viewport = self._format_viewport_line(scroll_top, scroll_left, scroll_height)
        if viewport:
            lines.append(viewport)
        if elements:
            lines.append("INTERACTIVE:")
            for el in elements:
                abbrev = _TAG_ABBREV.get(el.tag, el.tag[:3])
                desc = el.text or el.placeholder or el.role
                ref = el.ref or str(el.index)
                lines.append(
                    f"  [{abbrev}:{ref}] {desc!r}{self._element_state_suffix(el)}"
                )
        if text:
            lines.append("CONTENT:")
            lines.append(f"  {text[:2000]}")
            if len(text) > 2000:
                lines.append(
                    f"  ... [{len(text) - 2000} more characters truncated — call "
                    "read() for the full content]"
                )
        return "\n".join(lines)
