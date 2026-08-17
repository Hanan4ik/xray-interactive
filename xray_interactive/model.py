from __future__ import annotations

import json
import os
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

Json = dict[str, Any] | list[Any] | str | int | float | bool | None
PathPart = str | int
JsonPath = tuple[PathPart, ...]


TOP_LEVEL_TEMPLATE: dict[str, Any] = {
    "env": {},
    "log": {},
    "api": {},
    "dns": {},
    "routing": {},
    "policy": {},
    "inbounds": [],
    "outbounds": [],
    "stats": {},
    "fakedns": {},
    "metrics": {},
    "observatory": {},
    "burstObservatory": {},
    "geodata": {},
    "version": {},
}


def new_config() -> dict[str, Any]:
    """Return a new config containing every documented top-level entity."""
    return deepcopy(TOP_LEVEL_TEMPLATE)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Xray config root must be a JSON object")
    return data


def save_config(path: Path, data: dict[str, Any], backup: bool = True) -> None:
    """
    Atomically write JSON. If a config already exists, keep one previous saved
    version next to it as <name>.bak.
    """
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    if backup and path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))

    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def get_at(root: Json, path: JsonPath) -> Json:
    cur: Any = root
    for part in path:
        cur = cur[part]
    return cur


def parent_of(root: Json, path: JsonPath) -> tuple[Json, PathPart]:
    if not path:
        raise ValueError("root has no parent")
    return get_at(root, path[:-1]), path[-1]


def set_at(root: Json, path: JsonPath, value: Json) -> None:
    if not path:
        if not isinstance(root, dict) or not isinstance(value, dict):
            raise ValueError("root replacement must be a JSON object")
        root.clear()
        root.update(value)
        return
    parent, key = parent_of(root, path)
    parent[key] = value  # type: ignore[index]


def delete_at(root: Json, path: JsonPath) -> None:
    if not path:
        raise ValueError("cannot delete config root")
    parent, key = parent_of(root, path)
    if isinstance(parent, list):
        del parent[int(key)]
    else:
        del parent[str(key)]


def parse_jsonish(text: str) -> Json:
    """
    JSON-first input: true/false/null/numbers/arrays/objects/quoted strings are
    parsed as JSON; unquoted text is treated as a string.
    """
    s = text.strip()
    if not s:
        return ""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return text


def unique_tag(config: dict[str, Any], base: str) -> str:
    tags: set[str] = set()
    for key in ("inbounds", "outbounds"):
        for item in config.get(key, []) or []:
            if isinstance(item, dict) and isinstance(item.get("tag"), str):
                tags.add(item["tag"])
    if base not in tags:
        return base
    i = 2
    while f"{base}-{i}" in tags:
        i += 1
    return f"{base}-{i}"


def path_to_str(path: JsonPath) -> str:
    if not path:
        return "$"
    out = "$"
    for p in path:
        if isinstance(p, int):
            out += f"[{p}]"
        else:
            out += "." + p
    return out
