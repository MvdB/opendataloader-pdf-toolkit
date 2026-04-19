from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


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


class JobRegistry:
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
