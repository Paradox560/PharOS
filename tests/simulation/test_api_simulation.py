"""Actual SUMO through the public API, including responsiveness and terminal cancellation."""
import hashlib
import json
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from backend.config import Settings
from backend.models import SimulationRun, SimulationScenario
from backend.simulation.runner import NETWORK_DIR, _binary


@pytest.fixture
def simulation_api(tmp_path):
    settings = Settings(
        database_path=str(tmp_path / 'state.sqlite'),
        output_dir=str(tmp_path / 'runs'),
        source_cache_dir=str(tmp_path / 'sources'),
        public_sources_enabled=False,
        ingress_url='', username='', password='',
        wandb_api_key='', wandb_model='',
        demo_enabled=True,
        job_timeout_seconds=90,
    )
    # This suite requires the actual pinned simulator. Fail explicitly if it cannot run.
    _binary(settings)
    with TestClient(create_app(settings)) as client:
        yield client, settings


def wait_for_job(client, job_id, predicate, timeout=80):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f'/api/jobs/{job_id}')
        assert response.status_code == 200
        job = response.json()
        if predicate(job):
            return job
        if job['state'] in {'failed', 'cancelled'}:
            pytest.fail(f"Simulation ended unexpectedly: {job['state']} {job.get('error')}")
        time.sleep(.05)
    pytest.fail('The simulation API did not reach its bounded expected state.')


def test_actual_simulation_api_persists_run_and_seekable_media_stays_responsive(simulation_api):
    client, settings = simulation_api
    before = client.get('/api/assets/demo-traffic/media', headers={'Range': 'bytes=64-191'})
    assert before.status_code == 206 and len(before.content) == 128

    started = time.monotonic()
    submitted = client.post('/api/simulations', json={}, headers={'Idempotency-Key': 'api-default-comparison'})
    submit_latency = time.monotonic() - started
    assert submitted.status_code == 202
    job = submitted.json()
    assert job['state'] in {'queued', 'running'}
    # A synchronous five-second comparison here would violate the responsive job API.
    assert submit_latency < 2

    replay = client.post('/api/simulations', json={}, headers={'Idempotency-Key': 'api-default-comparison'})
    assert replay.status_code == 202 and replay.json()['id'] == job['id']
    assert client.get('/api/health').json()['status'] == 'ok'
    during = client.get('/api/assets/demo-traffic/media', headers={'Range': 'bytes=64-191'})
    assert during.status_code == 206
    assert during.content == before.content
    assert during.headers['content-range'] == before.headers['content-range']
    assert client.get('/api/jobs/' + job['id']).json()['state'] == 'running'

    completed = wait_for_job(client, job['id'], lambda value: value['state'] == 'succeeded')
    assert completed['progress'] == 1 and completed['error'] is None
    result = completed['result']
    # Validate the adapter/orchestrator handoff against the public canonical schema.
    SimulationRun.model_validate(result)
    assert result['job_id'] == job['id']
    assert result['scenario'] == SimulationScenario().model_dump()
    assert result['execution_mode'] == 'real_provider'
    assert result['data_origin'] == 'synthetic'
    assert result['engine'] == _binary(settings)[1]
    assert result['engine'].startswith('Eclipse SUMO sumo 1.27.1')
    assert 'playback' not in result  # The large replay is served separately.
    assert result['network_sha256'] == hashlib.sha256((NETWORK_DIR / 'nyc-demo-corridor.net.xml.gz').read_bytes()).hexdigest()

    stored = client.get('/api/simulations/' + result['id'])
    assert stored.status_code == 200 and stored.json() == result
    playback_response = client.get(result['playback_url'])
    assert playback_response.status_code == 200
    playback = playback_response.json()
    assert playback['network_id'] == 'nyc-demo-corridor'
    assert playback['data_origin'] == 'synthetic'
    assert playback['frame_interval_sec'] == 10
    assert [frame['time_sec'] for frame in playback['frames']] == list(range(0, 601, 10))
    assert any(frame['early'] for frame in playback['frames'])
    for frame in playback['frames']:
        for name in ('baseline', 'early', 'late'):
            for vehicle in frame[name]:
                assert -74 < vehicle['lon'] < -73.9
                assert 40.7 < vehicle['lat'] < 40.8
                assert vehicle['speed_kph'] >= 0
    for name in ('baseline', 'early', 'late'):
        metrics = result[name]
        assert metrics['scheduled_vehicles'] == 150
        assert metrics['throughput'] + metrics['unfinished_vehicles'] + metrics['insertion_backlog'] == 150
    assert result['comparison']['delay_saved_sec'] > 0

    run_directory = Path(settings.output_dir) / result['id']
    assert json.loads((run_directory / 'scenario.json').read_text()) == result['scenario']
    assert len(list(run_directory.glob('*/tripinfo.xml'))) == 3
    integrations = client.get('/api/integrations').json()['integrations']
    assert next(provider for provider in integrations if provider['id'] == 'sumo')['status'] == 'ready'
    after = client.get('/api/assets/demo-traffic/media', headers={'Range': 'bytes=64-191'})
    assert after.status_code == 206 and after.content == before.content

    # Idempotent submission does not create an additional worker/run directory.
    assert len(list(Path(settings.output_dir).iterdir())) == 1


