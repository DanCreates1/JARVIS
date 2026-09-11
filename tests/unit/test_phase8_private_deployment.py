import json
from pathlib import Path
from typing import Any

import pytest

from jarvis.remote.deployment import (
    PrivateDeploymentError,
    build_private_deployment_plan,
    load_tailscale_status,
)


def _status(**self_overrides: object) -> dict[str, Any]:
    self_node: dict[str, object] = {
        "Online": True,
        "DNSName": "jarvis-laptop.example-tailnet.ts.net.",
    }
    self_node.update(self_overrides)
    return {
        "BackendState": "Running",
        "TailscaleIPs": ["100.64.0.10", "fd7a:115c:a1e0::10"],
        "Self": self_node,
    }


def test_builds_loopback_only_single_replica_plan() -> None:
    plan = build_private_deployment_plan(_status(), backend_port=8765)

    assert plan.origin == "https://jarvis-laptop.example-tailnet.ts.net"
    assert plan.backend_url == "http://127.0.0.1:8765"
    assert plan.replica_count == 1
    assert plan.public_exposure is False
    assert plan.funnel_allowed is False


@pytest.mark.parametrize(
    ("status", "message"),
    [
        ({}, "backend must be Running"),
        ({"BackendState": "Stopped"}, "backend must be Running"),
        (
            {"BackendState": "Running", "Self": {}, "TailscaleIPs": ["100.64.0.1"]},
            "Self node must be online",
        ),
        (_status(Online=False), "Self node must be online"),
        (_status(DNSName="jarvis.example.test"), "exact .ts.net"),
        (_status(DNSName="jarvis..example.ts.net"), "invalid DNS label"),
        (_status(DNSName="-jarvis.example.ts.net"), "invalid DNS label"),
    ],
)
def test_rejects_unsafe_or_incomplete_tailscale_state(status: dict[str, Any], message: str) -> None:
    with pytest.raises(PrivateDeploymentError, match=message):
        build_private_deployment_plan(status, backend_port=8765)


@pytest.mark.parametrize("port", [0, 65536])
def test_rejects_invalid_backend_port(port: int) -> None:
    with pytest.raises(PrivateDeploymentError, match="between 1 and 65535"):
        build_private_deployment_plan(_status(), backend_port=port)


@pytest.mark.parametrize(
    "addresses",
    [None, [], [""], [100]],
)
def test_rejects_missing_or_invalid_tailscale_addresses(addresses: object) -> None:
    status = _status()
    status["TailscaleIPs"] = addresses

    with pytest.raises(PrivateDeploymentError, match="private address"):
        build_private_deployment_plan(status, backend_port=8765)


@pytest.mark.parametrize("address", ["192.168.1.2", "8.8.8.8", "fd00::1"])
def test_rejects_addresses_outside_tailscale_ranges(address: str) -> None:
    status = _status()
    status["TailscaleIPs"] = [address]

    with pytest.raises(PrivateDeploymentError, match="outside Tailscale ranges"):
        build_private_deployment_plan(status, backend_port=8765)


def test_loads_bounded_status_json(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    path.write_text(json.dumps(_status()), encoding="utf-8")

    assert load_tailscale_status(path)["BackendState"] == "Running"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("[]", "must be an object"),
        ("not-json", "is invalid"),
        ('{"BackendState":"Running","BackendState":"Stopped"}', "duplicate keys"),
    ],
)
def test_rejects_invalid_status_json(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "status.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(PrivateDeploymentError, match=message):
        load_tailscale_status(path)


def test_rejects_oversized_status_json(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    path.write_bytes(b" " * 1_048_577)

    with pytest.raises(PrivateDeploymentError, match="exceeds 1 MiB"):
        load_tailscale_status(path)


def test_rejects_non_utf8_status_json(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    path.write_bytes(b'{"BackendState":"Running"}\xff')

    with pytest.raises(PrivateDeploymentError, match="is invalid"):
        load_tailscale_status(path)
