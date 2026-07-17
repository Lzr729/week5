from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class MemberInfo:
    name: str
    size_bytes: int
    sha256: str


class SafeArchive:
    """Read a ZIP package without extracting it to the filesystem."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self._zip = zipfile.ZipFile(self.path)
        self._members = [item for item in self._zip.infolist() if not item.is_dir()]
        unsafe = [item.filename for item in self._members if _unsafe_name(item.filename)]
        if unsafe:
            raise ValueError(f"Unsafe archive member names: {unsafe}")

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> "SafeArchive":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    @property
    def file_names(self) -> list[str]:
        return [item.filename for item in self._members]

    def find(self, suffix: str) -> str:
        normalized = suffix.replace("\\", "/").lstrip("/")
        matches = [name for name in self.file_names if name == normalized or name.endswith("/" + normalized)]
        if not matches and "/" not in normalized:
            matches = [name for name in self.file_names if PurePosixPath(name).name == normalized]
        if len(matches) != 1:
            raise KeyError(f"Expected one archive member matching {suffix!r}; found {matches}")
        return matches[0]

    def read_bytes(self, suffix: str) -> bytes:
        return self._zip.read(self.find(suffix))

    def read_text(self, suffix: str, *, encoding: str = "utf-8") -> str:
        return self.read_bytes(suffix).decode(encoding)

    def read_json(self, suffix: str) -> dict[str, Any]:
        value = json.loads(self.read_text(suffix, encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError(f"{suffix} must contain a JSON object")
        return value

    def read_csv(self, suffix: str) -> list[dict[str, Any]]:
        text = self.read_text(suffix, encoding="utf-8-sig")
        return [dict(row) for row in csv.DictReader(io.StringIO(text))]

    def member_info(self, suffix: str) -> MemberInfo:
        name = self.find(suffix)
        data = self._zip.read(name)
        return MemberInfo(name=name, size_bytes=len(data), sha256=sha256_bytes(data))

    def verify_sha256s(self, suffix: str) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for raw_line in self.read_text(suffix, encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            digest, relative = line.split(None, 1)
            relative = relative.strip().lstrip("*")
            try:
                info = self.member_info(relative)
                ok = info.sha256 == digest
                entries.append({
                    "declared_path": relative,
                    "archive_member": info.name,
                    "declared_sha256": digest,
                    "observed_sha256": info.sha256,
                    "size_bytes": info.size_bytes,
                    "result": "PASS" if ok else "FAIL",
                })
                if not ok:
                    issues.append({"type": "HASH_MISMATCH", "path": relative})
            except KeyError as exc:
                entries.append({
                    "declared_path": relative,
                    "archive_member": None,
                    "declared_sha256": digest,
                    "observed_sha256": None,
                    "size_bytes": None,
                    "result": "FAIL",
                })
                issues.append({"type": "DECLARED_FILE_MISSING", "path": relative, "detail": str(exc)})
        return {"result": "PASS" if not issues else "FAIL", "entries": entries, "issues": issues}

    def verify_manifest_files(self, manifest_suffix: str, *, files_key: str = "files") -> dict[str, Any]:
        manifest = self.read_json(manifest_suffix)
        declared = manifest.get(files_key)
        if not isinstance(declared, list):
            return {"result": "NOT_APPLICABLE", "entries": [], "issues": [], "manifest": manifest}
        entries: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for item in declared:
            if not isinstance(item, dict) or not item.get("path"):
                issues.append({"type": "INVALID_MANIFEST_ENTRY", "entry": item})
                continue
            relative = str(item["path"])
            try:
                info = self.member_info(relative)
            except KeyError as exc:
                entries.append({"declared_path": relative, "archive_member": None, "result": "FAIL"})
                issues.append({"type": "DECLARED_FILE_MISSING", "path": relative, "detail": str(exc)})
                continue
            expected_hash = item.get("sha256")
            expected_size = item.get("size_bytes")
            hash_ok = expected_hash in (None, "") or str(expected_hash) == info.sha256
            size_ok = expected_size in (None, "") or int(expected_size) == info.size_bytes
            ok = hash_ok and size_ok
            entries.append({
                "declared_path": relative,
                "archive_member": info.name,
                "declared_sha256": expected_hash,
                "observed_sha256": info.sha256,
                "declared_size_bytes": expected_size,
                "observed_size_bytes": info.size_bytes,
                "result": "PASS" if ok else "FAIL",
            })
            if not hash_ok:
                issues.append({"type": "HASH_MISMATCH", "path": relative})
            if not size_ok:
                issues.append({"type": "SIZE_MISMATCH", "path": relative})
        return {"result": "PASS" if not issues else "FAIL", "entries": entries, "issues": issues, "manifest": manifest}


def _unsafe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return name.startswith("/") or ".." in path.parts
