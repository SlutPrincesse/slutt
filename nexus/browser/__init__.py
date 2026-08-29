"""Nexus Browser — CDP-native browser automation for AI agents."""

from nexus.browser.browser import Browser
from nexus.browser.compression.delta import SnapshotDelta
from nexus.browser.compression.summarizer import Element, PageSnapshot
from nexus.browser.errors.types import BrowserError, ErrorType, BrowserException, RecoveryAction
from nexus.browser.page import Page, Screenshot
from nexus.browser.reader import Block, Document
from nexus.browser.security.policy import NavigationPolicy
from nexus.browser.trace import Trace, TraceEntry

from nexus.browser.runner import RunResult

__all__ = [
    "Block",
    "Browser",
    "BrowserError",
    "BrowserException",
    "Document",
    "Element",
    "ErrorType",
    "NavigationPolicy",
    "Page",
    "PageSnapshot",
    "RecoveryAction",
    "RunResult",
    "Screenshot",
    "SnapshotDelta",
    "Trace",
    "TraceEntry",
]

__version__ = "0.8.2"
