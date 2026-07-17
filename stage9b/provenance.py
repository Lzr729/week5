from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, BinaryIO


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        update_digest(stream, digest)
    return digest.hexdigest()


def update_digest(stream: BinaryIO, digest: Any) -> None:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)


def register_file(
    path: str | Path,
    *,
    artifact_id: str,
    source_stage: int | None,
    artifact_role: str,
    acceptance_status: str,
    covers_stages: list[int] | None = None,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    return {
        "artifact_id": artifact_id,
        "source_stage": source_stage,
        "covers_stages": covers_stages or ([] if source_stage is None else [source_stage]),
        "artifact_role": artifact_role,
        "file_name": file_path.name,
        "size_bytes": file_path.stat().st_size,
        "sha256": sha256_file(file_path),
        "availability": "AVAILABLE",
        "acceptance_status": acceptance_status,
        "verification": verification or {},
    }


def inspect_pdf(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    result: dict[str, Any] = {
        "tool": None,
        "page_count": None,
        "encrypted": None,
        "page_size": None,
        "result": "PARTIAL",
    }
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return result
    completed = subprocess.run([pdfinfo, str(file_path)], capture_output=True, text=True, check=False)
    result["tool"] = "pdfinfo"
    result["return_code"] = completed.returncode
    if completed.returncode != 0:
        result["stderr"] = completed.stderr.strip()
        return result
    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    page_text = fields.get("Pages")
    result["page_count"] = int(page_text) if page_text and page_text.isdigit() else None
    result["encrypted"] = fields.get("Encrypted")
    result["page_size"] = fields.get("Page size")
    result["pdf_version"] = fields.get("PDF version")
    result["result"] = "PASS" if result["page_count"] is not None else "PARTIAL"
    return result
