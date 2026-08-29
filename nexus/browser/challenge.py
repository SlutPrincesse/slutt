"""Challenge detection and in-process solving."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ChallengeStage(Enum):
    NONE = "none"
    CHECKBOX = "checkbox"
    TURNSTILE = "turnstile"
    SLIDER = "slider"
    IMAGE_GRID = "image_grid"
    TEXT = "text"
    INVISIBLE = "invisible"
    UNKNOWN = "unknown"


@dataclass
class ChallengeResult:
    status: str
    stage: ChallengeStage
    detail: str = ""
    screenshot: object | None = None


_SOLVABLE = {ChallengeStage.CHECKBOX, ChallengeStage.TURNSTILE, ChallengeStage.SLIDER}
_NEEDS_VISION = {ChallengeStage.IMAGE_GRID, ChallengeStage.TEXT}


def is_solvable(stage: ChallengeStage) -> bool:
    return stage in _SOLVABLE


def needs_vision(stage: ChallengeStage) -> bool:
    return stage in _NEEDS_VISION


_RECAPTCHA_ANCHOR = "recaptcha/api2/anchor"
_RECAPTCHA_ENTERPRISE_ANCHOR = "recaptcha/enterprise/anchor"
_RECAPTCHA_BFRAME = "recaptcha/api2/bframe"
_RECAPTCHA_ENTERPRISE_BFRAME = "recaptcha/enterprise/bframe"
_TURNSTILE_HOST = "challenges.cloudflare.com"
_HCAPTCHA_HOST = "hcaptcha.com"

_WIDGET_MARKERS = {
    "g-recaptcha": ChallengeStage.CHECKBOX,
    "h-captcha": ChallengeStage.CHECKBOX,
    "cf-turnstile": ChallengeStage.TURNSTILE,
}
_SLIDER_MARKERS = (
    "geetest_slider",
    "nc_scale",
    "slider-verify",
    "captcha-slider",
    "verify-slider",
)
_TEXT_IMG = re.compile(r"<img[^>]+(?:src|id|class|alt)=[\"'][^\"']*captcha", re.IGNORECASE)
_TEXT_INPUT = re.compile(r"<input[^>]+(?:name|id)=[\"'][^\"']*captcha", re.IGNORECASE)
_PROSE_CHALLENGE = re.compile(
    r"(?:complete|solve|verify|confirm)[^.<>]{0,40}captcha"
    r"(?:[^.<>]{0,20}(?:to\s+continue|before\s+continuing|required))"
    r"|(?:complete|solve|verify|confirm)[^.<>]{0,40}"
    r"(?:you\s+are\s+human|not\s+a\s+robot)"
    r"|(?:captcha|security\s+check)[^.<>]{0,40}(?:to\s+continue|required)"
    r"|checking\s+your\s+browser",
    re.IGNORECASE,
)


def _has_widget_element(html: str, marker: str) -> bool:
    pattern = re.compile(
        r"<[a-zA-Z][\w-]*\b[^>]*\bclass\s*=\s*[\"'][^\"']*\b" + re.escape(marker) + r"\b",
        re.IGNORECASE,
    )
    return bool(pattern.search(html))


def detect_challenge_from_html(html: str, frames: list[str]) -> ChallengeStage:
    html = html or ""
    frames = frames or []
    joined = " ".join(frames)
    lowered = html.lower()

    if _RECAPTCHA_BFRAME in joined or _RECAPTCHA_ENTERPRISE_BFRAME in joined:
        return ChallengeStage.IMAGE_GRID

    if _TURNSTILE_HOST in joined or _has_widget_element(html, "cf-turnstile"):
        return ChallengeStage.TURNSTILE

    for marker in _SLIDER_MARKERS:
        if marker in lowered:
            return ChallengeStage.SLIDER

    has_anchor = (
        _RECAPTCHA_ANCHOR in joined
        or _RECAPTCHA_ENTERPRISE_ANCHOR in joined
        or _HCAPTCHA_HOST in joined
    )
    widget = next(
        (s for m, s in _WIDGET_MARKERS.items() if _has_widget_element(html, m)), None
    )

    if has_anchor:
        return ChallengeStage.CHECKBOX
    if widget is not None:
        return ChallengeStage.INVISIBLE

    if _TEXT_IMG.search(html) and _TEXT_INPUT.search(html):
        return ChallengeStage.TEXT

    if _PROSE_CHALLENGE.search(html):
        return ChallengeStage.UNKNOWN

    return ChallengeStage.NONE


def frame_urls(frame_tree: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        frame = node.get("frame") or {}
        url = frame.get("url")
        if url:
            urls.append(url)
        for child in node.get("childFrames") or []:
            walk(child)

    walk(frame_tree.get("frameTree") or {})
    return urls


TOKEN_PROBE_JS = (
    """
(function gripChallengeToken() {
  var names = ['g-recaptcha-response', 'cf-turnstile-response', 'h-captcha-response'];
  for (var i = 0; i < names.length; i++) {
    var el = document.querySelector('[name="' + names[i] + '"]');
    if (el && el.value) return el.value;
  }
  return '';
})()
"""
)

POINT_PROBE_JS = """
(function gripChallengePoint() {
  var sel = 'iframe[src*="recaptcha/api2/anchor"],'
          + 'iframe[src*="recaptcha/enterprise/anchor"],'
          + 'iframe[src*="hcaptcha.com"],'
          + 'iframe[src*="challenges.cloudflare.com"]';
  var f = document.querySelector(sel);
  if (f) {
    var r = f.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return null;
    return {x: Math.round(r.left + 30), y: Math.round(r.top + r.height / 2)};
  }
  return null;
})()
"""

SLIDER_PROBE_JS = """
(function gripChallengeSlider() {
  var handle = document.querySelector(
    '.geetest_slider_button, .nc_iconfont.btn_slide, [class*="slider-btn"],'
    + '[class*="slider_button"], [class*="handler"]');
  if (!handle) return {reason: 'no_handle'};
  var h = handle.getBoundingClientRect();
  if (h.width === 0) return {reason: 'handle_zero_size'};

  var trackSel = '.geetest_slider, .nc_scale, [class*="slider-track"], [class*="slider"]';
  var track = null;
  for (var el = handle.parentElement; el; el = el.parentElement) {
    if (el.matches && el.matches(trackSel)) { track = el; break; }
  }
  if (!track) return {reason: 'no_track_ancestor'};

  var t = track.getBoundingClientRect();
  if (t.width < h.width * 1.5) return {reason: 'track_not_wider_than_handle'};

  return {
    x: Math.round(h.left + h.width / 2),
    y: Math.round(h.top + h.height / 2),
    endX: Math.round(t.right - h.width / 2),
  };
})()
"""
