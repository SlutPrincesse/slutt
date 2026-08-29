"""Human-shaped pointer geometry."""

from __future__ import annotations

import math
import random

from nexus.browser.cdp.shadow import _RESOLVE_JS

Point = tuple[int, int]

RESOLVE_POINT_JS = """
function(handle, expectedTag, expectedText) {
""" + _RESOLVE_JS + """
  const r = gripResolve(handle, expectedTag, expectedText);
  if (!r.el) return { ok: false, reason: r.reason };
  r.el.scrollIntoView({ block: 'center', inline: 'center' });
  const b = r.el.getBoundingClientRect();
  if (b.width === 0 || b.height === 0) return { ok: false, reason: 'not_visible' };
  return {
    ok: true, reason: '',
    x: Math.round(b.left + b.width / 2),
    y: Math.round(b.top + b.height / 2),
  };
}
"""

_MIN_OFFSET_PX = 2.0
_MAX_OFFSET_FRACTION = 0.18


def _ease_in_out(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * t)


def bezier_path(
    start: Point,
    end: Point,
    steps: int = 24,
    *,
    rng: random.Random | None = None,
) -> list[Point]:
    r = rng or random.Random()
    steps = max(2, steps)

    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)

    if length == 0:
        return [(int(x0), int(y0))] * steps

    px, py = -dy / length, dx / length
    magnitude = max(_MIN_OFFSET_PX, length * _MAX_OFFSET_FRACTION * r.uniform(0.35, 1.0))
    magnitude *= r.choice((-1.0, 1.0))

    cx = x0 + dx / 2 + px * magnitude
    cy = y0 + dy / 2 + py * magnitude

    path: list[Point] = []
    for i in range(steps):
        t = _ease_in_out(i / (steps - 1))
        inv = 1 - t
        bx = inv * inv * x0 + 2 * inv * t * cx + t * t * x1
        by = inv * inv * y0 + 2 * inv * t * cy + t * t * y1
        path.append((round(bx), round(by)))

    path[0] = (int(x0), int(y0))
    path[-1] = (int(x1), int(y1))
    return path


def press_dwell(rng: random.Random | None = None) -> float:
    r = rng or random.Random()
    return round(r.uniform(0.04, 0.16), 4)


def move_delay(rng: random.Random | None = None) -> float:
    r = rng or random.Random()
    return round(r.uniform(0.006, 0.022), 4)
