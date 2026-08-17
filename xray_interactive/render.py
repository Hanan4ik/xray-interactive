from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from typing import Any

from .model import JsonPath


@dataclass
class RenderLine:
    text: str
    container_path: JsonPath
    value_path: JsonPath | None = None


def _scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def layout_action_lines(
    labels: list[str], selected_index: int, width: int, max_lines: int
) -> list[str]:
    """Lay out the action picker without losing the currently selected item."""
    width = max(1, width)
    max_lines = max(1, max_lines)
    rows: list[str] = []
    owners: list[set[int]] = []
    current = ""
    current_owners: set[int] = set()

    def flush() -> None:
        nonlocal current, current_owners
        if current:
            rows.append(current)
            owners.append(current_owners)
            current = ""
            current_owners = set()

    for i, label in enumerate(labels):
        marker = "▶" if i == selected_index else " "
        chunk = f"{marker} {label}"
        wrapped = textwrap.wrap(
            chunk,
            width=width,
            subsequent_indent="  ",
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]

        if len(wrapped) > 1:
            flush()
            for part in wrapped:
                rows.append(part)
                owners.append({i})
            continue

        candidate = f"{current}   {wrapped[0]}" if current else wrapped[0]
        if current and len(candidate) > width:
            flush()
            current = wrapped[0]
            current_owners = {i}
        else:
            current = candidate
            current_owners.add(i)
    flush()

    if len(rows) <= max_lines:
        return rows

    selected_rows = [i for i, row_owners in enumerate(owners) if selected_index in row_owners]
    target = selected_rows[0] if selected_rows else 0
    start = max(0, min(target - max_lines // 2, len(rows) - max_lines))
    return rows[start:start + max_lines]


def render_json(data: Any) -> list[RenderLine]:
    lines: list[RenderLine] = []

    def rec(value: Any, path: JsonPath, indent: int, key: str | None, is_last: bool) -> None:
        pad = " " * indent
        prefix = f"{json.dumps(key, ensure_ascii=False)}: " if key is not None else ""
        comma = "" if is_last else ","

        if isinstance(value, dict):
            lines.append(RenderLine(f"{pad}{prefix}{{", path, path))
            items = list(value.items())
            for idx, (k, v) in enumerate(items):
                rec(v, path + (k,), indent + 2, k, idx == len(items) - 1)
            lines.append(RenderLine(f"{pad}}}{comma}", path, path))
            return

        if isinstance(value, list):
            lines.append(RenderLine(f"{pad}{prefix}[", path, path))
            for idx, v in enumerate(value):
                rec(v, path + (idx,), indent + 2, None, idx == len(value) - 1)
            lines.append(RenderLine(f"{pad}]{comma}", path, path))
            return

        lines.append(RenderLine(f"{pad}{prefix}{_scalar(value)}{comma}", path[:-1], path))

    rec(data, (), 0, None, True)
    return lines
