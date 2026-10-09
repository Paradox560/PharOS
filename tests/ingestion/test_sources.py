import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from backend.data_adapters.public import PublicSources, normalize_speed, normalize_reports, normalize_weather, source_time
from backend.errors import ProviderError
from backend.ingestion.archive import ArchiveAdapter, normalize_asset
from backend.ingestion.reingestion import ReingestionAdapter
from backend.models import Camera, MediaAsset


def run(awaitable):
    return asyncio.run(awaitable)


def settings(tmp_path, **overrides):
    return SimpleNamespace(source_cache_dir=str(tmp_path),source_cache_ttl_seconds=300,
        public_sources_enabled=overrides.get('public_sources_enabled',True),
        nyc_camera_snapshots_enabled=overrides.get('nyc_camera_snapshots_enabled',False))


def test_verified_cold_start_has_no_fabricated_capture_times(tmp_path):
    adapter = PublicSources(settings(tmp_path,public_sources_enabled=False))
    cameras = run(adapter.cameras())['cameras']
    assert len(cameras)>=10
    assert all(c['coordinate_precision']=='catalog' and c['lat'] and c['lon'] for c in cameras)
    assert all(c['provenance']['captured_at'] is None and c['snapshot_url'] is None for c in cameras)
    for camera in cameras: Camera.model_validate(camera)


def test_floating_nyc_timestamp_is_converted_to_utc():
    assert source_time('2026-10-09T09:36:07.000',local=True)=='2026-10-09T13:36:07Z'
    assert source_time('2026-10-09T09:36:07.000') is None


def test_speed_missing_units_and_truncated_geometry_are_truthful():
    rows=normalize_speed([{'link_id':'x','speed':'35.2','travel_time':'123','data_as_of':'2020-01-01T10:00:00',
                           'link_points':'40.71,-74.0 40.72,-73.99 40.7,-'}])
    assert rows[0]['speed_kph'] is None
    assert rows[0]['speed_native']==35.2
    assert rows[0]['provenance']['freshness']=='stale'
    assert rows[0]['geometry']['coordinates']==[[-74.0,40.71],[-73.99,40.72]]


def test_reports_do_not_invent_coordinates_or_observations():
    report=normalize_reports([{'unique_key':'123','created_date':'2026-10-09T10:00:00','complaint_type':'Street Condition'}])[0]
    assert report['lat'] is None and report['lon'] is None
    assert 'Unverified service request' in report['provenance']['notes'][0]


def test_weather_units_must_match():
    value=normalize_weather({'properties':{'timestamp':'2026-10-09T14:51:00Z','visibility':{'value':3,'unitCode':'wmoUnit:mi'}}})[0]
    assert value['visibility_m'] is None


def test_refresh_is_bounded_and_failures_independent(tmp_path):
    calls=[]
    def handler(request):
        calls.append(str(request.url))
        if 'graphql' in str(request.url):
            return httpx.Response(200,json={'data':{'cameras':[{'id':'x','name':'Test','latitude':40.7,'longitude':-74,'isOnline':True}]}})
        if 'weather.gov' in str(request.url):
            return httpx.Response(200,json={'properties':{'timestamp':'2020-01-01T00:00:00Z'}})
        return httpx.Response(503,json={'error':'unavailable'})
    async def scenario():
        adapter=PublicSources(settings(tmp_path),httpx.MockTransport(handler))
        a,b=await asyncio.gather(adapter.refresh(),adapter.refresh())
        assert a['cameras'][0]['id']=='x'
        assert any(s['status']=='unavailable' for s in a['sources'])
        assert any(r['kind']=='weather' for r in a['records'])
        assert len(calls)==4
        await adapter.close()
    run(scenario())


def test_snapshot_access_gated_and_url_cannot_be_supplied(tmp_path):
    adapter=PublicSources(settings(tmp_path,public_sources_enabled=False))
    with pytest.raises(ProviderError) as error:
        run(adapter.snapshot({'id':'http://localhost/secret'}))
    assert error.value.code=='camera_agreement_required'
    enabled=PublicSources(settings(tmp_path,nyc_camera_snapshots_enabled=True))
    with pytest.raises(ProviderError) as error:
        run(enabled.snapshot({'id':'http://localhost/secret'}))
    assert error.value.code=='unknown_camera'


def asset():
    return normalize_asset({'original_video':'s3://team-8-chunks/team-8/clip.mp4','preview_source':'s3://team-8-segments/clip_0.mp4',
        'location':'nashville','camera_id':'i24_cam-1','capture_type':'fixed',
        'timeline':[{'source':'s3://team-8-segments/clip_0.mp4','start_time':0,'end_time':30}]})


class Client:
    def __init__(self): self.calls=[]
    async def request(self,method,path,**kwargs):
        self.calls.append((method,path,kwargs))
        if method=='POST': return {'job_id':'job-1'}
        return {'chunks':[{'original_video':asset()['original_video'],'location':'nashville'}],'total':1}


def test_archive_parent_is_unlocated_without_catalog_coordinates():
    row=asset()
    assert row['lat'] is None and row['coordinate_precision']=='unlocated'
    assert row['source_uri'].endswith('clip_0.mp4')
    assert row['original_video'].endswith('/clip.mp4')
    assert row['duration_sec']==30
    assert row['provenance']['data_origin']=='archive'
    MediaAsset.model_validate(row)
    result=run(ArchiveAdapter(Client()).inventory(12,0))
    assert result['assets'][0]['location']=='nashville'


def test_malformed_timing_does_not_create_non_json_values():
    row=normalize_asset({'original_video':'s3://chunks/a.mp4','duration':'Infinity',
                         'timeline':[{'end_time':'not-a-time'}]})
    assert row['duration_sec']==0
    with pytest.raises(ProviderError): normalize_asset(None)


def test_reingest_preserves_metadata_exactly_and_deduplicates():
    client=Client(); adapter=ReingestionAdapter(client)
    async def scenario():
        preview=await adapter.preview(asset(),'Describe visible obstruction.',True)
        first=await adapter.submit(preview); second=await adapter.submit(preview)
        assert first==second
        assert len(client.calls)==1
        assert client.calls[0][2]['json']=={'original_video':asset()['original_video'],'chunk_count':1,
                                         'custom_prompt':'Describe visible obstruction.'}
        assert preview['metadata']['location']=='nashville'
    run(scenario())


def test_reingest_rejects_tampered_and_synthetic_target():
    adapter=ReingestionAdapter(Client())
    async def scenario():
        preview=await adapter.preview(asset(),'Describe.',True)
        preview['target']='s3://different-team/other.mp4'
        with pytest.raises(ProviderError) as error: await adapter.submit(preview)
        assert error.value.code=='invalid_preview'
        fake=asset(); fake['provenance']['execution_mode']='mock'
        with pytest.raises(ProviderError): await adapter.preview(fake,'Describe.',True)
    run(scenario())


def test_uncertain_reingest_is_not_automatically_retried():
    class Failing(Client):
        async def request(self,*args,**kwargs): raise ProviderError('timeout','Provider timeout')
    adapter=ReingestionAdapter(Failing())
    async def scenario():
        preview=await adapter.preview(asset(),'Describe.',True)
        with pytest.raises(ProviderError): await adapter.submit(preview)
        with pytest.raises(ProviderError) as error: await adapter.submit(preview)
        assert error.value.code=='submission_uncertain'
    run(scenario())