def test_actual_simulation_api_cancellation_remains_terminal(simulation_api):
    client, settings = simulation_api
    submitted = client.post('/api/simulations', json={'duration_sec': 1800, 'demand_vph': 2400, 'seeds': [41, 42, 43]})
    assert submitted.status_code == 202
    job_id = submitted.json()['id']
    # Require simulation-driven progress to cancel after the real worker has started.
    running = wait_for_job(client, job_id, lambda value: value['state'] == 'running' and value['progress'] > .025)
    assert running['result'] is None
    cancelled = client.post('/api/jobs/' + job_id + '/cancel')
    assert cancelled.status_code == 200
    assert cancelled.json()['state'] == 'cancelled'
    assert cancelled.json()['error']['code'] == 'cancelled'

    observed = []
    for _ in range(20):
        current = client.get('/api/jobs/' + job_id).json()
        observed.append(current['state'])
        assert current['state'] == 'cancelled' and current['result'] is None
        time.sleep(.05)
    assert set(observed) == {'cancelled'}
    again = client.post('/api/jobs/' + job_id + '/cancel').json()
    assert again['state'] == 'cancelled'
    assert not list(Path(settings.output_dir).glob('*/result.json'))
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/assets/demo-traffic/media', headers={'Range': 'bytes=0-63'}).status_code == 206


def test_simulation_api_roads_keep_static_map_provenance(simulation_api):
    client, _ = simulation_api
    response = client.get('/api/roads')
    assert response.status_code == 200
    roads = response.json()['roads']
    manifest = json.loads((NETWORK_DIR / 'manifest.json').read_text())
    assert [road['id'] for road in roads] == ['osm-' + edge for edge in manifest['route_edges']]
    assert len(roads) == manifest['validation']['edge_count']
    for road in roads:
        provenance = road['provenance']
        assert provenance['captured_at'] is None
        assert provenance['freshness'] == 'unknown'
        assert provenance['source_url'].startswith('https://api.openstreetmap.org/')
        assert any('not a traffic sensor measurement' in note for note in provenance['notes'])
        assert road['geometry']['type'] == 'LineString'
        assert road['length_m'] > 0 and road['lanes'] > 0


def test_simulation_api_minimum_duration_and_duplicate_seed_validation(simulation_api):
    client, _ = simulation_api
    scenario = {'duration_sec': 300, 'blockage_start_sec': 30, 'early_clearance_sec': 100, 'late_clearance_sec': 220, 'seeds': [41, 42]}
    duplicate = client.post('/api/simulations', json=scenario | {'seeds': [42, 42]})
    assert duplicate.status_code == 422
    assert duplicate.json()['error']['code'] == 'invalid_request'
    short = client.post('/api/simulations', json=scenario | {'duration_sec': 299})
    assert short.status_code == 422

    accepted = client.post('/api/simulations', json=scenario)
    assert accepted.status_code == 202
    job = wait_for_job(client, accepted.json()['id'], lambda value: value['state'] == 'succeeded')
    result = job['result']
    assert result['scenario']['duration_sec'] == 300
    assert result['comparison']['seed_count'] == 2
    for name in ('baseline', 'early', 'late'):
        metrics = result[name]
        assert len(metrics['per_seed']) == 2
        completed_count = sum(row['throughput'] for row in metrics['per_seed'])
        completed_duration = sum(row['total_completed_travel_time_sec'] for row in metrics['per_seed'])
        expected = round(completed_duration / completed_count, 2) if completed_count else None
        assert metrics['mean_completed_travel_time_sec'] == expected
    playback = client.get(result['playback_url']).json()
    assert playback['frames'][-1]['time_sec'] == 300
