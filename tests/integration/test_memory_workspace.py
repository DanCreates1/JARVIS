"""Current owner review, admission, quarantine and restart acceptance; synthetic stores only."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jarvis.bootstrap import build_runtime
from jarvis.config import Settings
from jarvis.core import SensitivityClass
from jarvis.memory import (
    MemoryCategory,
    MemoryQuery,
    MemoryStateError,
    ProvenanceSource,
    SQLiteMemoryStore,
    explicit_provenance,
    untrusted_provenance,
)
from jarvis.web import create_app


@pytest.mark.asyncio
async def test_derived_privacy_and_ancestor_correction_expiry_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "derived.db"
    now = datetime.now(UTC)
    async with SQLiteMemoryStore(database) as memory:
        source = await memory.remember(
            host_id="owner",
            category=MemoryCategory.WORKING,
            content="orchard has 91 lanterns",
            provenance=explicit_provenance(source_id="source", source_label="synthetic source"),
            now=now,
        )
        derived = await memory.create_derived(
            host_id="owner",
            category=MemoryCategory.SEMANTIC,
            content="orchard rollup has 91 lanterns",
            source_memory_ids=(source.id,),
            derivation_type="summary",
            sensitivity=SensitivityClass.PUBLIC,
            now=now,
        )
        assert derived.sensitivity is SensitivityClass.PRIVATE
        grandchild = await memory.create_derived(
            host_id="owner",
            category=MemoryCategory.SEMANTIC,
            content="orchard aggregate has 91 lanterns",
            source_memory_ids=(derived.id,),
            derivation_type="summary",
            now=now,
        )
        query = MemoryQuery(host_id="owner", text="orchard", now=now + timedelta(days=8))
        assert await memory.search(query) == ()
        with pytest.raises(MemoryStateError, match="unexpired"):
            await memory.create_derived(
                host_id="owner",
                category=MemoryCategory.SEMANTIC,
                content="expired rollup",
                source_memory_ids=(source.id,),
                derivation_type="summary",
                now=query.now,
            )
        replacement = await memory.correct(
            host_id="owner",
            memory_id=source.id,
            expected_version=source.version,
            content="orchard has 29 lanterns",
            provenance=explicit_provenance(
                source_id="correction", source_label="synthetic correction"
            ),
            now=now,
        )
    async with SQLiteMemoryStore(database) as memory:
        hits = await memory.search(MemoryQuery(host_id="owner", text="orchard", now=now))
        assert [hit.item.id for hit in hits] == [replacement.id]
        assert await memory.get(host_id="owner", memory_id=grandchild.id) is not None
        assert await memory.get(host_id="owner", memory_id=derived.id) is not None


def workspace(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, data_dir=tmp_path, runtime_profile="private-memory")

    async def factory(config: Settings):
        runtime = await build_runtime(config)
        memory, host = runtime.memory_store, runtime.memory_host_id
        assert memory is not None and host is not None
        if not await memory.list(host_id=host):
            await memory.propose(
                host_id=host,
                category=MemoryCategory.PROFILE,
                content="quarantined amber orchard has 91 lanterns",
                confidence=1,
                provenance=untrusted_provenance(
                    source_type=ProvenanceSource.IMPORT,
                    source_id="synthetic-import",
                    import_uri="fixture:amber",
                    source_label="untrusted synthetic import",
                ),
            )
            await memory.remember(
                host_id="foreign-host",
                category=MemoryCategory.PROFILE,
                content="foreign orchard secret",
                provenance=explicit_provenance(
                    source_id="foreign-fixture", source_label="synthetic foreign"
                ),
            )
        return runtime

    return TestClient(create_app(settings, runtime_factory=factory))


def test_review_exact_approval_correction_rejection_retention_and_restart(tmp_path: Path) -> None:
    with workspace(tmp_path) as client:
        page = client.get("/memory", headers={"Cookie": "synthetic=remote"})
        assert page.status_code == 200  # Static navigation contains no private data.
        assert page.headers["cache-control"] == "no-store"
        assert "script-src 'self'" in page.headers["content-security-policy"]
        assert client.get("/memory/app.js").status_code == 200
        items = client.get("/api/memory/workspace/items").json()["items"]
        assert len(items) == 1 and items[0]["state"] == "candidate"
        candidate = client.get(f"/api/memory/workspace/items/{items[0]['id']}").json()
        inspected = client.post("/api/memory/workspace/inspect", json={"query": "amber orchard"})
        assert inspected.json()["source_ids"] == []
        assert inspected.json()["projection"] == ""
        path = f"/api/memory/candidates/{candidate['id']}/promote"
        payload = {
            "expected_version": candidate["version"],
            "expected_content_sha256": "0" * 64,
        }
        assert client.post(path, json=payload).status_code == 409
        payload["expected_content_sha256"] = candidate["content_sha256"]
        assert client.post(path, json={**payload, "trust": "trusted_host"}).status_code == 422
        approved = client.post(path, json=payload)
        assert approved.status_code == 200
        assert client.post(path, json=payload).status_code == 409
        inspected = client.post(
            "/api/memory/workspace/inspect", json={"query": "amber orchard"}
        ).json()
        assert inspected["source_ids"] == [candidate["id"]]
        assert "FTS5 matched" in inspected["hits"][0]["reason"]
        assert "confirmed untrusted-source" in inspected["hits"][0]["reason"]
        assert len(inspected["projection"]) <= 4000
        corrected = client.post(
            f"/api/memory/{candidate['id']}/correct",
            json={
                "expected_version": approved.json()["version"],
                "content": "amber orchard has 29 lanterns",
            },
        ).json()
        assert corrected["supersedes_id"] == candidate["id"]
        assert (
            client.post(
                f"/api/memory/{candidate['id']}/correct",
                json={"expected_version": approved.json()["version"], "content": "stale"},
            ).status_code
            == 409
        )
        corrected_id = corrected["id"]
    with workspace(tmp_path) as client:
        result = client.post(
            "/api/memory/workspace/inspect", json={"query": "amber orchard"}
        ).json()
        assert result["source_ids"] == [corrected_id]
        assert "29 lanterns" in result["projection"] and "91 lanterns" not in result["projection"]
        assert client.delete(f"/api/memories/{corrected_id}").status_code == 200
        assert client.get(f"/api/memory/workspace/items/{corrected_id}").status_code == 404
        assert (
            client.post("/api/memory/workspace/inspect", json={"query": "amber orchard"}).json()[
                "source_ids"
            ]
            == []
        )
        rules = client.get("/api/memory/workspace/retention").json()
        assert len(rules) == 5
        rule = client.post(
            "/api/memory/workspace/retention", json={"category": "semantic", "days": 1}
        )
        assert rule.status_code == 200 and rule.json()["retention_days"] == 1
        assert client.post("/api/memory/workspace/expire", json={}).status_code == 200
        assert (
            client.post(
                "/api/memory/workspace/retention", json={"category": "semantic", "days": 0}
            ).status_code
            == 422
        )


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "proxy.example.test"},
        {"Origin": "https://evil.example.test"},
        {"Sec-Fetch-Site": "cross-site"},
        {"X-Forwarded-For": "127.0.0.1"},
        {"Forwarded": "for=127.0.0.1"},
        {"Authorization": "Bearer synthetic"},
        {"Cookie": "synthetic=remote"},
    ],
)
def test_remote_credentials_proxy_and_cross_origin_cannot_read_or_write(
    tmp_path: Path, headers: dict[str, str]
) -> None:
    with workspace(tmp_path) as client:
        for path in (
            "/api/memories",
            "/api/memory/workspace/items",
            "/api/memory/search?query=orchard",
        ):
            assert client.get(path, headers=headers).status_code == 403
        assert (
            client.post("/api/memories", headers=headers, json={"content": "forged"}).status_code
            == 403
        )
        assert len(client.get("/api/memory/workspace/items").json()["items"]) == 1


def test_bounds_foreign_host_denial_pagination_and_reject(tmp_path: Path) -> None:
    with workspace(tmp_path) as client:
        runtime = client.app.state.runtime
        assert client.portal is not None
        foreign = client.portal.call(lambda: runtime.memory_store.list(host_id="foreign-host"))[0]
        assert client.get(f"/api/memory/workspace/items/{foreign.id}").status_code == 404
        assert (
            client.post(
                f"/api/memory/workspace/items/{foreign.id}/reject", json={"expected_version": 1}
            ).status_code
            == 409
        )
        assert client.delete(f"/api/memories/{foreign.id}").status_code == 404
        assert (
            client.post("/api/memory/workspace/inspect", json={"query": "foreign orchard"}).json()[
                "hits"
            ]
            == []
        )
        for number in range(22):
            response = client.post(
                "/api/memories", json={"content": f"synthetic acorn number {number}"}
            )
            assert response.status_code == 201
        first = client.get("/api/memory/workspace/items").json()
        second = client.get("/api/memory/workspace/items?offset=20").json()
        assert len(first["items"]) == 20 and first["has_more"]
        assert len(second["items"]) == 3 and not second["has_more"]
        assert {item["id"] for item in first["items"]}.isdisjoint(
            item["id"] for item in second["items"]
        )
        candidate = client.get("/api/memory/workspace/items?state=candidate").json()["items"][0]
        path = f"/api/memory/workspace/items/{candidate['id']}/reject"
        assert (
            client.post(path, json={"expected_version": candidate["version"]}).json()["state"]
            == "rejected"
        )
        assert client.post(path, json={"expected_version": candidate["version"]}).status_code == 409
        for query in ("offset=-1", "offset=10001", "state=unknown", "category=unknown"):
            assert client.get(f"/api/memory/workspace/items?{query}").status_code == 422
        assert (
            client.post("/api/memory/workspace/inspect", json={"query": "x" * 201}).status_code
            == 422
        )
        assert client.post("/api/memories", content=b"x" * 262145).status_code == 413


def test_expiry_and_transitive_delete_survive_restart(tmp_path: Path) -> None:
    with workspace(tmp_path) as client:
        runtime = client.app.state.runtime
        memory, host = runtime.memory_store, runtime.memory_host_id
        assert client.portal is not None

        async def seed():
            source = await memory.remember(
                host_id=host,
                category=MemoryCategory.SEMANTIC,
                content="deletion sentinel private acorn",
                provenance=explicit_provenance(source_id="source", source_label="synthetic source"),
            )
            derived = await memory.create_derived(
                host_id=host,
                category=MemoryCategory.SEMANTIC,
                content="deletion sentinel private rollup",
                source_memory_ids=(source.id,),
                derivation_type="summary",
            )
            await memory.remember(
                host_id=host,
                category=MemoryCategory.WORKING,
                content="expired sentinel",
                provenance=explicit_provenance(source_id="old", source_label="synthetic old"),
                now=datetime.now(UTC) - timedelta(days=8),
            )
            return source.id, derived.id

        source, derived = client.portal.call(seed)
        assert (
            client.post("/api/memory/workspace/inspect", json={"query": "expired"}).json()[
                "source_ids"
            ]
            == []
        )
    with workspace(tmp_path) as client:
        assert client.delete(f"/api/memories/{source}").status_code == 200
    with workspace(tmp_path) as client:
        assert client.get(f"/api/memory/workspace/items/{derived}").status_code == 404
        result = client.post(
            "/api/memory/workspace/inspect", json={"query": "deletion sentinel"}
        ).json()
        assert result["source_ids"] == []
