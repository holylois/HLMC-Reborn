"""Private upload verification receipts. No expiry or deletion functions."""
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import uuid
import zipfile


def remote_md5(remote):
    values = {str(value).lower() for key, value in remote.get("Hashes", {}).items() if key.lower() == "md5"}
    if not values:
        return ""
    if len(values) != 1 or not re.fullmatch(r"[a-f0-9]{32}", next(iter(values))):
        raise ValueError("Invalid or conflicting remote checksum")
    return next(iter(values))


def safe_remote(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or path.as_posix() != value or any(ord(c) < 32 for c in value)
            or any(part in ("..", ".") for part in value.split("/"))):
        raise ValueError("Unsafe backup object path")
    if path.parts[0] not in ("world", "server", "maintenance", "legacy") or "\\" in value:
        raise ValueError("Unexpected backup object scope")
    return value


def hashes(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular backup file")
    before = path.stat()
    sha, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(block)
            md5.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("Backup changed during verification")
    return after.st_size, sha.hexdigest(), md5.hexdigest()


def remote_file(path, remote, remote_path):
    safe_remote(remote_path)
    size, sha, md5 = hashes(path)
    if remote.get("IsDir") is not False or remote.get("Name") != PurePosixPath(remote_path).name:
        raise ValueError("Remote object identity mismatch")
    if remote.get("Size") != size or remote_md5(remote) != md5:
        raise ValueError("Remote copy does not match local bytes")
    return {"path": remote_path, "size": size, "sha256": sha, "md5": md5}


def jeb_header(path):
    with zipfile.ZipFile(path) as archive:
        entries = [item for item in archive.infolist() if item.filename == "justenoughbackups.data"]
        if len(entries) != 1 or entries[0].file_size > 8_000_000:
            raise ValueError("Missing/duplicate/oversized backup metadata")
        with archive.open(entries[0]) as source:
            payload = source.read(8_000_001)
        if len(payload) > 8_000_000:
            raise ValueError("Metadata exceeds bounded read")
    data = json.loads(payload)
    manifest, status = data["manifest"], data["status"]
    if data.get("metadataVersion") != 1 or manifest.get("manifestVersion") != 2:
        raise ValueError("Unsupported backup metadata")
    kind, base = str(manifest.get("type")).lower(), manifest.get("baseBackupId")
    if kind not in ("full", "differential") or status.get("completed") is not True or status.get("brokenFiles"):
        raise ValueError("Unsupported or incomplete backup")
    if status.get("backupId") != manifest.get("id") or status.get("baseBackupId") != base:
        raise ValueError("Conflicting backup identity/dependency")
    if str(status.get("type")).lower() != kind or (kind == "full" and base) or (kind == "differential" and not base):
        raise ValueError("Conflicting backup type")
    if not isinstance(manifest.get("id"), str) or not manifest["id"]:
        raise ValueError("Missing backup ID")
    created = datetime.fromisoformat(manifest["createdAt"].replace("Z", "+00:00"))
    if created.tzinfo is None:
        raise ValueError("Backup date requires timezone")
    if not isinstance(manifest.get("worldDirectoryName"), str) or not manifest["worldDirectoryName"]:
        raise ValueError("Missing backup stream")
    opaque = lambda prefix, value: prefix + hashlib.sha256(value.encode()).hexdigest()[:32]
    return {"id": opaque("jeb-", manifest["id"]), "kind": kind,
            "base_id": opaque("jeb-", base) if base else None,
            "stream": opaque("world-", manifest["worldDirectoryName"]),
            "created_at": created.astimezone(timezone.utc).isoformat()}


def file_receipt(path, remote, remote_path, kind):
    path = Path(path)
    before = path.stat()
    member = remote_file(path, remote, remote_path)
    if kind == "world":
        normalized = jeb_header(path)
    elif kind == "server":
        normalized = {"id": "server-" + member["sha256"], "kind": "server", "base_id": None,
                      "stream": "server", "created_at": datetime.fromtimestamp(before.st_mtime, timezone.utc).isoformat()}
    else:
        raise ValueError("Unexpected file receipt kind")
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("Backup changed during receipt creation")
    return {"schema": 1, "verified_at": datetime.now(timezone.utc).isoformat(),
            "backup": {**normalized, "complete": True, "verified": True}, "members": [member]}


def tree_receipt(folder, remote_listing, remote_prefix):
    """Revalidate every member against Drive after the existing rclone check.

    This hashes only within the already approved backup job's source scope.
    Private member names stay in the root-only receipt, never a public report.
    """
    folder = Path(folder)
    prefix = safe_remote(remote_prefix)
    if not prefix.startswith("maintenance/") or len(PurePosixPath(prefix).parts) != 2 or folder.is_symlink():
        raise ValueError("Expected one complete maintenance set")
    remote = {row["Path"]: row for row in remote_listing}
    if len(remote) != len(remote_listing):
        raise ValueError("Duplicate remote member")
    files = sorted(folder.rglob("*"))
    if any(path.is_symlink() for path in files):
        raise ValueError("Symlink in maintenance set")
    files = [path for path in files if path.is_file()]
    if not files or {path.relative_to(folder).as_posix() for path in files} != set(remote):
        raise ValueError("Incomplete maintenance set")
    members = []
    newest = 0
    for path in files:
        relative = path.relative_to(folder).as_posix()
        members.append(remote_file(path, remote[relative], prefix + "/" + relative))
        newest = max(newest, path.stat().st_mtime)
    members.sort(key=lambda item: item["path"])
    fingerprint = hashlib.sha256(json.dumps(members, sort_keys=True).encode()).hexdigest()
    if {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()} != set(remote):
        raise ValueError("Maintenance set membership changed during verification")
    return {"schema": 1, "verified_at": datetime.now(timezone.utc).isoformat(), "backup": {
        "id": "maintenance-" + fingerprint, "kind": "maintenance", "stream": "maintenance",
        "created_at": datetime.fromtimestamp(newest, timezone.utc).isoformat(),
        "base_id": None, "whole_set": True, "complete": True, "verified": True}, "members": members}


def save_receipt(directory, receipt):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink():
        raise ValueError("Receipt directory must not be a symlink")
    os.chmod(directory, 0o700)
    key = hashlib.sha256(json.dumps(receipt["members"], sort_keys=True).encode()).hexdigest()
    target = directory / (key + ".json")
    if target.is_symlink():
        raise ValueError("Receipt must not be a symlink")
    temporary = directory / ("pending-" + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(receipt, output, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, target)
    return key
