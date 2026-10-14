"""Read-only coverage report. No archive payload access, deletion or provider writes."""
import json
from pathlib import Path
import subprocess
from catalog import coverage


def main():
    result = subprocess.run(["rclone", "lsjson", "-R", "--files-only", "--hash",
                             "gdrive:Holy Lois Backups", "--tpslimit", "2"],
                            check=True, capture_output=True, text=True, timeout=180)
    listing = json.loads(result.stdout)
    if len(listing) > 100000:
        raise ValueError("Inventory exceeds bounded review size")
    receipts = []
    directory = Path("/var/lib/holylois/backup-inventory")
    if directory.is_symlink():
        raise ValueError("Receipt directory must not be a symlink")
    for path in directory.glob("*.json"):
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            raise ValueError("Unexpected receipt file")
        receipts.append(json.loads(path.read_text()))
    report = coverage(receipts, listing)
    print(json.dumps({**report["summary"], "inventory_complete": report["inventory_complete"],
                      "deletion_performed": False}, indent=2))


if __name__ == "__main__":
    main()
