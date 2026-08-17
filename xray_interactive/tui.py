from __future__ import annotations

import curses
import json
import os
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from .model import (
    JsonPath,
    delete_at,
    get_at,
    parse_jsonish,
    path_to_str,
    save_config,
    set_at,
)
from .render import RenderLine, layout_action_lines, render_json
from .schema import Action, actions_for, template_for
from .xray import generate_uuid, validate_config

KEY_CTRL_LEFT = 0x2201
KEY_CTRL_RIGHT = 0x2202
KEY_CTRL_UP = 0x2203
KEY_CTRL_DOWN = 0x2204


class Editor:
    def __init__(self, config: dict[str, Any], config_path: Path, xray_binary: Path):
        self.config = config
        self.config_path = config_path
        self.xray_binary = xray_binary
        self.cursor = 0
        self.scroll = 0
        self.action_index = 0
        self.status = "Ready"
        self.dirty = False
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []
        self.preferred_path: JsonPath | None = None

    def snapshot(self) -> None:
        self.undo_stack.append(deepcopy(self.config))
        if len(self.undo_stack) > 100:
            del self.undo_stack[0]
        self.redo_stack.clear()

    def mutate(self, fn) -> None:
        self.snapshot()
        fn()
        self.dirty = True

    def current(self, lines: list[RenderLine]) -> RenderLine:
        self.cursor = max(0, min(self.cursor, len(lines) - 1))
        return lines[self.cursor]

    def selected_path(self, lines: list[RenderLine]) -> JsonPath:
        return self.current(lines).container_path

    def move_to_path(self, lines: list[RenderLine], path: JsonPath) -> None:
        for i, line in enumerate(lines):
            if line.container_path == path or line.value_path == path:
                self.cursor = i
                return

    def prompt(self, stdscr, label: str, default: str = "") -> str | None:
        h, w = stdscr.getmaxyx()
        prompt = f"{label}"
        if default != "":
            prompt += f" [{default}]"
        prompt += ": "
        curses.echo()
        curses.curs_set(1)
        try:
            stdscr.move(h - 1, 0)
            stdscr.clrtoeol()
            stdscr.addnstr(h - 1, 0, prompt, max(1, w - 1), curses.A_BOLD)
            stdscr.refresh()
            raw = stdscr.getstr(h - 1, min(len(prompt), w - 2), max(1, w - len(prompt) - 2))
            text = raw.decode("utf-8", errors="replace")
            if not text and default != "":
                return default
            return text
        except (KeyboardInterrupt, curses.error):
            return None
        finally:
            curses.noecho()
            curses.curs_set(0)

    def confirm(self, stdscr, text: str) -> bool:
        answer = self.prompt(stdscr, text + " (y/N)")
        return bool(answer and answer.lower() in {"y", "yes", "д", "да"})

    def edit_value(self, stdscr, path: JsonPath) -> None:
        try:
            old = get_at(self.config, path)
        except Exception as e:
            self.status = f"Cannot edit: {e}"
            return
        if isinstance(old, (dict, list)):
            self.status = "Container selected; use E for raw block editor"
            return
        default = json.dumps(old, ensure_ascii=False) if not isinstance(old, str) else old
        text = self.prompt(stdscr, f"New value for {path_to_str(path)}", default)
        if text is None:
            return
        value = parse_jsonish(text)
        self.mutate(lambda: set_at(self.config, path, value))
        self.status = f"Changed {path_to_str(path)}"

    def raw_edit(self, stdscr, path: JsonPath) -> None:
        editor = os.environ.get("EDITOR")
        if not editor:
            for candidate in ("nano", "vim", "vi"):
                if shutil.which(candidate):
                    editor = candidate
                    break
        if not editor:
            self.status = "Set $EDITOR or install nano/vim/vi for raw block editing"
            return

        value = get_at(self.config, path)
        fd, name = tempfile.mkstemp(prefix="xray-interactive-", suffix=".json")
        os.close(fd)
        tmp = Path(name)
        try:
            tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            curses.endwin()
            rc = subprocess.call([editor, str(tmp)])
            stdscr.refresh()
            if rc != 0:
                self.status = f"$EDITOR exited with {rc}"
                return
            try:
                replacement = json.loads(tmp.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                self.status = f"Raw edit rejected: invalid JSON at line {e.lineno}, col {e.colno}"
                return
            if path == () and not isinstance(replacement, dict):
                self.status = "Root must stay a JSON object"
                return
            self.mutate(lambda: set_at(self.config, path, replacement))
            self.status = f"Replaced {path_to_str(path)} from $EDITOR"
        finally:
            tmp.unlink(missing_ok=True)

    def apply_action(self, stdscr, path: JsonPath, action: Action) -> JsonPath | None:
        node = get_at(self.config, path)

        if action.op == "jump":
            return tuple(action.default)

        if action.op == "append_template":
            if not isinstance(node, list):
                self.status = "Selected block is not an array"
                return None
            item = template_for(self.config, action.default)
            self.mutate(lambda: node.append(item))
            new_path = path + (len(node) - 1,)
            self.status = f"Added {action.default}"
            return new_path

        if action.op == "set_field":
            if not isinstance(node, dict) or action.key is None:
                return None
            default_text = json.dumps(action.default, ensure_ascii=False)
            if isinstance(action.default, str):
                default_text = action.default
            text = self.prompt(stdscr, action.key, default_text)
            if text is None:
                return None
            value = parse_jsonish(text)
            self.mutate(lambda: node.__setitem__(action.key, value))
            self.status = f"Added {action.key}"
            return path + (action.key,)

        if action.op == "use_xhttp":
            if not isinstance(node, dict):
                return None
            def do():
                node["method"] = "xhttp"
                node.setdefault("xhttpSettings", {"path": "/"})
            self.mutate(do)
            self.status = "XHTTP enabled"
            return path + ("xhttpSettings",)

        if action.op == "enable_reality":
            if not isinstance(node, dict):
                return None
            is_inbound = len(path) >= 2 and path[0] == "inbounds"
            defaults = (
                {
                    "show": False,
                    "target": "example.com:443",
                    "xver": 0,
                    "serverNames": ["example.com"],
                    "privateKey": "",
                    "shortIds": [""],
                }
                if is_inbound
                else {
                    "serverName": "",
                    "fingerprint": "chrome",
                    "password": "",
                    "shortId": "",
                    "spiderX": "",
                }
            )
            def do():
                node["security"] = "reality"
                node.setdefault("realitySettings", defaults)
            self.mutate(do)
            self.status = "REALITY enabled"
            return path + ("realitySettings",)

        if action.op == "generate_uuid":
            result = generate_uuid(self.xray_binary)
            if not result.ok:
                self.status = "xray uuid failed: " + result.output[:140]
                return None
            uuid_value = result.output.strip().splitlines()[-1].strip()
            target: JsonPath | None = None
            if isinstance(node, dict):
                if "id" in node:
                    target = path + ("id",)
                elif node.get("protocol") == "vless":
                    settings = node.setdefault("settings", {})
                    if isinstance(settings, dict):
                        if path[0] == "outbounds":
                            target = path + ("settings", "id")
                        else:
                            users = settings.setdefault("users", [])
                            if isinstance(users, list):
                                users.append({"id": uuid_value, "level": 0, "email": "", "flow": ""})
                                self.dirty = True
                                self.undo_stack.append(deepcopy(self.config))
                                self.status = "Generated UUID and added VLESS user"
                                return path + ("settings", "users", len(users)-1)
            if target is not None:
                self.mutate(lambda: set_at(self.config, target, uuid_value))
                self.status = "Generated UUID"
                return target
            self.status = "No VLESS id target in selected block"
            return None

        if action.op == "append_json":
            if not isinstance(node, list):
                return None
            text = self.prompt(stdscr, "JSON item", "{}")
            if text is None:
                return None
            try:
                value = json.loads(text)
            except json.JSONDecodeError as e:
                self.status = f"Invalid JSON: {e.msg}"
                return None
            self.mutate(lambda: node.append(value))
            self.status = "Added JSON item"
            return path + (len(node)-1,)

        if action.op == "custom_key":
            if not isinstance(node, dict):
                return None
            key = self.prompt(stdscr, "Key")
            if not key:
                return None
            text = self.prompt(stdscr, "JSON value", "null")
            if text is None:
                return None
            value = parse_jsonish(text)
            self.mutate(lambda: node.__setitem__(key, value))
            self.status = f"Added custom key {key}"
            return path + (key,)

        return None

    def save(self) -> None:
        save_config(self.config_path, self.config, backup=True)
        self.dirty = False
        self.status = f"Saved {self.config_path.name} (backup: {self.config_path.name}.bak)"

    def validate(self) -> None:
        # Validate exactly what the user sees, but don't silently mark the editor clean.
        save_config(self.config_path, self.config, backup=True)
        self.dirty = False
        result = validate_config(self.xray_binary, self.config_path)
        one_line = " | ".join(line.strip() for line in result.output.splitlines() if line.strip())
        if result.ok:
            self.status = "Xray validation OK" + (f": {one_line[:120]}" if one_line else "")
        else:
            self.status = f"Xray validation FAILED ({result.returncode}): {one_line[:180]}"

    def undo(self) -> None:
        if not self.undo_stack:
            self.status = "Nothing to undo"
            return
        self.redo_stack.append(deepcopy(self.config))
        self.config = self.undo_stack.pop()
        self.dirty = True
        self.status = "Undo"

    def redo(self) -> None:
        if not self.redo_stack:
            self.status = "Nothing to redo"
            return
        self.undo_stack.append(deepcopy(self.config))
        self.config = self.redo_stack.pop()
        self.dirty = True
        self.status = "Redo"

    def draw(self, stdscr) -> tuple[list[RenderLine], list[Action]]:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        if h < 8 or w < 40:
            stdscr.addnstr(0, 0, "Terminal too small (need at least 40x8)", max(1, w - 1))
            stdscr.refresh()
            return render_json(self.config), []

        lines = render_json(self.config)
        if self.preferred_path is not None:
            self.move_to_path(lines, self.preferred_path)
            self.preferred_path = None

        self.cursor = max(0, min(self.cursor, len(lines) - 1))
        selected = self.selected_path(lines)
        actions = actions_for(self.config, selected)
        if actions:
            self.action_index %= len(actions)
        else:
            self.action_index = 0

        header = (
            f"xray-interactive  {self.config_path.name}"
            f"{'  * unsaved' if self.dirty else ''}  block: {path_to_str(selected)}"
        )
        stdscr.addnstr(0, 0, header, w - 1, curses.A_BOLD)

        if actions:
            action_lines = layout_action_lines(
                [action.label for action in actions], self.action_index, w - 1, h - 4
            )
        else:
            action_lines = ["(no guided actions for this block)"]

        status_y = h - len(action_lines) - 2
        body_top = 1
        body_height = max(1, status_y - body_top)

        if self.cursor < self.scroll:
            self.scroll = self.cursor
        if self.cursor >= self.scroll + body_height:
            self.scroll = self.cursor - body_height + 1
        self.scroll = max(0, min(self.scroll, max(0, len(lines) - body_height)))

        for screen_y, idx in enumerate(range(self.scroll, min(len(lines), self.scroll + body_height)), start=body_top):
            line = lines[idx]
            attr = curses.A_NORMAL
            if line.container_path == selected:
                attr |= curses.color_pair(1)
            if idx == self.cursor:
                attr |= curses.A_REVERSE | curses.A_BOLD
            try:
                stdscr.addnstr(screen_y, 0, line.text, w - 1, attr)
            except curses.error:
                pass

        status = self.status
        stdscr.addnstr(status_y, 0, status, w - 1, curses.color_pair(2))

        for offset, action_line in enumerate(action_lines, start=1):
            stdscr.addnstr(status_y + offset, 0, action_line, w - 1, curses.A_BOLD)

        help_line = "↑↓ cursor  Ctrl←→ actions  Enter add/apply  e edit  E raw  d delete  u undo  ^R redo  s save  t test  ? help  q quit"
        stdscr.addnstr(h - 1, 0, help_line, w - 1, curses.A_DIM)
        stdscr.refresh()
        return lines, actions

    def show_help(self, stdscr) -> None:
        help_text = [
            "xray-interactive keys",
            "",
            "↑ / ↓          move through JSON",
            "PgUp/PgDn     page",
            "Ctrl+← / →    choose a context action (also [ and ])",
            "Ctrl+↑         jump to parent JSON container",
            "Enter          apply selected context action",
            "e              edit scalar value on the current line",
            "E              edit selected JSON block in $EDITOR",
            "d              delete current scalar/block/list item",
            "u / Ctrl+R     undo / redo",
            "s              atomic save; previous saved file becomes .bak",
            "t              save + `./xray run -test -config ...`",
            "q              quit (asks before discarding unsaved changes)",
            "",
            "Input is JSON-first: 443 -> number, true -> bool, [\"a\"] -> array.",
            "Plain unquoted text becomes a JSON string.",
            "",
            "Press any key to return.",
        ]
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        for i, text in enumerate(help_text[:h-1]):
            stdscr.addnstr(i, 0, text, w - 1, curses.A_BOLD if i == 0 else 0)
        stdscr.refresh()
        stdscr.getch()

    def _read_key(self, stdscr) -> int:
        """
        Read one logical key.

        Modified arrows are not normalized by every curses/Python build.
        When curses.define_key() is unavailable, xterm-compatible terminals
        normally send CSI sequences such as ESC [ 1 ; 5 D for Ctrl+Left.
        Decode those sequences ourselves while preserving bare Esc.
        """
        ch = stdscr.getch()
        if ch != 27 or getattr(curses, "define_key", None) is not None:
            return ch

        # Briefly collect the rest of an ESC/CSI sequence. 25 ms is enough for
        # bytes already queued by a local terminal and keeps bare Esc responsive.
        seq: list[int] = []
        stdscr.timeout(25)
        try:
            for _ in range(8):
                nxt = stdscr.getch()
                if nxt == -1:
                    break
                seq.append(nxt)
                # CSI modified-arrow sequences terminate with A/B/C/D.
                if nxt in (ord("A"), ord("B"), ord("C"), ord("D")):
                    break
        finally:
            stdscr.timeout(-1)

        raw = bytes(x for x in seq if 0 <= x <= 255)
        mapping = {
            b"[1;5D": KEY_CTRL_LEFT,
            b"[1;5C": KEY_CTRL_RIGHT,
            b"[1;5A": KEY_CTRL_UP,
            b"[1;5B": KEY_CTRL_DOWN,
            # A few terminals use CSI 5D/5C/5A/5B instead.
            b"[5D": KEY_CTRL_LEFT,
            b"[5C": KEY_CTRL_RIGHT,
            b"[5A": KEY_CTRL_UP,
            b"[5B": KEY_CTRL_DOWN,
        }
        return mapping.get(raw, 27)

    def run(self, stdscr) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        curses.use_default_colors()
        try:
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(2, curses.COLOR_YELLOW, -1)
        except curses.error:
            pass

        # Some Python/curses builds (including some Python 3.14 packages)
        # do not expose curses.define_key(). Use it when available; otherwise
        # Ctrl+Arrow escape sequences are decoded by _read_key() below.
        define_key = getattr(curses, "define_key", None)
        if define_key is not None:
            for seq, code in (
                ("\x1b[1;5D", KEY_CTRL_LEFT),
                ("\x1b[1;5C", KEY_CTRL_RIGHT),
                ("\x1b[1;5A", KEY_CTRL_UP),
                ("\x1b[1;5B", KEY_CTRL_DOWN),
            ):
                try:
                    define_key(seq, code)
                except curses.error:
                    pass

        while True:
            lines, actions = self.draw(stdscr)
            ch = self._read_key(stdscr)

            if ch in (curses.KEY_UP, ord("k")):
                self.cursor = max(0, self.cursor - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.cursor = min(len(lines) - 1, self.cursor + 1)
            elif ch == curses.KEY_PPAGE:
                self.cursor = max(0, self.cursor - max(1, stdscr.getmaxyx()[0] - 5))
            elif ch == curses.KEY_NPAGE:
                self.cursor = min(len(lines) - 1, self.cursor + max(1, stdscr.getmaxyx()[0] - 5))
            elif ch in (KEY_CTRL_LEFT, ord("[")):
                if actions:
                    self.action_index = (self.action_index - 1) % len(actions)
            elif ch in (KEY_CTRL_RIGHT, ord("]")):
                if actions:
                    self.action_index = (self.action_index + 1) % len(actions)
            elif ch == KEY_CTRL_UP:
                path = self.selected_path(lines)
                if path:
                    self.preferred_path = path[:-1]
            elif ch in (10, 13, curses.KEY_ENTER):
                if actions:
                    path = self.selected_path(lines)
                    new_path = self.apply_action(stdscr, path, actions[self.action_index])
                    if new_path is not None:
                        self.preferred_path = new_path
                        self.action_index = 0
            elif ch == ord("e"):
                line = self.current(lines)
                if line.value_path is not None:
                    self.edit_value(stdscr, line.value_path)
            elif ch == ord("E"):
                self.raw_edit(stdscr, self.selected_path(lines))
            elif ch == ord("d"):
                line = self.current(lines)
                target = line.value_path if line.value_path not in (None, ()) else self.selected_path(lines)
                if target == ():
                    self.status = "Cannot delete config root"
                elif self.confirm(stdscr, f"Delete {path_to_str(target)}?"):
                    parent_path = target[:-1]
                    try:
                        self.mutate(lambda: delete_at(self.config, target))
                        self.preferred_path = parent_path
                        self.status = f"Deleted {path_to_str(target)}"
                    except Exception as e:
                        self.status = f"Delete failed: {e}"
            elif ch == ord("u"):
                self.undo()
            elif ch == 18:  # Ctrl+R
                self.redo()
            elif ch == ord("s"):
                try:
                    self.save()
                except Exception as e:
                    self.status = f"Save failed: {e}"
            elif ch == ord("t"):
                try:
                    self.validate()
                except Exception as e:
                    self.status = f"Validation failed to run: {e}"
            elif ch == ord("?"):
                self.show_help(stdscr)
            elif ch in (ord("q"), 27):
                if self.dirty and not self.confirm(stdscr, "Discard unsaved changes and quit?"):
                    continue
                break


def edit_config(config: dict[str, Any], config_path: Path, xray_binary: Path) -> None:
    editor = Editor(config, config_path, xray_binary)
    curses.wrapper(editor.run)
