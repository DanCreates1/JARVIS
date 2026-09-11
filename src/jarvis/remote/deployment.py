"""Fail-closed Phase 8D private-deployment planning."""

from __future__ import annotations

import json
from collections.abc import Mapping
from ipaddress import IPv4Network, IPv6Network, ip_address
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_TS_NET_SUFFIX = ".ts.net"
_DNS_LABEL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")
MAX_TAILSCALE_STATUS_BYTES = 1_048_576
_TAILSCALE_IPV4 = IPv4Network("100.64.0.0/10")
_TAILSCALE_IPV6 = IPv6Network("fd7a:115c:a1e0::/48")


class PrivateDeploymentError(ValueError):
    """Raised when a Tailscale node cannot safely host the private gateway."""


class PrivateDeploymentPlan(BaseModel):
    """Sanitized deployment values derived from live Tailscale state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    topology: Literal["tailscale-serve"] = "tailscale-serve"
    origin: str
    fqdn: str
    backend_host: Literal["127.0.0.1"] = "127.0.0.1"
    backend_port: int = Field(ge=1, le=65535)
    replica_count: Literal[1] = 1
    public_exposure: Literal[False] = False
    funnel_allowed: Literal[False] = False

    @property
    def backend_url(self) -> str:
        return f"http://{self.backend_host}:{self.backend_port}"


def build_private_deployment_plan(
    status: Mapping[str, Any], *, backend_port: int
) -> PrivateDeploymentPlan:
    """Derive one private HTTPS origin without trusting caller-supplied hostnames."""
    if not 1 <= backend_port <= 65535:
        raise PrivateDeploymentError("backend port must be between 1 and 65535")
    if status.get("BackendState") != "Running":
        raise PrivateDeploymentError("Tailscale backend must be Running")

    self_node = status.get("Self")
    if not isinstance(self_node, Mapping):
        raise PrivateDeploymentError("Tailscale status is missing Self node data")
    if self_node.get("Online") is not True:
        raise PrivateDeploymentError("Tailscale Self node must be online")

    raw_dns_name = self_node.get("DNSName")
    if not isinstance(raw_dns_name, str):
        raise PrivateDeploymentError("Tailscale Self DNSName is missing")
    fqdn = _normalize_ts_net_name(raw_dns_name)

    addresses = status.get("TailscaleIPs")
    if not isinstance(addresses, list) or not addresses:
        raise PrivateDeploymentError("Tailscale status has no assigned private address")
    for raw_address in addresses:
        if not isinstance(raw_address, str) or not raw_address.strip():
            raise PrivateDeploymentError("Tailscale status contains an invalid private address")
        try:
            address = ip_address(raw_address)
        except ValueError as exc:
            raise PrivateDeploymentError(
                "Tailscale status contains an invalid private address"
            ) from exc
        expected_range = _TAILSCALE_IPV4 if address.version == 4 else _TAILSCALE_IPV6
        if address not in expected_range:
            raise PrivateDeploymentError(
                "Tailscale status contains an address outside Tailscale ranges"
            )

    return PrivateDeploymentPlan(
        origin=f"https://{fqdn}",
        fqdn=fqdn,
        backend_port=backend_port,
    )


def load_tailscale_status(path: Path) -> Mapping[str, Any]:
    """Load bounded status JSON and reject duplicate object keys."""
    try:
        with path.open("rb") as status_file:
            payload = status_file.read(MAX_TAILSCALE_STATUS_BYTES + 1)
        if len(payload) > MAX_TAILSCALE_STATUS_BYTES:
            raise PrivateDeploymentError("Tailscale status JSON exceeds 1 MiB")
        raw = payload.decode("utf-8")
        parsed = json.loads(raw, object_pairs_hook=_unique_object)
    except OSError as exc:
        raise PrivateDeploymentError("Tailscale status JSON is unavailable") from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PrivateDeploymentError("Tailscale status JSON is invalid") from exc
    if not isinstance(parsed, Mapping):
        raise PrivateDeploymentError("Tailscale status JSON must be an object")
    return parsed


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PrivateDeploymentError("Tailscale status JSON has duplicate keys")
        result[key] = value
    return result


def _normalize_ts_net_name(raw: str) -> str:
    fqdn = raw.strip().rstrip(".").casefold()
    if len(fqdn) > 253 or not fqdn.endswith(_TS_NET_SUFFIX):
        raise PrivateDeploymentError("Tailscale DNSName must be an exact .ts.net hostname")
    labels = fqdn.split(".")
    if len(labels) < 4:
        raise PrivateDeploymentError("Tailscale DNSName is incomplete")
    for label in labels:
        if (
            not label
            or len(label) > 63
            or label[0] == "-"
            or label[-1] == "-"
            or any(character not in _DNS_LABEL_CHARS for character in label)
        ):
            raise PrivateDeploymentError("Tailscale DNSName contains an invalid DNS label")
    return fqdn
