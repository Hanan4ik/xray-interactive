from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .model import JsonPath, get_at, unique_tag


@dataclass(frozen=True)
class Action:
    label: str
    op: str
    key: str | None = None
    default: Any = None
    help: str = ""


def _is_path(path: JsonPath, *parts: object) -> bool:
    if len(path) != len(parts):
        return False
    for got, want in zip(path, parts):
        if want is int:
            if not isinstance(got, int):
                return False
        elif got != want:
            return False
    return True


def _ancestor_item(config: dict[str, Any], path: JsonPath, root_key: str) -> dict[str, Any] | None:
    if len(path) >= 2 and path[0] == root_key and isinstance(path[1], int):
        try:
            item = config[root_key][path[1]]
            return item if isinstance(item, dict) else None
        except (KeyError, IndexError, TypeError):
            return None
    return None


def _missing_fields(node: dict[str, Any], specs: list[tuple[str, Any, str]]) -> list[Action]:
    out: list[Action] = []
    for key, default, help_text in specs:
        if key not in node:
            out.append(Action(f"+ {key}", "set_field", key, default, help_text))
    return out


INBOUND_BASE_FIELDS = [
    ("listen", "0.0.0.0", "Listening address"),
    ("port", 1080, "Listening port"),
    ("protocol", "vless", "Inbound protocol"),
    ("settings", {}, "Protocol-specific settings"),
    ("streamSettings", {}, "Transport/security settings"),
    ("tag", "inbound", "Unique inbound tag"),
    ("sniffing", {"enabled": True, "destOverride": ["http", "tls"]}, "Traffic sniffing"),
]

OUTBOUND_BASE_FIELDS = [
    ("sendThrough", "0.0.0.0", "Source address"),
    ("protocol", "vless", "Outbound protocol"),
    ("settings", {}, "Protocol-specific settings"),
    ("tag", "outbound", "Unique outbound tag"),
    ("streamSettings", {}, "Transport/security settings"),
    ("proxySettings", {"tag": "", "transportLayer": False}, "Forward through another outbound"),
    ("mux", {"enabled": False}, "Mux.Cool settings"),
    ("targetStrategy", "AsIs", "Outbound target resolution strategy"),
]

VLESS_INBOUND_SETTINGS = [
    ("users", [], "Allowed VLESS users"),
    ("flow", "", "Default flow for users"),
    ("decryption", "none", "VLESS encryption/decryption setting"),
    ("fallbacks", [], "Fallback destinations"),
]

VLESS_USER_FIELDS = [
    ("id", "", "VLESS UUID or mapped custom id"),
    ("level", 0, "Policy level"),
    ("email", "", "User identifier used by routing/stats"),
    ("flow", "", "Flow, e.g. xtls-rprx-vision"),
    ("reverse", {}, "VLESS reverse settings"),
]

VLESS_OUTBOUND_SETTINGS = [
    ("address", "example.com", "Server address"),
    ("port", 443, "Server port"),
    ("id", "", "VLESS UUID or mapped custom id"),
    ("encryption", "none", "VLESS encryption setting"),
    ("flow", "", "Flow, e.g. xtls-rprx-vision"),
    ("level", 0, "Policy level"),
    ("reverse", {}, "VLESS reverse settings"),
]

SOCKS_INBOUND_SETTINGS = [
    ("auth", "noauth", "noauth | password"),
    ("users", [], "Username/password accounts; used when auth=password"),
    ("udp", False, "Enable UDP support"),
    ("ip", "127.0.0.1", "Client-reachable local IP used for UDP replies"),
    ("userLevel", 0, "Policy level"),
]

HTTP_INBOUND_SETTINGS = [
    ("users", [], "HTTP Basic Authentication accounts; empty disables authentication"),
    ("allowTransparent", False, "Forward all HTTP requests, not only proxy requests"),
    ("userLevel", 0, "Policy level"),
]

PROXY_USER_FIELDS = [
    ("user", "", "Username"),
    ("pass", "", "Password"),
]

TUNNEL_SETTINGS = [
    ("allowedNetwork", "tcp", "tcp | udp | tcp,udp"),
    ("rewriteAddress", "localhost", "Target address"),
    ("rewritePort", 0, "Target port; 0 means listening port"),
    ("portMap", {}, "Local-port to remote endpoint map"),
    ("followRedirect", False, "Use redirected original destination"),
    ("userLevel", 0, "Policy level"),
]

STREAM_FIELDS = [
    ("method", "raw", "raw | xhttp | mkcp | grpc | websocket | httpupgrade | hysteria"),
    ("security", "none", "none | reality | tls"),
    ("xhttpSettings", {}, "XHTTP transport settings"),
    ("realitySettings", {}, "REALITY transport security settings"),
    ("sockopt", {}, "Socket options"),
]

