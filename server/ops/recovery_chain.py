"""Select a complete native recovery chain by metadata, never by filename or upload time."""
from datetime import datetime


def select_chain(candidates):
    """Candidates are (opaque reference, normalized jeb_header metadata) pairs."""
    if not candidates:
        raise ValueError('No verified world backup candidates')
    identities = {}
    for reference, metadata in candidates:
        key = (metadata['stream'], metadata['id'])
        if key in identities:
            raise ValueError('Duplicate recovery identity')
        created = datetime.fromisoformat(metadata['created_at'].replace('Z', '+00:00'))
        if created.tzinfo is None or metadata['kind'] not in ('full', 'differential'):
            raise ValueError('Invalid recovery metadata')
        identities[key] = (reference, metadata, created)
    streams = {m['stream'] for _, m in candidates}
    if len(streams) != 1:
        raise ValueError('Select one explicit world stream')
    latest = max(identities.values(), key=lambda row: row[2])
    reference, metadata, _ = latest
    if metadata['kind'] == 'full':
        if metadata.get('base_id'):
            raise ValueError('Full backup has a base')
        return [reference]
    base = identities.get((metadata['stream'], metadata.get('base_id')))
    if not base or base[1]['kind'] != 'full' or base[1].get('base_id') or base[2] > latest[2]:
        raise ValueError('Newest differential has no valid full base')
    return [base[0], reference]
