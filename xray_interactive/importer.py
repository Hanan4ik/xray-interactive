from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .model import unique_tag


class ImportLinkError(ValueError):
    pass


@dataclass
class ImportResult:
    outbound: dict[str, Any]
    warnings: list[str]


SUPPORTED_TYPE_TO_METHOD = {
    "tcp": "raw",
    "raw": "raw",
    "xhttp": "xhttp",
    "splithttp": "xhttp",
}


def _one(qs: dict[str, list[str]], key: str, default: str = "") -> str:
    values = qs.get(key)
    if not values:
        return default
    return values[-1]


def _label_from_fragment(fragment: str) -> str:
    if not fragment:
        return "imported-vless"
    # Be forgiving about links copied from tools that accidentally put more
    # than one '#' into the fragment. The last fragment is usually the display name.
    label = unquote(fragment.rsplit("#", 1)[-1]).strip()
    # Some malformed generators append query-like fields after '#'.
    if "&" in label and "=" in label:
        label = label.split("&", 1)[0]
    return label or "imported-vless"


def parse_vless_link(link: str, config: dict[str, Any] | None = None) -> ImportResult:
    parts = urlsplit(link.strip())
    if parts.scheme.lower() != "vless":
        raise ImportLinkError(f"Only vless:// links are supported in this version, got {parts.scheme!r}")
    if not parts.username:
        raise ImportLinkError("VLESS link has no user id")
    if not parts.hostname:
        raise ImportLinkError("VLESS link has no server address")
    try:
        port = parts.port
    except ValueError as e:
        raise ImportLinkError(f"Invalid VLESS port: {e}") from e
    if port is None:
        raise ImportLinkError("VLESS link has no port")

    qs = parse_qs(parts.query, keep_blank_values=True)
    warnings: list[str] = []

    link_type = _one(qs, "type", "tcp").lower()
    if link_type not in SUPPORTED_TYPE_TO_METHOD:
        raise ImportLinkError(
            f"Unsupported transport type={link_type!r}. "
            f"Supported in this version: tcp/raw, xhttp/splithttp"
        )
    method = SUPPORTED_TYPE_TO_METHOD[link_type]

    settings: dict[str, Any] = {
        "address": parts.hostname,
        "port": port,
        "id": unquote(parts.username),
        "encryption": _one(qs, "encryption", "none") or "none",
    }
    flow = _one(qs, "flow")
    if flow:
        settings["flow"] = flow

    outbound: dict[str, Any] = {
        "protocol": "vless",
        "settings": settings,
    }

    label = _label_from_fragment(parts.fragment)
    if config is not None:
        label = unique_tag(config, label)
    outbound["tag"] = label

    stream: dict[str, Any] = {"method": method}

    if method == "xhttp":
        xhttp: dict[str, Any] = {}
        for qkey, ckey in (("host", "host"), ("path", "path"), ("mode", "mode")):
            value = _one(qs, qkey)
            if value:
                xhttp[ckey] = value

        extra = _one(qs, "extra")
        if extra:
            try:
                parsed = json.loads(unquote(extra))
                if not isinstance(parsed, dict):
                    raise ValueError("extra must decode to a JSON object")
                xhttp["extra"] = parsed
            except (json.JSONDecodeError, ValueError) as e:
                warnings.append(f"Ignored invalid XHTTP extra=: {e}")

        # XHTTP defaults are intentionally not expanded. Upstream docs recommend
        # usually setting only path unless a non-default behavior is required.
        stream["xhttpSettings"] = xhttp

    security = _one(qs, "security", "none").lower()
    stream["security"] = security

    if security == "reality":
        reality: dict[str, Any] = {}
        sni = _one(qs, "sni")
        fp = _one(qs, "fp")
        pbk = _one(qs, "pbk") or _one(qs, "publicKey") or _one(qs, "password")
        sid = _one(qs, "sid")
        spx = _one(qs, "spx")
        pqv = _one(qs, "pqv")

        if sni:
            reality["serverName"] = sni
        if fp:
            reality["fingerprint"] = fp
        if pbk:
            # Current Xray docs call this field `password`; `publicKey` is the old name.
            reality["password"] = pbk
        if sid or "sid" in qs:
            reality["shortId"] = sid
        if spx:
            reality["spiderX"] = spx
        if pqv:
            reality["mldsa65Verify"] = pqv

        stream["realitySettings"] = reality
    elif security not in {"none", ""}:
        warnings.append(
            f"security={security!r} was preserved, but this MVP only has a guided editor for REALITY"
        )

    outbound["streamSettings"] = stream

    consumed = {
        "type", "security", "encryption", "flow", "host", "path", "mode", "extra",
        "sni", "fp", "pbk", "publicKey", "password", "sid", "spx", "pqv",
    }
    ignored = sorted(k for k in qs if k not in consumed)
    if ignored:
        warnings.append("Unmapped link parameters: " + ", ".join(ignored))

    return ImportResult(outbound=outbound, warnings=warnings)


def import_link(config: dict[str, Any], link: str) -> ImportResult:
    result = parse_vless_link(link, config=config)
    outbounds = config.setdefault("outbounds", [])
    if not isinstance(outbounds, list):
        raise ImportLinkError("config.outbounds exists but is not an array")
    outbounds.append(result.outbound)
    return result
