"""Nightly off-site copy of Holy Lois backups to the owner's Google Drive (rclone remote "gdrive").

- world/:  the newest Just Enough Backups full archive and the newest differential after it, uploaded only
           when they are new. JEB makes backups only while players are online, so no play means no upload.
- server/: a small archive of configs, permissions, login data, claims settings and mods, uploaded only
           when its content changed.
- maintenance/: complete release backups from /opt/minecraft-backups/maintenance. Each folder is uploaded, checked
           against Drive's checksums and only then deleted from the VM (owner decision 2026-10-04: backups live
           on Google Drive, not on the server disk).
- Capacity: report remote usage without deleting remote recovery copies. Removing old copies requires
  a separately reviewed complete recovery-set proposal and explicit owner approval.

The owner creates the remote once with `sudo rclone config` (Google Drive, scope "drive.file"), so no
Google credentials pass through anyone else. Without the remote the job exits quietly.
"""
import hashlib, io, json, os, subprocess, sys, tarfile, time
from pathlib import Path
from backup_receipts import file_receipt, tree_receipt, save_receipt

REMOTE = "gdrive:Holy Lois Backups"
ROOT = Path("/opt/minecraft")
JEB = ROOT / "backups" / "world"
STATE = Path("/var/lib/holylois/offsite-backup.json")
MAINTENANCE = Path("/opt/minecraft-backups/maintenance")
CAP_BYTES = 500 * 1024**3
RECEIPTS = Path("/var/lib/holylois/backup-inventory")
SERVER_PATHS = ["config", "EasyAuth", "mods", "defaultconfigs", "server.properties", "ops.json", "whitelist.json",
                "banned-players.json", "banned-ips.json", "usercache.json", "eula.txt", "server-icon.png"]
ALERT = "/usr/local/lib/holylois/discord-alert.py"


def rclone(*args, capture=False):
    # 256M chunks: rclone's shared Google client is rate limited, so fewer requests per file
    return subprocess.run(["rclone", *args, "--drive-chunk-size", "256M", "--tpslimit", "4"], check=True, capture_output=capture, text=True)


def remote_ready():
    try:
        return "gdrive:" in rclone("listremotes", capture=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return False


def settled(path):
    # JEB writes archives in place; skip anything touched in the last two minutes.
    return time.time() - path.stat().st_mtime > 120


def newest_world_files():
    fulls = sorted((p for p in JEB.glob("full-*.zip") if settled(p)), key=lambda p: p.stat().st_mtime)
    if not fulls:
        return []
    full = fulls[-1]
    diffs = sorted((p for p in JEB.glob("differential-*.zip") if settled(p) and p.stat().st_mtime > full.stat().st_mtime),
                   key=lambda p: p.stat().st_mtime)
    return [full] + diffs[-1:]


def server_archive():
    """Deterministic content fingerprint first; build the tarball only when something changed."""
    digest, files = hashlib.sha256(), []
    for entry in SERVER_PATHS:
        base = ROOT / entry
        for path in sorted([base] if base.is_file() else base.rglob("*") if base.is_dir() else []):
            if path.is_file() and not path.is_symlink():
                files.append(path)
                digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest(), files


def upload_server(files, stamp):
    name = f"server-{stamp}.tar.gz"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path in files:
            tar.add(path, arcname=str(path.relative_to(ROOT)))
    temporary = Path("/var/lib/holylois") / name
    temporary.write_bytes(buffer.getvalue())
    temporary.chmod(0o600)
    try:
        rclone("copyto", str(temporary), f"{REMOTE}/server/{name}")
        remote = json.loads(rclone("lsjson", f"{REMOTE}/server/{name}", "--stat", "--hash", capture=True).stdout)
        save_receipt(RECEIPTS, file_receipt(temporary, remote, "server/" + name, "server"))
    finally:
        temporary.unlink(missing_ok=True)
    return name


def offload_maintenance():
    """Upload finished release backups, verify them on Drive, then free the VM disk. A folder still being written
    (anything modified in the last 10 minutes) or one without a receipt (deploy not finished) waits for the next run."""
    moved = []
    for folder in sorted(p for p in MAINTENANCE.iterdir() if p.is_dir()) if MAINTENANCE.is_dir() else []:
        newest = max((f.stat().st_mtime for f in folder.rglob("*") if f.is_file()), default=0)
        if time.time() - newest < 600 or not (folder / "receipt.json").exists() and folder.name.startswith("release"):
            continue
        target = f"{REMOTE}/maintenance/{folder.name}"
        rclone("copy", str(folder), target)
        rclone("check", str(folder), target, "--one-way")  # sizes and MD5 against Drive; raises on any mismatch
        listing = json.loads(rclone("lsjson", "-R", "--files-only", "--hash", target, capture=True).stdout)
        save_receipt(RECEIPTS, tree_receipt(folder, listing, "maintenance/" + folder.name))
        subprocess.run(["rm", "-rf", "--", str(folder)], check=True)
        moved.append(folder.name)
    return moved


def enforce_cap():
    """Compatibility name: measure capacity only; never prune remote backup files.

    File-count pruning can split maintenance folders or full/differential chains.
    The existing storage watch requests approval for whole recovery sets instead.
    """
    listing = json.loads(rclone("lsjson", "-R", "--files-only", REMOTE, capture=True).stdout or "[]")
    if not isinstance(listing, list) or len(listing) > 100000:
        raise ValueError("Unexpected capacity inventory")
    paths = set()
    for item in listing:
        path, size = item.get("Path"), item.get("Size")
        if (not isinstance(path, str) or not path or path in paths
                or type(size) is not int or size < 0 or item.get("IsDir") is not False):
            raise ValueError("Invalid capacity metadata")
        paths.add(path)
    return sum(item["Size"] for item in listing), []


def main():
    if not remote_ready():
        print("Google Drive remote 'gdrive' is not configured yet; nothing uploaded.")
        return
    state = json.loads(STATE.read_text()) if STATE.exists() else {"uploaded": [], "server_hash": None}
    uploaded = []
    for path in newest_world_files():
        if path.name not in state["uploaded"]:
            rclone("copyto", str(path), f"{REMOTE}/world/{path.name}")
            state["uploaded"] = (state["uploaded"] + [path.name])[-200:]
            uploaded.append(path.name)
        remote = json.loads(rclone("lsjson", f"{REMOTE}/world/{path.name}", "--stat", "--hash", capture=True).stdout)
        save_receipt(RECEIPTS, file_receipt(path, remote, "world/" + path.name, "world"))
    fingerprint, files = server_archive()
    if fingerprint != state.get("server_hash"):
        uploaded.append(upload_server(files, time.strftime("%Y-%m-%d_%H-%M", time.gmtime())))
        state["server_hash"] = fingerprint
    uploaded += [f"maintenance/{name}" for name in offload_maintenance()]
    total, removed = enforce_cap()
    state.update(last_run=time.time(), remote_bytes=total)
    STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))
    print(json.dumps({"uploaded": uploaded or "nothing new", "removed_for_cap": removed, "remote_gb": round(total / 1024**3, 2),
                      "capacity_warning": total >= 450 * 1024**3,
                      "capacity_limit_reached": total >= CAP_BYTES,
                      "remote_cleanup_requires_approval": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if os.path.exists(ALERT):
            subprocess.run([sys.executable, ALERT, "message", f"Off-site backup to Google Drive failed: {error}"], check=False)
        raise
