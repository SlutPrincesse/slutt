from __future__ import annotations

from nexus.browser.errors.types import BrowserError, ErrorType, RecoveryAction

_CAPTCHA_TITLE_PATTERNS = [
    "captcha", "prove you're human", "verify you are human", "i am not a robot",
]
_BLOCK_TITLE_PATTERNS = [
    "cloudflare", "access denied", "ddos-guard",
    "attention required", "blocked", "security check",
    "just a moment",
    "checking your browser", "one more step",
    "are you a robot", "human verification", "verifying you are human",
    "pardon our interruption", "request blocked",
]
_AUTH_URL_PATTERNS = ["/login", "/signin", "/sign-in", "/auth", "/account/login"]
_AUTH_TITLE_PATTERNS = ["sign in", "log in", "login", "sign up", "create account"]
_SOFT_404_TITLE_PATTERNS = [
    "page not found", "404 not found", "error 404", "404 - page not found",
]
RAW_TEXT_PROBE_FLOOR = 200
_THIN_CONTENT_CHAR_FLOOR = 100
_THIN_CONTENT_RATIO_CEILING = 0.15
_STALE_CDP_MESSAGES = [
    "cannot find context",
    "execution context was destroyed",
    "no such node",
    "invalid nodeid",
]


class ErrorClassifier:
    def classify_cdp_error(self, message: str) -> BrowserError:
        msg_lower = message.lower()
        if any(p in msg_lower for p in _STALE_CDP_MESSAGES):
            return BrowserError(
                type=ErrorType.ELEMENT_STALE,
                message=message,
                confidence=0.92,
                recovery=[RecoveryAction.RE_SNAPSHOT, RecoveryAction.RETRY],
            )
        return BrowserError(
            type=ErrorType.ELEMENT_NOT_FOUND,
            message=message,
            confidence=0.7,
            recovery=[RecoveryAction.RE_SNAPSHOT],
        )

    def classify_semantic_miss(self, description: str) -> BrowserError:
        return BrowserError(
            type=ErrorType.ELEMENT_NOT_FOUND,
            message=f"No element matched: {description!r}",
            confidence=0.85,
            recovery=[RecoveryAction.RE_SNAPSHOT, RecoveryAction.RETRY],
        )

    def classify_not_a_select(self, description: str, actual_tag: str) -> BrowserError:
        return BrowserError(
            type=ErrorType.ELEMENT_NOT_FOUND,
            message=(
                f"{description!r} resolved to a <{actual_tag or '?'}>, not a "
                "<select>. select() only works on dropdowns."
            ),
            confidence=0.85,
            recovery=[RecoveryAction.RE_SNAPSHOT, RecoveryAction.RETRY],
        )

    def classify_invalid_option(
        self, description: str, value: str, options: list[str]
    ) -> BrowserError:
        listed = ", ".join(repr(o) for o in options) if options else "no options"
        return BrowserError(
            type=ErrorType.ELEMENT_NOT_FOUND,
            message=(
                f"No option matched {value!r} in {description!r} "
                f"(available: {listed})"
            ),
            confidence=0.85,
            recovery=[RecoveryAction.RE_SNAPSHOT, RecoveryAction.RETRY],
        )

    def classify_ambiguous_target(
        self, description: str, candidates: list[tuple[str, str]]
    ) -> BrowserError:
        shown = candidates[:5]
        listed = "; ".join(
            f"{ref} ({label[:60]!r})" for ref, label in shown
        )
        if len(candidates) > len(shown):
            listed += f"; and {len(candidates) - len(shown)} more"
        return BrowserError(
            type=ErrorType.AMBIGUOUS_TARGET,
            message=(
                f"{description!r} matched {len(candidates)} elements: {listed}. "
                "Retry with one of these exact refs instead of a text description."
            ),
            confidence=0.9,
            recovery=[RecoveryAction.RE_SNAPSHOT, RecoveryAction.RETRY],
        )

    def classify_stale_ref(self, ref: str) -> BrowserError:
        return BrowserError(
            type=ErrorType.STALE_REF,
            message=(
                f"Ref {ref!r} belonged to a previous page snapshot and does not "
                "resolve on the current page. Re-snapshot and use a fresh ref."
            ),
            confidence=0.95,
            recovery=[RecoveryAction.RE_SNAPSHOT],
        )

    def classify_page_state(
        self,
        title: str,
        url: str,
        status_code: int,
        raw_chars: int | None = None,
        content_chars: int | None = None,
        content_blocks: int | None = None,
    ) -> BrowserError:
        title_lower = title.lower()
        url_lower = url.lower()

        if not title and (not url or url == "about:blank"):
            return BrowserError(
                type=ErrorType.NAVIGATION_FAILED,
                message="Page did not load — blank title and URL",
                confidence=0.9,
                recovery=[RecoveryAction.RETRY, RecoveryAction.EXPONENTIAL_BACKOFF],
            )

        if any(p in title_lower for p in _CAPTCHA_TITLE_PATTERNS):
            return BrowserError(
                type=ErrorType.CAPTCHA_REQUIRED,
                message=f"CAPTCHA challenge detected: {title!r}",
                confidence=0.93,
                recovery=[RecoveryAction.ESCALATE_TO_HUMAN, RecoveryAction.VISION_FALLBACK],
            )

        if status_code == 429:
            return BrowserError(
                type=ErrorType.RATE_LIMITED,
                message=f"Rate limited (429): {title!r}",
                confidence=0.97,
                recovery=[RecoveryAction.EXPONENTIAL_BACKOFF, RecoveryAction.RETRY],
            )

        if any(p in title_lower for p in _BLOCK_TITLE_PATTERNS) or status_code == 403:
            return BrowserError(
                type=ErrorType.ANTI_BOT_BLOCK,
                message=f"Anti-bot block detected: {title!r}",
                confidence=0.88,
                recovery=[
                    RecoveryAction.ROTATE_IDENTITY,
                    RecoveryAction.EXPONENTIAL_BACKOFF,
                ],
            )

        auth_url = any(p in url_lower for p in _AUTH_URL_PATTERNS)
        auth_title = any(p in title_lower for p in _AUTH_TITLE_PATTERNS)
        if auth_url or auth_title:
            return BrowserError(
                type=ErrorType.AUTH_REQUIRED,
                message=f"Login wall detected: {title!r}",
                confidence=0.82,
                recovery=[RecoveryAction.ESCALATE_TO_HUMAN],
            )

        if any(p in title_lower for p in _SOFT_404_TITLE_PATTERNS):
            return BrowserError(
                type=ErrorType.NO_CONTENT,
                message=f"Soft 404 detected: {title!r}",
                confidence=0.85,
                recovery=[RecoveryAction.RETRY],
            )

        if (
            raw_chars is not None and content_chars is not None
            and raw_chars >= RAW_TEXT_PROBE_FLOOR
            and 0 < content_chars < _THIN_CONTENT_CHAR_FLOOR
            and content_chars / raw_chars < _THIN_CONTENT_RATIO_CEILING
        ):
            return BrowserError(
                type=ErrorType.NO_CONTENT,
                message=(
                    f"Page loaded but almost nothing survived chrome stripping "
                    f"({content_chars} of {raw_chars} raw chars"
                    f"{f', {content_blocks} blocks' if content_blocks is not None else ''}"
                    f"): {title!r}"
                ),
                confidence=0.75,
                recovery=[RecoveryAction.RETRY],
            )

        return BrowserError(
            type=ErrorType.NAVIGATION_FAILED,
            message=f"Unexpected page state: {title!r} ({status_code})",
            confidence=0.6,
            recovery=[RecoveryAction.RETRY],
        )

    def classify_zero_results(self, context: str = "") -> BrowserError:
        return BrowserError(
            type=ErrorType.ZERO_RESULTS,
            message=(
                "Page loaded but returned no matching content"
                f"{': ' + context if context else ''}"
            ),
            confidence=0.80,
            recovery=[RecoveryAction.RETRY],
        )

    def classify_timeout(self) -> BrowserError:
        return BrowserError(
            type=ErrorType.NETWORK_TIMEOUT,
            message="Operation timed out",
            confidence=1.0,
            recovery=[RecoveryAction.EXPONENTIAL_BACKOFF, RecoveryAction.RETRY],
        )
