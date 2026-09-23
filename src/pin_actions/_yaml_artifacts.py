"""Workarounds for ``yamlrocks`` round-trip re-emit quirks."""

import re

_NEXT_SIBLING_LINE_RE = re.compile(r"^([ \t]*)(?:-([ \t]|$)|[^\s:]+:)")


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def strip_blank_line_artifacts(rendered: bytes, original: bytes) -> bytes:
    """Work around a yamlrocks round-trip quirk that injects spurious blank lines.

    Confirmed against yamlrocks 0.6.1: any mutation to a round-trip ``YAMLRocksDocument``
    -- even one unrelated to a given block scalar -- causes ``doc.to_yaml()`` to insert an
    extra whitespace-only line (matching the next sibling's indent) directly before a
    sequence item (``- ``) or mapping key (``key:``) that immediately follows a
    literal/folded (``|``/``>``) block scalar with no blank line separating them in the
    original source. Only lines matching that exact position (whitespace-only, immediately
    preceding a sequence-item or mapping-key line at indent <= the blank line's own indent,
    and absent at that position in the original) are dropped -- intentional blank lines
    inside a kept (``|+``/``>+``) block scalar's own content are never touched, since those
    are followed by further (deeper-indented) block content, not a sibling key/item, and
    genuinely pre-existing blank lines (present in ``original`` at the same position) are
    always preserved.
    """
    original_lines = original.decode().split("\n")
    lines = rendered.decode().split("\n")
    cleaned: list[str] = []
    for i, line in enumerate(lines):
        is_artifact = (
            line.strip() == ""
            and line != ""
            and i + 1 < len(lines)
            and _NEXT_SIBLING_LINE_RE.match(lines[i + 1]) is not None
            and _indent_of(lines[i + 1]) <= _indent_of(line)
            and line not in original_lines
        )
        if not is_artifact:
            cleaned.append(line)
    return "\n".join(cleaned).encode()
