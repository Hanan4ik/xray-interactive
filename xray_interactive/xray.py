from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class XrayResult:
    ok: bool
    output: str
    returncode: int


def find_xray_binary(cwd: Path | None = None) -> Path:
    """
    xray-interactive deliberately does NOT search PATH.
    The Xray binary must be in the current working directory.
    """
    cwd = (cwd or Path.cwd()).resolve()
    candidates = [cwd / "xray", cwd / "xray.exe"]
    for candidate in candidates:
        if candidate.is_file():
            if os.name == "nt" or os.access(candidate, os.X_OK):
                return candidate
            raise RuntimeError(
                f"Found {candidate.name!r} in {cwd}, but it is not executable. "
                f"Run: chmod +x {candidate.name}"
            )
    raise RuntimeError(
        f"xray-interactive only works when the current directory contains "
        f"the Xray-core binary named 'xray' (or 'xray.exe'). Current directory: {cwd}"
    )


def run_xray(binary: Path, *args: str, timeout: int = 15) -> XrayResult:
    try:
        p = subprocess.run(
            [str(binary), *args],
            cwd=binary.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return XrayResult(p.returncode == 0, p.stdout.strip(), p.returncode)
    except subprocess.TimeoutExpired as e:
        output = ((e.stdout or "") + "\n" + (e.stderr or "")).strip()
        return XrayResult(False, f"Xray command timed out.\n{output}".strip(), 124)


def validate_config(binary: Path, config_path: Path) -> XrayResult:
    return run_xray(binary, "run", "-test", "-config", str(config_path.resolve()), timeout=20)


def generate_uuid(binary: Path) -> XrayResult:
    return run_xray(binary, "uuid")


def xray_version(binary: Path) -> XrayResult:
    # Current builds accept `version`; old builds usually print version with -version.
    result = run_xray(binary, "version")
    if result.ok:
        return result
    return run_xray(binary, "-version")
