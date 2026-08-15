"""Hydrate and persist ephemeral project directories with MongoDB GridFS."""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tarfile
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from gridfs import GridFSBucket
from pymongo import ReturnDocument
from ulid import ULID

from novelvideo.ports.mongodb import (
    get_mongo_database,
    project_work_root,
    serverless_work_root,
    utc_now,
)


_PROJECT_PATH = re.compile(r"^/api/v1/projects/([^/]+)(?:/|$)")
_STATIC_PROJECT_PATH = re.compile(r"^/static/projects/([^/]+)(?:/|$)")
_MARKER_NAME = ".dramaclaw-workspace.json"
_LEASE_SECONDS = 15 * 60


def project_id_from_path(path: str) -> str | None:
    for pattern in (_PROJECT_PATH, _STATIC_PROJECT_PATH):
        match = pattern.match(path)
        if match:
            return match.group(1)
    return None


def _assert_project_root(root: Path) -> None:
    expected_parent = (serverless_work_root() / "projects").resolve()
    resolved = root.resolve()
    if resolved == expected_parent or not resolved.is_relative_to(expected_parent):
        raise RuntimeError(f"Unsafe serverless project root: {resolved}")


def _project_dirs(document: dict[str, Any]) -> tuple[Path, Path, Path]:
    return (
        Path(str(document["output_dir"])),
        Path(str(document["state_dir"])),
        Path(str(document["runtime_dir"])),
    )


def _ensure_project_dirs(document: dict[str, Any]) -> None:
    for directory in _project_dirs(document):
        directory.mkdir(parents=True, exist_ok=True)


def _marker_path(project_id: str) -> Path:
    return project_work_root(project_id) / _MARKER_NAME


def _read_marker(project_id: str) -> str | None:
    try:
        payload = json.loads(_marker_path(project_id).read_text(encoding="utf-8"))
        return str(payload.get("revision") or "") or None
    except (OSError, ValueError, TypeError):
        return None


def _write_marker(project_id: str, revision: str | None) -> None:
    marker = _marker_path(project_id)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"project_id": project_id, "revision": revision}, ensure_ascii=False),
        encoding="utf-8",
    )


