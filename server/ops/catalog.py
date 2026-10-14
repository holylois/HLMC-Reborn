"""Compare private receipts with provider metadata. Never schedules or performs expiry."""
import json
from backup_receipts import remote_md5


def coverage(receipts, remote_listing):
    remote = {row["Path"]: row for row in remote_listing}
    if len(remote) != len(remote_listing):
        raise ValueError("Duplicate provider paths require review")
    covered = set()
    valid, stale = [], 0
    for receipt in receipts:
        if receipt.get("schema") != 1 or not receipt.get("members"):
            raise ValueError("Invalid receipt")
        members = receipt["members"]
        matched = True
        for member in members:
            item = remote.get(member["path"])
            if (not item or item.get("Size") != member["size"]
                    or remote_md5(item) != member["md5"]):
                matched = False
        if matched:
            paths = {member["path"] for member in members}
            if len(paths) != len(members) or covered.intersection(paths):
                raise ValueError("Overlapping receipt membership requires review")
            covered.update(paths)
            valid.append(receipt["backup"])
        else:
            stale += 1
    return {"summary": {"remote_objects": len(remote), "verified_objects": len(covered),
                         "unverified_objects": len(remote) - len(covered), "stale_receipts": stale,
                         "verified_recovery_units": len(valid), "expiry_enabled": False},
            "backups": valid, "inventory_complete": bool(remote) and stale == 0 and len(remote) == len(covered)}
