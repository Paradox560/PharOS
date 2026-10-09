from dataclasses import replace
import time

from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from backend.config import Settings


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_path=str(tmp_path/'state.sqlite'), output_dir=str(tmp_path/'runs'),
        source_cache_dir=str(tmp_path/'sources'), public_sources_enabled=False,
        ingress_url='', username='', password='', demo_enabled=True)
    with TestClient(create_app(settings)) as client:
        yield client


def test_demo_bootstrap_has_truthful_origins(client):
    response = client.get('/api/overview')
    assert response.status_code == 200
    data = response.json()
    assert data['mode'] == 'demo'
    assert data['cameras'] and all(x['coordinate_precision'] == 'catalog' for x in data['cameras'])
    assert all(x['snapshot_url'] is None for x in data['cameras'])
    assert data['assets'][0]['provenance']['data_origin'] == 'synthetic'
    assert data['incidents'][0]['road_id'] is None  # Do not attach illustration to NYC
    assert any(x['score'] is None for x in data['risk'])
    assert all(x['status'] != 'ready' for x in data['integrations'] if x['id'] in {'vss','cosmos','yolo','wandb'})


def test_search_and_analysis_are_explicit_fixtures(client):
    result = client.post('/api/search', json={'query':'lane obstruction'}).json()
    assert result['results'] and result['execution_mode'] == 'mock'
    assert 'not semantic' in result['engine']
    job = client.post('/api/analysis/jobs', json={'asset_id':'demo-traffic'}).json()
    for _ in range(100):
        job = client.get('/api/jobs/'+job['id']).json()
        if job['state'] == 'succeeded':
            break
        time.sleep(.01)
    assert job['state'] == 'succeeded'
    assert job['result']['tracks'] == []
    assert all(x['model'] == 'fixture geometry (not YOLO)' for x in job['result']['detections'])
    brief = client.post('/api/ask', json={'question':'What should I review?', 'asset_id':'demo-traffic'}).json()
    assert brief['execution_mode'] == 'mock' and 'demo-obstruction-span' in brief['evidence_ids']


def test_media_range_is_seekable_and_arbitrary_media_rejected(client):
    response = client.get('/api/assets/demo-traffic/media', headers={'Range':'bytes=0-99'})
    assert response.status_code == 206
    assert len(response.content) == 100
    assert response.headers['content-range'].startswith('bytes 0-99/')
    assert client.get('/api/assets/http%3A%2F%2F127.0.0.1/media').status_code == 404


def test_mutations_bounded_and_uploads_disabled(client):
    assert client.post('/api/clips').status_code == 403
    assert client.post('/api/reingest/jobs', json={'preview_id':'x', 'confirmed':True}).status_code == 403
    assert client.post('/api/reingest/preview', json={'asset_id':'demo-traffic','prompt':'road conditions'}).status_code == 422
    invalid = client.post('/api/simulations', json={'early_clearance_sec':500,'late_clearance_sec':400})
    assert invalid.status_code == 422 and invalid.json()['error']['code'] == 'invalid_request'
    assert client.post('/api/demo', headers={'origin':'https://evil.example'}).status_code == 403
    assert client.post('/api/search', content='x'*70000, headers={'content-type':'application/json'}).status_code == 413


def test_demo_seed_is_idempotent_and_does_not_reset_acknowledgement(client):
    client.post('/api/incidents/demo-obstruction/acknowledge')
    for _ in range(3):
        result = client.post('/api/demo').json()
    assert len(result['incidents']) == 1 and result['incidents'][0]['status'] == 'acknowledged'


def test_forecast_truthful_and_persisted(client):
    road_id = client.get('/api/roads').json()['roads'][0]['id']
    result = client.post('/api/forecasts', json={'road_id':road_id}).json()
    assert result['data_origin'] == 'synthetic'
    assert client.get('/api/forecasts/'+result['id']).json()['horizons'] == result['horizons']
    assert client.post('/api/forecasts',json={'road_id':road_id,'mode':'persistence'}).status_code in {422,503}


def test_workshop_prefix_preserved(tmp_path):
    settings = Settings(database_path=str(tmp_path/'state.db'),source_cache_dir=str(tmp_path/'src'),public_sources_enabled=False,
        api_base_path='/app',ingress_url='',username='',password='')
    with TestClient(create_app(settings)) as client:
        asset = client.get('/api/overview').json()['assets'][0]
        assert asset['playback_url'] == '/app/api/assets/demo-traffic/media'


def test_missing_access_never_silently_returns_demo_when_disabled(tmp_path):
    settings = Settings(database_path=str(tmp_path/'state.db'), source_cache_dir=str(tmp_path/'src'),public_sources_enabled=False,
        demo_enabled=False,ingress_url='',username='',password='')
    with TestClient(create_app(settings)) as client:
        response = client.get('/api/archive')
        assert response.status_code == 503 and response.json()['error']['code'] == 'vss_unconfigured'
        assert client.get('/api/overview').json()['assets'] == []
