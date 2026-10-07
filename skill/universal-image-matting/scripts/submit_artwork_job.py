#!/usr/bin/env python3
"""Submit an artwork job to the async image-processing service."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def multipart(fields: dict[str, str], files: list[tuple[str, str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f"----artwork-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"])
    for file_field, file_name, content, media_type in files:
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'.encode(),
            f"Content-Type: {media_type}\r\n\r\n".encode(), content, b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def request(url: str, *, method: str = "GET", data: bytes | None = None, content_type: str | None = None, token: str | None = None) -> tuple[int, bytes]:
    headers = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--core-only", action="store_true", help="Explicitly stop after deterministic core artifacts; do not claim a complete PSD workflow")
    args = parser.parse_args()
    base = os.environ.get("ARTWORK_SERVICE_URL", "http://127.0.0.1:8000").rstrip("/")
    token = os.environ.get("ARTWORK_SERVICE_TOKEN")
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    files = [("source", args.source.name, args.source.read_bytes(), "application/octet-stream")]
    payload, content_type = multipart(
        {"policy_json": json.dumps(policy, ensure_ascii=False), "manifest_json": json.dumps({"client": "universal-image-matting-skill"})},
        files,
    )
    status, raw = request(f"{base}/v1/jobs", method="POST", data=payload, content_type=content_type, token=token)
    if status != 202:
        print(raw.decode("utf-8", errors="replace"), file=sys.stderr)
        return 4
    job_id = json.loads(raw)["job_id"]
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        status, raw = request(f"{base}/v1/jobs/{urllib.parse.quote(job_id)}", token=token)
        if status != 200:
            print(raw.decode("utf-8", errors="replace"), file=sys.stderr)
            return 4
        body = json.loads(raw)
        report = body.get("report") or {}
        psd_pending = report.get("psd_export_status") == "pending"
        if body["status"] in {"passed", "review_required", "refused", "failed"} or (psd_pending and args.core_only):
            break
        time.sleep(0.5)
    else:
        print("job polling timed out", file=sys.stderr)
        return 4

    terminal = body["status"]
    if terminal == "failed":
        print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
        return 4
    status, raw = request(f"{base}/v1/jobs/{urllib.parse.quote(job_id)}/artifacts", token=token)
    if status != 200:
        print(raw.decode("utf-8", errors="replace"), file=sys.stderr)
        return 4
    args.out.mkdir(parents=True, exist_ok=True)
    for artifact in json.loads(raw)["artifacts"]:
        artifact_status, file_bytes = request(f"{base}{artifact['download_url']}", token=token)
        if artifact_status != 200:
            print(f"failed to download {artifact['name']}", file=sys.stderr)
            return 4
        (args.out / artifact["name"]).write_bytes(file_bytes)
    print(json.dumps({
        "job_id": job_id,
        "status": terminal,
        "psd_export_status": (body.get("report") or {}).get("psd_export_status", "unknown"),
        "output": str(args.out),
    }, ensure_ascii=False))
    return {"passed": 0, "review_required": 2, "refused": 3, "running": 2}.get(terminal, 4)


if __name__ == "__main__":
    raise SystemExit(main())
