from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass(frozen=True, slots=True)
class StoredJob:
    job_id: str
    idempotency_key: str | None
    source_hash: str
    status: str
    progress: int
    payload: dict[str, Any]
    created_at: float
    updated_at: float
    error: dict[str, str] | None = None


class FileJobStore:
    def __init__(self, root: Path, ttl_seconds: int = 86_400) -> None:
        self.root = root
        self.ttl_seconds = ttl_seconds
        self._lock = Lock()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise ValueError("invalid job id")
        return self.root / job_id / "job.json"

    def create(self, job_id: str, source_hash: str, idempotency_key: str | None, payload: dict[str, Any]) -> StoredJob:
        now = time.time()
        record = StoredJob(job_id, idempotency_key, source_hash, "accepted", 0, payload, now, now)
        with self._lock:
            self._path(job_id).parent.mkdir(parents=True, exist_ok=False)
            self._write(record)
        return record

    def find_idempotent(self, key: str, fingerprint: str) -> StoredJob | None:
        for path in self.root.glob("*/job.json"):
            record = self.get(path.parent.name)
            if record and record.idempotency_key == key:
                if record.payload.get("_idempotency_fingerprint") != fingerprint:
                    raise ValueError("idempotency key already belongs to a different request")
                return record
        return None

    def get(self, job_id: str) -> StoredJob | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        return StoredJob(**json.loads(path.read_text(encoding="utf-8")))

    def update(self, job_id: str, **changes: Any) -> StoredJob:
        current = self.get(job_id)
        if current is None:
            raise KeyError(job_id)
        record = StoredJob(**{**asdict(current), **changes, "updated_at": time.time()})
        with self._lock:
            self._write(record)
        return record

    def _write(self, record: StoredJob) -> None:
        destination = self._path(record.job_id)
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, destination)

    def job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise ValueError("invalid job id")
        path = self.root / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cleanup(self) -> int:
        cutoff = time.time() - self.ttl_seconds
        removed = 0
        for path in self.root.glob("*/job.json"):
            if path.stat().st_mtime < cutoff:
                shutil.rmtree(path.parent, ignore_errors=True)
                removed += 1
        return removed


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
