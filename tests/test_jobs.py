import asyncio
from types import SimpleNamespace

import pytest

from backend.errors import ProviderError
from backend.jobs import JobManager
from backend.store import Store


@pytest.mark.asyncio
async def test_idempotency_reuses_result_rejects_different_inputs():
    store = Store(':memory:')
    manager = JobManager(store)
    async def work(id, cancel, progress):
        return {'value': 7}
    a = await manager.submit('analysis', {'asset': 'a'}, work, 'key')
    b = await manager.submit('analysis', {'asset': 'a'}, work, 'key')
    assert a['id'] == b['id']
    with pytest.raises(ProviderError) as error:
        await manager.submit('analysis', {'asset': 'b'}, work, 'key')
    assert error.value.status_code == 409
    await manager.tasks[a['id']]
    assert store.get('jobs', a['id'])['result'] == {'value': 7}
    await manager.shutdown()
    store.close()


@pytest.mark.asyncio
async def test_cancel_is_terminal_even_if_worker_returns_late():
    store = Store(':memory:')
    manager = JobManager(store)
    ready = asyncio.Event()
    async def work(id, cancel, progress):
        ready.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return {'late': True}
    job = await manager.submit('simulation', {}, work)
    await ready.wait()
    manager.cancel(job['id'])
    await manager.tasks[job['id']]
    current = store.get('jobs', job['id'])
    assert current['state'] == 'cancelled' and current['result'] is None
    assert manager.cancel(job['id']) == current
    await manager.shutdown()
    store.close()


@pytest.mark.asyncio
async def test_remote_cancel_does_not_claim_pipeline_stopped():
    store = Store(':memory:')
    manager = JobManager(store)
    async def work(*args):
        await asyncio.sleep(30)
    job = await manager.submit('reingest', {}, work)
    current = manager.cancel(job['id'])
    assert 'may continue' in current['error']['message']
    await manager.shutdown()
    store.close()


def test_restart_preserves_state_and_marks_interrupted_jobs(tmp_path):
    path = str(tmp_path / 'state.db')
    store = Store(path)
    store.put('jobs', {'id': 'pending', 'kind': 'reingest', 'state': 'running'})
    store.put('incidents', {'id': 'i', 'status': 'acknowledged'})
    store.close()
    store = Store(path)
    store.fail_interrupted_jobs()
    assert store.get('jobs', 'pending')['error']['code'] == 'worker_restarted'
    assert store.get('incidents', 'i')['status'] == 'acknowledged'
    store.close()