def acquire_workspace_lease(project_id: str, timeout_seconds: float = 25.0) -> str:
    """Serialise project-directory mutations across function instances."""
    owner = secrets.token_urlsafe(18)
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    db = get_mongo_database()
    if db.projects.find_one({"_id": project_id}, {"_id": 1}) is None:
        raise KeyError(project_id)
    while True:
        now = utc_now()
        row = db.projects.find_one_and_update(
            {
                "_id": project_id,
                "$or": [
                    {"workspace_lease_until": {"$lt": now}},
                    {"workspace_lease_until": None},
                    {"workspace_lease_until": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "workspace_lease_owner": owner,
                    "workspace_lease_until": now + timedelta(seconds=_LEASE_SECONDS),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if row is not None:
            return owner
        if time.monotonic() >= deadline:
            raise TimeoutError("Project is busy; retry the request shortly")
        time.sleep(0.2)


def release_workspace_lease(project_id: str, owner: str) -> None:
    get_mongo_database().projects.update_one(
        {"_id": project_id, "workspace_lease_owner": owner},
        {
            "$unset": {
                "workspace_lease_owner": "",
                "workspace_lease_until": "",
            }
        },
    )


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != destination and not target.is_relative_to(destination):
            raise RuntimeError("Unsafe path in project workspace archive")
        if member.issym() or member.islnk():
            raise RuntimeError("Links are not allowed in project workspace archives")
    archive.extractall(destination)


def hydrate_workspace(project_id: str) -> bool:
    """Restore the latest workspace into /tmp. Returns False for unknown projects."""
    db = get_mongo_database()
    document = db.projects.find_one({"_id": project_id})
    if document is None:
        return False

    root = project_work_root(project_id)
    _assert_project_root(root)
    revision = str(document.get("workspace_revision") or "") or None
    if root.exists() and _read_marker(project_id) == revision:
        _ensure_project_dirs(document)
        return True

    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    file_id = document.get("workspace_file_id")
    if file_id is not None:
        scratch = serverless_work_root() / "scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(dir=scratch, suffix=".tar.gz", delete=False)
        archive_path = Path(handle.name)
        try:
            with handle:
                GridFSBucket(db, bucket_name="project_workspaces").download_to_stream(
                    file_id, handle
                )
            with tarfile.open(archive_path, mode="r:gz") as archive:
                _safe_extract(archive, root)
        finally:
            archive_path.unlink(missing_ok=True)

    _ensure_project_dirs(document)
    _write_marker(project_id, revision)
    return True


def persist_workspace(project_id: str, lease_owner: str | None = None) -> bool:
    """Archive a temporary workspace and atomically publish its new revision."""
    db = get_mongo_database()
    query: dict[str, Any] = {"_id": project_id}
    if lease_owner:
        query["workspace_lease_owner"] = lease_owner
    document = db.projects.find_one(query)
    if document is None:
        return False

    root = project_work_root(project_id)
    _assert_project_root(root)
    if not root.exists():
        return False
    _ensure_project_dirs(document)

    previous_revision = str(document.get("workspace_revision") or "") or None
    new_revision = str(ULID())
    _write_marker(project_id, new_revision)

    scratch = serverless_work_root() / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=scratch, suffix=".tar.gz", delete=False)
    archive_path = Path(handle.name)
    handle.close()
    new_file_id = None
    try:
        with tarfile.open(archive_path, mode="w:gz") as archive:
            for child in root.iterdir():
                archive.add(child, arcname=child.name, recursive=True)
        with archive_path.open("rb") as stream:
            new_file_id = GridFSBucket(db, bucket_name="project_workspaces").upload_from_stream(
                f"{project_id}-{new_revision}.tar.gz",
                stream,
                metadata={"project_id": project_id, "revision": new_revision},
            )

        publish_query: dict[str, Any] = {"_id": project_id}
        if lease_owner:
            publish_query["workspace_lease_owner"] = lease_owner
        result = db.projects.update_one(
            publish_query,
            {
                "$set": {
                    "workspace_file_id": new_file_id,
                    "workspace_revision": new_revision,
                    "updated_at": utc_now(),
                }
            },
        )
        if result.matched_count == 0:
            GridFSBucket(db, bucket_name="project_workspaces").delete(new_file_id)
            _write_marker(project_id, previous_revision)
            return False

        old_file_id = document.get("workspace_file_id")
        if old_file_id is not None and old_file_id != new_file_id:
            try:
                GridFSBucket(db, bucket_name="project_workspaces").delete(old_file_id)
            except Exception:
                pass
        return True
    except Exception:
        if new_file_id is not None:
            try:
                GridFSBucket(db, bucket_name="project_workspaces").delete(new_file_id)
            except Exception:
                pass
        _write_marker(project_id, previous_revision)
        raise
    finally:
        archive_path.unlink(missing_ok=True)


def delete_workspace(project_id: str) -> None:
    db = get_mongo_database()
    document = db.projects.find_one({"_id": project_id})
    if document and document.get("workspace_file_id") is not None:
        try:
            GridFSBucket(db, bucket_name="project_workspaces").delete(
                document["workspace_file_id"]
            )
        except Exception:
            pass
    root = project_work_root(project_id)
    _assert_project_root(root)
    if root.exists():
        shutil.rmtree(root)


def is_mongodb_backend() -> bool:
    return bool(os.environ.get("MONGODB_URI", "").strip())


__all__ = [
    "acquire_workspace_lease",
    "delete_workspace",
    "hydrate_workspace",
    "is_mongodb_backend",
    "persist_workspace",
    "project_id_from_path",
    "release_workspace_lease",
]