XHTTP_FIELDS = [
    ("host", "", "HTTP host override; usually omit unless needed"),
    ("path", "/", "XHTTP path"),
    ("mode", "auto", "auto | packet-up | stream-up | stream-one"),
    ("extra", {}, "Advanced raw XHTTP JSON options"),
]

REALITY_INBOUND_FIELDS = [
    ("show", False, "Debug output"),
    ("target", "example.com:443", "Camouflage target; required server-side"),
    ("xver", 0, "PROXY protocol version for fallback"),
    ("serverNames", ["example.com"], "Accepted serverName values"),
    ("privateKey", "", "Server private key"),
    ("minClientVer", "26.3.27", "Minimum client version"),
    ("maxClientVer", "", "Maximum client version"),
    ("maxTimeDiff", 0, "Maximum client/server time difference in ms"),
    ("shortIds", [""], "Allowed client shortIds"),
    ("mldsa65Seed", "", "Optional ML-DSA-65 signing seed"),
    ("limitFallbackUpload", {"afterBytes": 0, "bytesPerSec": 0, "burstBytesPerSec": 0}, "Fallback upload limiter"),
    ("limitFallbackDownload", {"afterBytes": 0, "bytesPerSec": 0, "burstBytesPerSec": 0}, "Fallback download limiter"),
]

REALITY_OUTBOUND_FIELDS = [
    ("serverName", "", "Server name/SNI"),
    ("fingerprint", "chrome", "uTLS fingerprint"),
    ("password", "", "Server REALITY public material; formerly publicKey"),
    ("shortId", "", "One of server shortIds"),
    ("mldsa65Verify", "", "Optional ML-DSA-65 verification key"),
    ("spiderX", "", "Initial crawler path/parameters"),
]

ROUTING_FIELDS = [
    ("domainStrategy", "AsIs", "AsIs | IPIfNonMatch | IPOnDemand"),
    ("rules", [], "Routing rules, first match wins"),
    ("balancers", [], "Load balancers"),
]

RULE_FIELDS = [
    ("domain", [], "Domain matchers"),
    ("ip", [], "IP/CIDR/geosite matchers"),
    ("port", "", "Destination ports"),
    ("sourcePort", "", "Source ports"),
    ("localPort", "", "Local ports"),
    ("network", "tcp", "tcp | udp | tcp,udp"),
    ("sourceIP", [], "Source IP matchers"),
    ("localIP", [], "Local IP matchers"),
    ("user", [], "User/email matchers"),
    ("vlessRoute", "", "VLESS route"),
    ("inboundTag", [], "Inbound tags"),
    ("protocol", [], "Sniffed protocol matchers"),
    ("attrs", {}, "Sniffed HTTP attributes"),
    ("process", [], "Process matchers"),
    ("outboundTag", "", "Destination outbound tag"),
    ("balancerTag", "", "Destination balancer tag"),
    ("ruleTag", "", "Rule name"),
    ("webhook", {"url": "", "deduplication": 300}, "Rule webhook"),
]


