# xray-interactive

Interactive, context-aware editor for Xray-core JSON configuration.

The tool **intentionally works only when the current working directory contains the Xray-core binary named `xray`** (`xray.exe` on Windows is also accepted). It never silently searches `$PATH`.

## Current scope

Guided editing is implemented for:

- top-level Xray config;
- `inbounds`;
- `outbounds`;
- `routing`;
- VLESS inbound/outbound;
- `tunnel` inbound (the former dokodemo-door);
- SOCKS and HTTP local proxy inbounds, including username/password users;
- XHTTP transport;
- REALITY transport security;
- VLESS share-link import into `outbounds`.

Anything outside the guided schema can still be changed via **custom JSON key/item** actions or the **raw block editor** (`E`).

## Install

From the source directory:

```bash
python3 -m pip install -e .
```

Or use the included source launcher directly:

```bash
chmod +x xray-interactive
```

The working directory should look like:

```text
xray
xray-interactive        # only if using the source launcher
config.json             # after creation
```

If installed with pip/pipx, `xray-interactive` itself can live anywhere; **the shell's current directory still must contain `./xray`**.

## Commands

Create a config with every documented top-level entity and immediately open the TUI:

```bash
xray-interactive --create-config
```

Open an existing `config.json`:

```bash
xray-interactive --edit-config
```

No mode is also an alias for editing:

```bash
xray-interactive
```

Import a VLESS sharing link as an outbound:

```bash
xray-interactive --import-link 'vless://...'
```

Import and immediately open the editor:

```bash
xray-interactive --import-link 'vless://...' --edit-after-import
```

Validate with the **local** Xray binary:

```bash
xray-interactive --validate
```

Use a different config filename:

```bash
xray-interactive --edit-config --config client.json
```

## TUI

The JSON view is structural, not a text-only syntax highlighter. Every rendered line remembers its JSON path.

- Cursor outside child blocks → root object is selected.
- Cursor on `inbounds` array → the whole `inbounds` array is selected.
- Cursor inside one inbound → that inbound object is selected.
- Cursor inside `settings` / `streamSettings` / `realitySettings` → that deeper block is selected.

The selected block is highlighted and the bottom action bar is recalculated from its schema context.

Keys:

```text
↑ / ↓          move through JSON
PgUp / PgDn    page
Ctrl+← / →     choose context action
[ / ]          fallback for terminals that don't report Ctrl+arrows cleanly
Ctrl+↑         jump to parent container
Enter          apply selected action
e              edit scalar on current line
E              replace selected block using $EDITOR
d              delete current value/block/item
u              undo
Ctrl+R         redo
s              atomic save (+ config.json.bak)
t              save and run ./xray run -test -config config.json
?              help
q              quit
```

Input is JSON-first. Examples:

```text
443                 -> number
true                -> boolean
["http", "tls"]     -> array
{"a": 1}            -> object
example.com         -> string
```

## VLESS import mapping

The importer currently understands common VLESS URI fields:

- `type=tcp` / `type=raw` → current `streamSettings.method = "raw"`
- `type=xhttp` / `type=splithttp` → `method = "xhttp"`
- `security=reality`
- `sni` → `realitySettings.serverName`
- `fp` → `realitySettings.fingerprint`
- `pbk` / old `publicKey` → current `realitySettings.password`
- `sid` → `realitySettings.shortId`
- `spx` → `realitySettings.spiderX`
- XHTTP `host`, `path`, `mode`, `extra`
- VLESS `encryption`, `flow`

Unknown query parameters are not injected into Xray JSON; they are reported as warnings.

## Safety / integrity behavior

- Existing configs are parsed with Python's `json` module before editing.
- Writes are atomic (`tempfile` + `os.replace`).
- The previous saved version is retained as `config.json.bak`.
- Xray validation is delegated to the binary in the current directory.
- The guided editor does not claim that a partially filled block is valid; press `t` to ask Xray itself.

## Design note: `tunnel` vs `tun`

This version implements `protocol: "tunnel"` from `/config/inbounds/tunnel.html` — the port-mapping/transparent-proxy inbound formerly called dokodemo-door.

Xray also has a separate `protocol: "tun"` that creates a TUN interface. It is intentionally not exposed in the guided schema yet.


## Compatibility note: Python 3.14 / curses

Version 0.1.1 no longer requires `curses.define_key()`. On Python/curses builds
where that function is unavailable, xray-interactive decodes common
xterm-compatible Ctrl+Arrow escape sequences itself. `[` and `]` remain
fallback keys for switching context actions.

Starting with version 0.1.2, the context-action picker wraps onto additional
terminal rows instead of truncating actions that do not fit the window width.
