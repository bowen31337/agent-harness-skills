"""
dom_snapshot_utility
====================
Browser-free DOM inspection for agents.

Public API
----------
    from dom_snapshot_utility import snapshot_from_html, snapshot_from_url, snapshot_to_text, DOMSnapshot
"""

from .snapshot import (
    AriaRegion,
    Button,
    DOMSnapshot,
    Form,
    Heading,
    ImageSnapshot,
    InputField,
    Link,
    PageMeta,
    TableSnapshot,
    snapshot_from_html,
    snapshot_from_url,
    snapshot_to_text,
)

__all__ = [
    "DOMSnapshot",
    "PageMeta",
    "Heading",
    "Link",
    "Button",
    "InputField",
    "Form",
    "AriaRegion",
    "TableSnapshot",
    "ImageSnapshot",
    "snapshot_from_html",
    "snapshot_from_url",
    "snapshot_to_text",
]