def actions_for(config: dict[str, Any], path: JsonPath) -> list[Action]:
    try:
        node = get_at(config, path)
    except Exception:
        return []

    if path == ("inbounds",) and isinstance(node, list):
        return [
            Action("+ VLESS inbound", "append_template", default="vless"),
            Action("+ Tunnel inbound", "append_template", default="tunnel"),
            Action("+ SOCKS inbound", "append_template", default="socks"),
            Action("+ HTTP inbound", "append_template", default="http"),
        ]

    if path == ("outbounds",) and isinstance(node, list):
        return [
            Action("+ VLESS outbound", "append_template", default="vless-outbound"),
        ]

    if _is_path(path, "inbounds", int) and isinstance(node, dict):
        actions = _missing_fields(node, INBOUND_BASE_FIELDS)
        if node.get("protocol") == "vless":
            actions.insert(0, Action("Generate VLESS UUID", "generate_uuid"))
        return actions

    if _is_path(path, "outbounds", int) and isinstance(node, dict):
        actions = _missing_fields(node, OUTBOUND_BASE_FIELDS)
        if node.get("protocol") == "vless":
            actions.insert(0, Action("Generate VLESS UUID", "generate_uuid"))
        return actions

    inbound = _ancestor_item(config, path, "inbounds")
    outbound = _ancestor_item(config, path, "outbounds")

    if len(path) >= 3 and path[-1] == "settings" and isinstance(node, dict):
        if inbound and inbound.get("protocol") == "vless":
            return _missing_fields(node, VLESS_INBOUND_SETTINGS)
        if inbound and inbound.get("protocol") == "tunnel":
            return _missing_fields(node, TUNNEL_SETTINGS)
        if inbound and inbound.get("protocol") == "socks":
            return _missing_fields(node, SOCKS_INBOUND_SETTINGS)
        if inbound and inbound.get("protocol") == "http":
            return _missing_fields(node, HTTP_INBOUND_SETTINGS)
        if outbound and outbound.get("protocol") == "vless":
            return _missing_fields(node, VLESS_OUTBOUND_SETTINGS)

    if len(path) >= 4 and path[-1] == "users" and isinstance(node, list) and inbound:
        if inbound.get("protocol") == "vless":
            return [Action("+ VLESS user", "append_template", default="vless-user")]
        if inbound.get("protocol") in {"socks", "http"}:
            return [Action("+ username/password user", "append_template", default="proxy-user")]

    if len(path) >= 5 and path[-2] == "users" and isinstance(path[-1], int) and isinstance(node, dict) and inbound:
        if inbound.get("protocol") == "vless":
            return _missing_fields(node, VLESS_USER_FIELDS) + [Action("Generate UUID here", "generate_uuid")]
        if inbound.get("protocol") in {"socks", "http"}:
            return _missing_fields(node, PROXY_USER_FIELDS)

    if path and path[-1] == "streamSettings" and isinstance(node, dict):
        actions = [
            Action("Use XHTTP", "use_xhttp", help="Set method=xhttp and create xhttpSettings"),
            Action("Enable REALITY", "enable_reality", help="Set security=reality and create realitySettings"),
        ]
        actions += _missing_fields(node, STREAM_FIELDS)
        return actions

    if path and path[-1] == "xhttpSettings" and isinstance(node, dict):
        return _missing_fields(node, XHTTP_FIELDS)

    if path and path[-1] == "realitySettings" and isinstance(node, dict):
        if inbound is not None:
            return _missing_fields(node, REALITY_INBOUND_FIELDS)
        if outbound is not None:
            return _missing_fields(node, REALITY_OUTBOUND_FIELDS)

    if path == ("routing",) and isinstance(node, dict):
        return _missing_fields(node, ROUTING_FIELDS)

    if path == ("routing", "rules") and isinstance(node, list):
        return [Action("+ routing rule", "append_template", default="routing-rule")]

    if len(path) == 3 and path[:2] == ("routing", "rules") and isinstance(path[2], int) and isinstance(node, dict):
        return _missing_fields(node, RULE_FIELDS)

    if path == ():
        # All top-level entities are present in --create-config by design.
        return [
            Action("Go to inbounds", "jump", default=("inbounds",)),
            Action("Go to outbounds", "jump", default=("outbounds",)),
            Action("Go to routing", "jump", default=("routing",)),
        ]

    if isinstance(node, list):
        return [Action("+ JSON item", "append_json")]
    if isinstance(node, dict):
        return [Action("+ custom key", "custom_key")]
    return []


def template_for(config: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind == "vless":
        return {
            "listen": "0.0.0.0",
            "port": 443,
            "protocol": "vless",
            "settings": {"users": [], "decryption": "none"},
            "streamSettings": {},
            "tag": unique_tag(config, "vless-in"),
        }
    if kind == "tunnel":
        return {
            "listen": "127.0.0.1",
            "port": 1080,
            "protocol": "tunnel",
            "settings": {
                "allowedNetwork": "tcp",
                "rewriteAddress": "localhost",
                "rewritePort": 0,
                "followRedirect": False,
                "userLevel": 0,
            },
            "tag": unique_tag(config, "tunnel-in"),
        }
    if kind == "socks":
        return {
            "listen": "127.0.0.1",
            "port": 1080,
            "protocol": "socks",
            "settings": {
                "auth": "noauth",
                "users": [],
                "udp": False,
                "ip": "127.0.0.1",
                "userLevel": 0,
            },
            "tag": unique_tag(config, "socks-in"),
        }
    if kind == "http":
        return {
            "listen": "127.0.0.1",
            "port": 8080,
            "protocol": "http",
            "settings": {
                "users": [],
                "allowTransparent": False,
                "userLevel": 0,
            },
            "tag": unique_tag(config, "http-in"),
        }
    if kind == "vless-outbound":
        return {
            "protocol": "vless",
            "settings": {
                "address": "example.com",
                "port": 443,
                "id": "",
                "encryption": "none",
            },
            "streamSettings": {},
            "tag": unique_tag(config, "vless-out"),
        }
    if kind == "vless-user":
        return {
            "id": "",
            "level": 0,
            "email": "",
            "flow": "",
        }
    if kind == "proxy-user":
        return {"user": "", "pass": ""}
    if kind == "routing-rule":
        return {"outboundTag": ""}
    raise ValueError(f"unknown template kind: {kind}")
