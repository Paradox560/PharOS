import asyncio
import hashlib
import json
import threading
from uuid import uuid4

from backend.errors import ProviderError
from backend.models import utcnow

TERMINAL = {'succeeded', 'failed', 'cancelled'}


class JobManager:
    def __init__(self, store, concurrency=2, timeout=180):
        self.store = store
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout = timeout
        self.tasks = {}
        self.cancel_events = {}
        self.listeners = set()

    def emit(self, kind, data):
        for queue in tuple(self.listeners):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait({'event': kind, 'data': data})

    def update(self, id, **fields):
        def apply(job):
            if job['state'] in TERMINAL:
                return job
            job.update(fields, updated_at=utcnow())
            return job
        job = self.store.mutate('jobs', id, apply)
        if job:
            self.emit('job', job)
        return job

    async def submit(self, kind, inputs, work, idempotency_key=None):
        fingerprint = hashlib.sha256(json.dumps([kind, inputs], sort_keys=True).encode()).hexdigest()
        # No await before reservation: one event-loop owner creates job + idempotency record.
        if idempotency_key:
            old = self.store.find_request(f'{kind}:{idempotency_key}')
            if old:
                if old[0] != fingerprint:
                    raise ProviderError('idempotency_conflict', 'This request key was already used with different inputs.', 409)
                return self.store.get('jobs', old[1])
        active = sum(not task.done() for task in self.tasks.values())
        if active >= 10:
            raise ProviderError('queue_full', 'The work queue is full. Wait for a job to finish.', 429)
        id = f'job-{uuid4().hex[:16]}'
        now = utcnow()
        job = dict(id=id, kind=kind, state='queued', progress=0, created_at=now, updated_at=now, result=None, error=None, inputs=inputs)
        self.store.put('jobs', job)
        if idempotency_key:
            self.store.remember_request(f'{kind}:{idempotency_key}', fingerprint, id)
        self.cancel_events[id] = threading.Event()
        self.tasks[id] = asyncio.create_task(self._run(id, work))
        self.emit('job', job)
        return job

    async def _run(self, id, work):
        cancel = self.cancel_events[id]
        try:
            async with self.semaphore:
                if cancel.is_set():
                    return
                self.update(id, state='running', progress=.01)
                async with asyncio.timeout(self.timeout):
                    result = await work(id, cancel, lambda progress: self.update(id, progress=min(.99, max(0, float(progress)))))
                if not cancel.is_set():
                    self.update(id, state='succeeded', progress=1, result=result)
        except asyncio.CancelledError:
            cancel.set()
            self.update(id, state='cancelled', error={'code': 'cancelled', 'message': 'Job cancelled.'})
        except TimeoutError:
            cancel.set()
            self.update(id, state='failed', error={'code': 'timeout', 'message': 'Bounded job runtime exceeded; inspect remote state before retrying re-ingestion.'})
        except ProviderError as exc:
            self.update(id, state='failed', error={'code': exc.code, 'message': exc.message})
        except Exception:
            self.update(id, state='failed', error={'code': 'worker_failed', 'message': 'Worker failed. Check local diagnostics; provider details were redacted.'})

    def cancel(self, id):
        job = self.store.get('jobs', id)
        if job is None:
            raise ProviderError('job_not_found', 'Unknown job.', 404)
        if job['state'] in TERMINAL:
            return job
        self.cancel_events[id].set()
        # Shared upstream ingestion has no cancellation API. Do not falsely report it stopped.
        message = 'Local monitoring cancelled. Shared pipeline processing may continue; verify upstream before any retry.' if job['kind'] == 'reingest' else 'Cancellation requested; worker stops at its next bounded checkpoint.'
        job = self.update(id, state='cancelled', error={'code': 'cancelled', 'message': message})
        self.tasks[id].cancel()
        return job

    async def shutdown(self):
        for id, task in self.tasks.items():
            if not task.done():
                self.cancel_events[id].set()
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
