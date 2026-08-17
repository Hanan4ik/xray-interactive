from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .importer import ImportLinkError, import_link
from .model import load_config, new_config, save_config
from .tui import edit_config
from .xray import find_xray_binary, validate_config, xray_version


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xray-interactive",
        description="Context-aware interactive Xray-core config editor",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--create-config",
        action="store_true",
        help="create a new config containing all top-level Xray entities, then open the editor",
    )
    mode.add_argument(
        "--edit-config",
        action="store_true",
        help="open the existing config in the interactive editor",
    )
    mode.add_argument(
        "--import-link",
        metavar="LINK",
        help="import a VLESS sharing link as an outbound",
    )
    mode.add_argument(
        "--validate",
        action="store_true",
        help="validate config using the local Xray binary",
    )
    mode.add_argument(
        "--xray-version",
        action="store_true",
        help="show the version of the local Xray binary",
    )
    p.add_argument(
        "--config",
        default="config.json",
        metavar="PATH",
        help="config path relative to the current directory (default: config.json)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="allow --create-config to overwrite an existing config",
    )
    p.add_argument(
        "--edit-after-import",
        action="store_true",
        help="open TUI after --import-link",
    )
    return p


def fail(message: str, code: int = 2) -> int:
    print(f"xray-interactive: error: {message}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # This check is intentionally unconditional, including --help-like normal
    # operations after argparse has parsed args. The tool is coupled to the
    # Xray binary in the working directory by design.
    try:
        xray = find_xray_binary(Path.cwd())
    except RuntimeError as e:
        return fail(str(e))

    config_path = (Path.cwd() / args.config).resolve()

    if args.xray_version:
        result = xray_version(xray)
        print(result.output)
        return 0 if result.ok else result.returncode or 1

    if args.create_config:
        if config_path.exists() and not args.force:
            return fail(f"{config_path.name} already exists; use --force to replace it")
        config = new_config()
        save_config(config_path, config, backup=config_path.exists())
        print(f"Created {config_path}")
        edit_config(config, config_path, xray)
        return 0

    if args.import_link is not None:
        if not config_path.exists():
            return fail(f"{config_path.name} does not exist; run --create-config first")
        try:
            config = load_config(config_path)
            result = import_link(config, args.import_link)
            save_config(config_path, config, backup=True)
        except (ValueError, OSError, ImportLinkError) as e:
            return fail(str(e))
        print(f"Imported outbound: {result.outbound.get('tag', '<untagged>')}")
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if args.edit_after_import:
            edit_config(config, config_path, xray)
        return 0

    if args.validate:
        if not config_path.exists():
            return fail(f"{config_path.name} does not exist")
        result = validate_config(xray, config_path)
        if result.output:
            print(result.output)
        return 0 if result.ok else result.returncode or 1

    # No explicit mode is a convenience alias for --edit-config.
    if not config_path.exists():
        return fail(f"{config_path.name} does not exist; run --create-config first")
    try:
        config = load_config(config_path)
    except (ValueError, OSError) as e:
        return fail(str(e))
    edit_config(config, config_path, xray)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
