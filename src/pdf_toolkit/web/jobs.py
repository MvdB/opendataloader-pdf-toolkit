from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    id: str
    profile: str = "rag"
    ocr: bool = False
    enrich: bool = False
    enrich_summarize: bool = False
    enrich_recaption: bool = False
    enrich_embed: bool = False
    enrich_markdown: bool = False
    status: JobStatus = JobStatus.queued
    input_paths: list[str] = field(default_factory=list)
    output_dir: str = ""
    error: str | None = None
    created_at: datetime = field(default_factory=now_utc)
    finished_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat() if self.finished_at else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        return cls(
            id=data["id"],
            profile=data.get("profile", "rag"),
            ocr=bool(data.get("ocr", False)),
            enrich=bool(data.get("enrich", False)),
            enrich_summarize=bool(data.get("enrich_summarize", False)),
            enrich_recaption=bool(data.get("enrich_recaption", False)),
            enrich_embed=bool(data.get("enrich_embed", False)),
            enrich_markdown=bool(data.get("enrich_markdown", False)),
            status=JobStatus(data.get("status", JobStatus.queued.value)),
            input_paths=list(data.get("input_paths") or []),
            output_dir=data.get("output_dir", ""),
            error=data.get("error"),
            created_at=_parse_dt(data.get("created_at")) or now_utc(),
            finished_at=_parse_dt(data.get("finished_at")),
        )


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


class JobRegistry(Protocol):
    """Registry contract for durable or in-process job tracking."""

    async def create(self, **fields: Any) -> Job: ...
    async def update(self, job_id: str, **fields: Any) -> Job: ...
    async def get(self, job_id: str) -> Job | None: ...
    async def all(self) -> list[Job]: ...


class InMemoryJobRegistry:
    """Default registry. Loses state on restart — fine for single-process samples."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def create(self, **fields: Any) -> Job:
        async with self._lock:
            job = Job(id=uuid.uuid4().hex, **fields)
            self._jobs[job.id] = job
            return job

    async def update(self, job_id: str, **fields: Any) -> Job:
        async with self._lock:
            job = self._jobs[job_id]
            for key, value in fields.items():
                setattr(job, key, value)
            return job

    async def get(self, job_id: str) -> Job | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def all(self) -> list[Job]:
        async with self._lock:
            return list(self._jobs.values())


class RedisJobRegistry:
    """Redis-backed registry — survives restarts, can be shared across replicas.

    Storage layout:
      job:<id>     JSON blob of Job.to_dict()
      jobs:all     set of known job ids (for the list endpoint)

    Concurrency: a per-process asyncio lock wraps read-modify-write; this is
    sufficient for single-writer deployments. For multi-worker setups, swap in
    WATCH/MULTI or short-lived Redis locks.
    """

    def __init__(self, client: Any) -> None:
        self._redis = client
        self._lock = asyncio.Lock()

    @classmethod
    def from_url(cls, url: str) -> "RedisJobRegistry":
        import redis.asyncio as aioredis  # local import — redis is in the [redis] extra
        return cls(aioredis.from_url(url, decode_responses=True))

    async def create(self, **fields: Any) -> Job:
        async with self._lock:
            job = Job(id=uuid.uuid4().hex, **fields)
            await self._redis.set(f"job:{job.id}", json.dumps(job.to_dict()))
            await self._redis.sadd("jobs:all", job.id)
            return job

    async def update(self, job_id: str, **fields: Any) -> Job:
        async with self._lock:
            raw = await self._redis.get(f"job:{job_id}")
            if raw is None:
                raise KeyError(job_id)
            job = Job.from_dict(json.loads(raw))
            for key, value in fields.items():
                setattr(job, key, value)
            await self._redis.set(f"job:{job_id}", json.dumps(job.to_dict()))
            return job

    async def get(self, job_id: str) -> Job | None:
        raw = await self._redis.get(f"job:{job_id}")
        return Job.from_dict(json.loads(raw)) if raw else None

    async def all(self) -> list[Job]:
        ids = await self._redis.smembers("jobs:all")
        jobs: list[Job] = []
        for job_id in ids:
            raw = await self._redis.get(f"job:{job_id}")
            if raw:
                jobs.append(Job.from_dict(json.loads(raw)))
        return jobs


def create_registry() -> JobRegistry:
    """Factory — reads `JOB_REGISTRY` (memory|redis) from env, default memory."""
    backend = os.environ.get("JOB_REGISTRY", "memory").strip().lower()
    if backend == "redis":
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        return RedisJobRegistry.from_url(url)
    return InMemoryJobRegistry()
