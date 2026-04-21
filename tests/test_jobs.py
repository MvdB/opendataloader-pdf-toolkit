from __future__ import annotations

import pytest
import fakeredis.aioredis

from pdf_toolkit.web.jobs import (
    InMemoryJobRegistry,
    Job,
    JobStatus,
    RedisJobRegistry,
    create_registry,
    now_utc,
)


@pytest.fixture
def redis_registry() -> RedisJobRegistry:
    """Fresh fake Redis per test — no shared state across cases."""
    return RedisJobRegistry(fakeredis.aioredis.FakeRedis(decode_responses=True))


@pytest.fixture
def memory_registry() -> InMemoryJobRegistry:
    return InMemoryJobRegistry()


@pytest.mark.parametrize("registry_fx", ["memory_registry", "redis_registry"])
async def test_create_and_get_roundtrip(request: pytest.FixtureRequest, registry_fx: str) -> None:
    registry = request.getfixturevalue(registry_fx)
    job = await registry.create(profile="rag", enrich=True, enrich_summarize=True)
    fetched = await registry.get(job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.profile == "rag"
    assert fetched.enrich is True
    assert fetched.enrich_summarize is True
    assert fetched.status == JobStatus.queued


@pytest.mark.parametrize("registry_fx", ["memory_registry", "redis_registry"])
async def test_update_persists_fields(request: pytest.FixtureRequest, registry_fx: str) -> None:
    registry = request.getfixturevalue(registry_fx)
    job = await registry.create(profile="rag")
    now = now_utc()
    await registry.update(
        job.id,
        status=JobStatus.succeeded,
        output_dir="/tmp/out",
        finished_at=now,
    )
    fetched = await registry.get(job.id)
    assert fetched is not None
    assert fetched.status == JobStatus.succeeded
    assert fetched.output_dir == "/tmp/out"
    assert fetched.finished_at == now


@pytest.mark.parametrize("registry_fx", ["memory_registry", "redis_registry"])
async def test_all_lists_every_created_job(request: pytest.FixtureRequest, registry_fx: str) -> None:
    registry = request.getfixturevalue(registry_fx)
    a = await registry.create(profile="rag")
    b = await registry.create(profile="structured")
    listed = await registry.all()
    assert {j.id for j in listed} == {a.id, b.id}


@pytest.mark.parametrize("registry_fx", ["memory_registry", "redis_registry"])
async def test_get_missing_returns_none(request: pytest.FixtureRequest, registry_fx: str) -> None:
    registry = request.getfixturevalue(registry_fx)
    assert await registry.get("does-not-exist") is None


async def test_job_to_dict_roundtrip_via_redis_preserves_timestamps(redis_registry: RedisJobRegistry) -> None:
    job = await redis_registry.create(profile="rag")
    fetched = await redis_registry.get(job.id)
    assert fetched is not None
    # Redis stored the ISO string; Job.from_dict parsed it back into a datetime.
    assert fetched.created_at == job.created_at


def test_factory_default_is_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOB_REGISTRY", raising=False)
    assert isinstance(create_registry(), InMemoryJobRegistry)


def test_factory_honours_job_registry_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Redis path is constructed lazily; it does not require a running Redis
    # at factory time (the client lazily connects on first command).
    monkeypatch.setenv("JOB_REGISTRY", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    registry = create_registry()
    assert isinstance(registry, RedisJobRegistry)


def test_job_from_dict_tolerates_missing_enrichment_fields() -> None:
    # Older persisted jobs (pre-enrichment fields) must still load.
    legacy = {
        "id": "abc",
        "profile": "rag",
        "status": "queued",
        "input_paths": [],
        "output_dir": "",
        "created_at": "2026-04-21T00:00:00+00:00",
    }
    job = Job.from_dict(legacy)
    assert job.id == "abc"
    assert job.enrich is False
    assert job.enrich_markdown is False
