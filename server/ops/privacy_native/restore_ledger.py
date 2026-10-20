"""Shared identity/path helpers only. The historical SQLite pilot ledger is deliberately excluded."""
from datetime import datetime,timezone
import hashlib,json,uuid
from pathlib import Path

STORES=frozenset(('profiles','holylois','authentication','claims','homes','economy','public-exports','discord','private-recovery','world-ownership'))
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def stamp(value):
    when=datetime.fromisoformat(value.replace('Z','+00:00'))
    if when.tzinfo is None:raise ValueError('Timezone required')
    return when.astimezone(timezone.utc).isoformat()
def uuid_text(value):
    parsed=str(uuid.UUID(value))
    if parsed!=value:raise ValueError('Canonical UUID required')
    return parsed

def real(path):
    path=Path(path).absolute()
    if path.resolve()!=path:raise ValueError('Symlink or noncanonical private path')
    return path
