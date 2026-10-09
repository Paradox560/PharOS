"""Read-only discovery of the team's indexed parent chunks."""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

from backend.errors import ProviderError
from backend.retrieval.normalize import stable_id


def normalize_asset(row: dict) -> dict:
    if not isinstance(row, dict):
        raise ProviderError('archive_schema', 'Indexed parent has an unsupported shape.')
    original = row.get('original_video')
    if not isinstance(original, str) or urlparse(original).scheme != 's3':
        raise ProviderError('archive_schema', 'Indexed parent is missing its original S3 URI.')
    metadata = row.get('metadata') if isinstance(row.get('metadata'), dict) else {}
    def field(name):
        return row.get(name) if row.get(name) is not None else metadata.get(name)
    timeline = row.get('timeline', [])
    if not isinstance(timeline, list):
        raise ProviderError('archive_schema', 'Archive timeline has an unsupported shape.')
    # No geocoding from a broad city label. Only explicit coordinates are eligible.
    lat, lon = field('latitude'), field('longitude')
    try:
        lat, lon = float(lat), float(lon)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            lat = lon = None
    except (ValueError, TypeError):
        lat = lon = None
    duration = row.get('duration_sec', row.get('chunk_duration_sec', row.get('duration', row.get('total_duration'))))
    if duration is None:
        values = []
        for item in timeline:
            if isinstance(item, dict):
                try:
                    value = float(item.get('end_sec', item.get('segment_end_sec', item.get('end_time', 0))) or 0)
                    if math.isfinite(value):
                        values.append(value)
                except (TypeError, ValueError):
                    pass
        duration = max(values, default=0)
    try:
        duration = max(0, float(duration or 0))
        if not math.isfinite(duration):
            duration = 0
    except (TypeError, ValueError):
        duration = 0
    asset_id = stable_id(original)
    source = row.get('preview_source') or row.get('source')
    if not source and timeline:
        source = timeline[0].get('source') if isinstance(timeline[0], dict) else None
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    return {
        'id': asset_id, 'name': row.get('filename') or unquote(original.rsplit('/', 1)[-1]),
        'camera_id': field('camera_id'), 'location': field('location') or 'Unlocated archive',
        'coordinate_precision': 'catalog' if lat is not None else 'unlocated',
        'lat': lat, 'lon': lon, 'source_uri': source, 'original_video': original,
        'duration_sec': duration, 'playback_url': f'/api/assets/{asset_id}/media',
        'capability': 'indexed_archive', 'timeline': timeline,
        'upstream_metadata': {key:field(key) for key in ('camera_id', 'capture_type', 'location', 'stream_id', 'chunk_index')},
        'indexed_segment_count': len(timeline), 'verified_indexed': True,
        'cosmos_model': row.get('cosmos_model'),
        'provenance': {'source_url': original, 'captured_at': field('captured_at'),
                       'processed_at': now, 'data_origin': 'archive', 'execution_mode': 'real_provider',
                       'freshness': 'unknown', 'notes': ['Indexed archive; retrieval time is not footage capture time.',
                         'Coordinates remain unlocated unless explicitly supplied by source metadata.']},
    }


class ArchiveAdapter:
    def __init__(self, client):
        self.client = client

    async def inventory(self, limit=24, offset=0):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100 or not isinstance(offset, int) or offset < 0:
            raise ProviderError('invalid_pagination', 'Use limit 1–100 and a non-negative offset.', 422)
        data = await self.client.request('GET', '/videos/explore', params={'scope':'all', 'limit':limit, 'offset':offset})
        if isinstance(data, list):
            rows, total = data, len(data)
        elif isinstance(data, dict):
            rows = next((data[k] for k in ('videos', 'chunks', 'items', 'results') if isinstance(data.get(k), list)), None)
            if rows is None:
                raise ProviderError('archive_schema', 'Explore returned no supported parent chunk list.')
            total = data.get('total', len(rows))
        else:
            raise ProviderError('archive_schema', 'Explore returned an unsupported response.')
        return {'assets': [normalize_asset(row) for row in rows], 'mode':'connected', 'status':'available', 'total':total}

    async def metadata(self):
        schema, config = await asyncio.gather(
            self.client.request('GET', '/metadata/schema'),
            self.client.request('GET', '/metadata/ingest-config'))
        if not isinstance(schema, dict) or not isinstance(schema.get('schema'), list):
            raise ProviderError('metadata_schema', 'Metadata schema did not contain filter definitions.')
        return {**schema, 'ingest_config':config}
