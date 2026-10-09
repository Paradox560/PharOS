"""Exact-preview, single-parent re-ingestion. The API owner supplies confirmation."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
import time
import uuid
from urllib.parse import urlparse

from backend.errors import ProviderError


ROAD_CONDITIONS_PROMPT = (
    'Describe only visible road conditions in this temporal clip. Identify potential lane '
    'obstructions, their location within the visible road, vehicles slowing or stopping, '
    'queue formation, and changes over time. State which frames/times support each claim. '
    'Distinguish a parked/stopped vehicle from motion that cannot be established. Note '
    'occlusion, limited viewpoint, and uncertainty. Do not infer a collision, cause, speed, '
    'identity, or exact geography without evidence. Give a concise searchable summary '
    'and the observed time span.'
)


class ReingestionAdapter:
    def __init__(self, client):
        self.client = client
        self._previews = {}
        self._submitted = {}

    async def preview(self, asset, prompt, keep_metadata=True):
        if keep_metadata is not True:
            raise ProviderError('metadata_override_disabled', 'This workflow preserves existing archive metadata.', 422)
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 800:
            raise ProviderError('invalid_prompt', 'Custom analysis prompt must contain 1–800 characters.', 422)
        original = asset.get('original_video')
        if (not asset.get('verified_indexed') or asset.get('capability') != 'indexed_archive'
                or asset.get('provenance', {}).get('execution_mode') != 'real_provider'
                or not isinstance(original, str) or urlparse(original).scheme != 's3'):
            raise ProviderError('unverified_target', 'Choose one parent chunk returned by the connected archive.', 422)
        now = time.monotonic()
        self._previews = {k:v for k,v in self._previews.items() if now - v[0] <= 600}
        result = {'preview_id':str(uuid.uuid4()), 'target':original, 'prompt':prompt,
                  'metadata':deepcopy(asset.get('upstream_metadata', {})), 'chunk_count':1,
                  'indexed_segment_count':asset.get('indexed_segment_count', len(asset.get('timeline', []))),
                  'requires_confirmation':True, 'keep_metadata':True,
                  'created_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}
        self._previews[result['preview_id']] = (now, deepcopy(result))
        return result

    async def submit(self, preview):
        preview_id = preview.get('preview_id') if isinstance(preview, dict) else None
        stored = self._previews.get(preview_id)
        if not stored or time.monotonic() - stored[0] > 600 or preview != stored[1]:
            raise ProviderError('invalid_preview', 'Preview is missing, modified, or expired; create and confirm a new preview.', 409)
        if preview_id in self._submitted:
            previous = self._submitted[preview_id]
            if previous is None:
                raise ProviderError('submission_uncertain', 'This request was already attempted. Check upstream jobs before another re-ingestion.', 409)
            return deepcopy(previous)
        # Never submit stream_id, metadata overrides, arbitrary source URLs, or multiple chunks.
        payload = {'original_video':preview['target'], 'chunk_count':1, 'custom_prompt':preview['prompt']}
        self._submitted[preview_id] = None
        result = await self.client.request('POST', '/dashboard/reingest', json=payload)
        if not isinstance(result, dict) or not (result.get('job_id') or result.get('id')):
            raise ProviderError('reingest_schema', 'Submission returned no job identifier; inspect upstream dashboard before retrying.')
        self._submitted[preview_id] = deepcopy(result)
        return result

    async def status(self, upstream_id):
        if not isinstance(upstream_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', upstream_id):
            raise ProviderError('invalid_job_id', 'Invalid upstream job identifier.', 422)
        return await self.client.request('GET', f'/dashboard/reingest/{upstream_id}')
