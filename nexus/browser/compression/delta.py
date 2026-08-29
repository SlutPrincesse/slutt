from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.browser.compression.summarizer import Element, PageSnapshot


@dataclass
class SnapshotDelta:
    version: int
    previous_version: int
    added: list[Element] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[tuple[str, str, str]] = field(default_factory=list)
    content_ops: list[str] = field(default_factory=list)
    url_changed: bool = False

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed or self.content_ops)


def _content_ops(old: str, new: str) -> list[str]:
    if old == new:
        return []
    old_words = old.split()
    new_words = new.split()
    matcher = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    ops: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("replace", "insert"):
            ops.append(f"+{j1}: {' '.join(new_words[j1:j2])}")
        if tag in ("replace", "delete"):
            ops.append(f"-{i1}:{i2 - i1}")
    return ops


_MIN_SHARED_HANDLES = 4
_MIN_HANDLE_AGREEMENT = 0.5


def _is_restamped_document(previous: PageSnapshot, current: PageSnapshot) -> bool:
    before = {el.handle: el for el in previous.elements if el.handle}
    after = {el.handle: el for el in current.elements if el.handle}
    shared = before.keys() & after.keys()
    if len(shared) < _MIN_SHARED_HANDLES:
        return False
    agreed = sum(
        1 for h in shared
        if (before[h].tag, before[h].role, before[h].text, before[h].placeholder)
        == (after[h].tag, after[h].role, after[h].text, after[h].placeholder)
    )
    return agreed / len(shared) < _MIN_HANDLE_AGREEMENT


def build_delta(
    previous: PageSnapshot | None, current: PageSnapshot
) -> SnapshotDelta | None:
    if previous is None:
        return None
    if previous.url != current.url:
        return None
    if _is_restamped_document(previous, current):
        return None

    before = {el.ref: el for el in previous.elements}
    after = {el.ref: el for el in current.elements}

    delta = SnapshotDelta(
        version=current.version, previous_version=previous.version
    )
    delta.added = [el for ref, el in after.items() if ref not in before]
    delta.removed = [ref for ref in before if ref not in after]
    delta.changed = [
        (ref, before[ref].text, after[ref].text)
        for ref in after
        if ref in before and before[ref].text != after[ref].text
    ]
    delta.content_ops = _content_ops(previous.text_content, current.text_content)
    return delta


_TAG_ABBREV = {"button": "btn", "input": "inp", "a": "lnk", "select": "sel",
               "textarea": "inp"}


def format_delta(delta: SnapshotDelta) -> str:
    if delta.is_empty:
        return f"DELTA v{delta.previous_version}->v{delta.version}: no change"
    lines = [f"DELTA v{delta.previous_version}->v{delta.version}"]
    for el in delta.added:
        abbrev = _TAG_ABBREV.get(el.tag, el.tag[:3])
        desc = el.text or el.placeholder or el.role
        lines.append(f"  + [{abbrev}:{el.ref}] {desc!r}")
    for ref in delta.removed:
        lines.append(f"  - [{ref}]")
    for ref, old, new in delta.changed:
        lines.append(f"  ~ [{ref}] {old!r} -> {new!r}")
    if delta.content_ops:
        lines.append("  CONTENT:")
        for op in delta.content_ops:
            lines.append(f"    {op}")
    return "\n".join(lines)


_WORTHWHILE_RATIO = 0.9


def is_worth_sending(rendered_delta: str, rendered_snapshot: str) -> bool:
    return len(rendered_delta) <= _WORTHWHILE_RATIO * len(rendered_snapshot)
