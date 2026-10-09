from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import secrets
from pathlib import Path
import time
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.config import ROOT, Settings
from backend.errors import ProviderError
from backend.models import (AskRequest, AnalysisRequest, ForecastRequest, ReingestPreviewRequest,
                            ReingestRequest, SearchRequest, SimulationScenario, utcnow)
from backend.store import Store
from backend.jobs import JobManager
from backend import fixtures
from backend.data_adapters import PublicSources
from backend.ingestion import ArchiveAdapter, ReingestionAdapter
from backend.retrieval import VSSClient, RetrievalAdapter
from backend.inference import OperationsAgent, diagnostics

load_dotenv(ROOT / '.env', override=False)


def create_app(settings: Settings | None = None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        if settings.require_auth and not settings.operator_password:
            raise RuntimeError('PHAROS_OPERATOR_PASSWORD is required when operator authentication is enabled.')
        state = app.state
        state.settings = settings
        state.store = Store(settings.database_path)
        state.store.fail_interrupted_jobs()
        state.jobs = JobManager(state.store, settings.max_concurrent_jobs, settings.job_timeout_seconds)
        state.client = VSSClient(settings)
        state.retrieval = RetrievalAdapter(state.client)
        state.archive = ArchiveAdapter(state.client)
        state.reingestion = ReingestionAdapter(state.client)
        state.operations = OperationsAgent(settings)
        state.sources = PublicSources(settings)
        state.demo = settings.demo_enabled and not settings.vss_configured
        state.context = {'sources': [], 'records': []}
        state.archive_total = 0
        from backend.simulation import get_roads
        state.roads = get_roads()
        state.providers = initial_providers(settings)
        if state.demo:
            fixtures.seed(state.store, state.roads)
        yield
        await state.jobs.shutdown()
        await asyncio.gather(state.client.close(), state.operations.close(), state.sources.close())
        state.store.close()

    app = FastAPI(title='PharOS', version='0.1.0', lifespan=lifespan, root_path=settings.api_base_path)

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return JSONResponse({'error': {'code': exc.code, 'message': exc.message}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        details = [{'field': '.'.join(str(x) for x in error['loc']), 'message': error['msg']} for error in exc.errors()]
        return JSONResponse({'error': {'code': 'invalid_request', 'message': 'Request validation failed.', 'details': details}}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        code = 'not_found' if exc.status_code == 404 else 'http_error'
        return JSONResponse({'error': {'code': code, 'message': str(exc.detail)}}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse({'error': {'code':'internal_error', 'message':'The application could not complete this request.'}}, status_code=500)

    @app.middleware('http')
    async def protect_request(request, call_next):
        if settings.require_auth and request.url.path not in {'/api/health', '/app/api/health'}:
            accepted = False
            try:
                scheme, encoded = request.headers.get('authorization', '').split(' ', 1)
                username, password = base64.b64decode(encoded, validate=True).decode('utf-8').split(':', 1)
                accepted = scheme.lower() == 'basic' and secrets.compare_digest(username.encode(), settings.operator_username.encode()) and secrets.compare_digest(password.encode(), settings.operator_password.encode())
            except (ValueError, UnicodeError):
                pass
            if not accepted:
                return JSONResponse({'error': {'code':'operator_auth_required', 'message':'Sign in to access this operator workspace.'}},status_code=401,
                                    headers={'WWW-Authenticate':'Basic realm="PharOS operator", charset="UTF-8"'})
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            origin = request.headers.get('origin')
            if origin:
                from urllib.parse import urlsplit
                if urlsplit(origin).netloc != request.headers.get('host'):
                    return JSONResponse({'error': {'code': 'origin_rejected', 'message': 'Cross-origin writes are disabled.'}}, status_code=403)
            try:
                too_big = int(request.headers.get('content-length', 0)) > 65536
            except ValueError:
                too_big = True
            if too_big:
                return JSONResponse({'error': {'code': 'request_too_large', 'message': 'Request body exceeds 64 KiB.'}}, status_code=413)
            collected = bytearray()
            async for chunk in request.stream():
                collected.extend(chunk)
                if len(collected) > 65536:
                    return JSONResponse({'error': {'code': 'request_too_large', 'message': 'Request body exceeds 64 KiB.'}}, status_code=413)
            request._body = bytes(collected)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def require(kind, id):
        item = app.state.store.get(kind, id)
        if item is None:
            raise ProviderError('not_found', f'Unknown {kind.replace("_", " ")} identifier.', 404)
        return item

    def activity(agent, message, mode='real_provider', evidence_ids=None, latency_ms=None):
        item = dict(id=f'activity-{uuid4().hex[:12]}', agent=agent, status='completed', message=message,
                    timestamp=utcnow(), evidence_ids=evidence_ids or [], execution_mode=mode, latency_ms=latency_ms)
        app.state.store.put('activity', item)
        app.state.jobs.emit('activity', item)

    def current_assets():
        return [asset for asset in app.state.store.list('assets') if (asset['provenance']['data_origin'] == 'synthetic') == app.state.demo]

    def current_incidents():
        return [incident for incident in app.state.store.list('incidents') if (incident['data_origin'] == 'synthetic') == app.state.demo]

    def current_risk():
        from backend.risk import score_roads
        observations = app.state.store.list('observations')
        if not app.state.demo:
            observations = [x for x in observations if x['provenance']['data_origin'] != 'synthetic']
        return score_roads(app.state.roads, observations)

    def record_context(records):
        from datetime import datetime, timedelta, timezone
        for record in records:
            if record.get('kind') == 'traffic_speed':
                app.state.store.put('sensor_history', record, insert_only=True)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, settings.history_retention_days))).isoformat().replace('+00:00', 'Z')
        app.state.store.prune('sensor_history', cutoff)

    def externalize(value):
        # Returned adapter URLs are internal. Prefix only app-owned URLs for ingress deployment.
        if isinstance(value, dict):
            return {k: externalize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [externalize(v) for v in value]
        if isinstance(value, str) and value.startswith('/api/'):
            return settings.api_base_path + value
        return value

    async def evidence_for(asset):
        if asset['provenance']['data_origin'] == 'synthetic':
            if asset['id'] != 'demo-traffic':
                raise ProviderError('evidence_unavailable', 'No fixture evidence exists for this asset.', 404)
            return fixtures.demo_evidence()
        bundle = await app.state.retrieval.evidence(asset)
        app.state.store.put('evidence_bundles', {'id': asset['id'], **bundle})
        for span in bundle.get('evidence', []):
            app.state.store.put('evidence', span)
        return bundle

    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'version': '0.1.0', 'mode': 'demo' if app.state.demo else 'connected'}

    @app.get('/api/overview')
    async def overview():
        state = app.state
        cameras = (await state.sources.cameras())['cameras']
        assets, incidents = current_assets(), current_incidents()
        notes = ['NYC public snapshot context, workshop archive footage, and synthetic corridor scenarios are separate datasets.',
                 'NYC DOT developer camera access requires a data-sharing agreement; public source pages remain linked.',
                 'Unobserved road segments remain unknown. Priority scores are not accident probabilities.']
        if state.demo:
            notes.insert(0, 'DEMO: synthetic annotations and keyword search; no workshop model execution is implied.')
        return externalize({'mode': 'demo' if state.demo else 'connected', 'updated_at': utcnow(), 'cameras': cameras,
            'assets': assets, 'incidents': incidents, 'roads': state.roads, 'risk': current_risk()['cells'],
            'integrations': state.providers, 'activity': state.store.list('activity', 30),
            'metrics': {'cameras': len(cameras), 'assets': len(assets), 'open_incidents': sum(i['status'] == 'open' for i in incidents),
                        'observations': len(state.store.list('observations'))}, 'notes': notes})

    @app.get('/api/integrations')
    async def integrations():
        return {'integrations': app.state.providers}

    @app.post('/api/integrations/check')
    async def check_integrations():
        remote = await diagnostics(settings, app.state.client)
        local = [x for x in app.state.providers if x['id'] in {'sumo', 'browser', 'dataengine'}]
        app.state.providers = remote + local
        activity('context', 'Provider checks completed; health checks do not establish a new pipeline inference run.')
        return {'integrations': app.state.providers}

    @app.get('/api/cameras')
    async def cameras(borough: str = '', q: str = ''):
        result = await app.state.sources.cameras()
        result['cameras'] = [x for x in result['cameras'] if (not borough or x.get('borough') == borough) and q.lower() in x['name'].lower()]
        return externalize(result)

    @app.get('/api/cameras/{id}/snapshot')
    async def snapshot(id: str):
        camera = next((x for x in (await app.state.sources.cameras())['cameras'] if x['id'] == id), None)
        if camera is None:
            raise ProviderError('unknown_camera', 'Select a verified catalog camera.', 404)
        body, content_type = await app.state.sources.snapshot(camera)
        return Response(body, media_type=content_type)

    @app.post('/api/sources/refresh')
    async def refresh():
        result = await app.state.sources.refresh()
        app.state.context = {'sources': result['sources'], 'records': result['records']}
        record_context(result['records'])
        activity('context', 'Public catalog and contextual feeds refreshed independently of workshop ingestion.')
        return externalize(result)

    @app.get('/api/context')
    async def context():
        app.state.context = await app.state.sources.context()
        record_context(app.state.context['records'])
        return app.state.context

    @app.get('/api/archive')
    async def archive(limit: int = Query(24, ge=1, le=100), offset: int = Query(0, ge=0)):
        if app.state.demo:
            assets = current_assets()
            return externalize({'assets': assets[offset:offset+limit], 'mode': 'demo', 'status': 'demo', 'total': len(assets)})
        result = await app.state.archive.inventory(limit, offset)
        for asset in result['assets']:
            app.state.store.put('assets', asset)
        app.state.archive_total = result.get('total', len(result['assets']))
        return externalize(result)

    @app.get('/api/metadata')
    async def metadata():
        if app.state.demo:
            return {'schema': [], 'ingest_config': {}, 'notes': ['Connect the workshop to discover actual filter fields.']}
        return await app.state.archive.metadata()

    @app.get('/api/assets/{id}/evidence')
    async def evidence(id: str):
        return externalize(await evidence_for(require('assets', id)))

    @app.get('/api/assets/{id}/media')
    async def media(id: str, request: Request):
        asset = require('assets', id)
        if asset['id'] == 'demo-traffic':
            return FileResponse(ROOT / 'backend' / 'assets' / 'synthetic-traffic.mp4', media_type='video/mp4')
        response = await app.state.retrieval.media(asset, request.headers.get('range'))
        safe_headers = {k: v for k, v in response.headers.items() if k.lower() in {'content-type', 'content-length', 'content-range', 'accept-ranges', 'etag', 'last-modified'}}
        media_source = asset.get('original_video') or asset.get('source_uri') or ''
        if safe_headers.get('content-type', '').split(';')[0] in {'binary/octet-stream', 'application/octet-stream'} and media_source.lower().endswith('.mp4'):
            # Live VSS emits generic S3 MIME for MP4. This is a registered media
            # URI, never a caller-provided arbitrary URL; retain seek headers.
            safe_headers['content-type'] = 'video/mp4'
        async def chunks():
            try:
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                await response.aclose()
        return StreamingResponse(chunks(), status_code=response.status_code, headers=safe_headers, background=BackgroundTask(response.aclose))

    @app.post('/api/search')
    async def search(body: SearchRequest):
        if app.state.demo:
            return fixtures.search(body.query, body.top_k)
        start = time.perf_counter()
        result = await app.state.retrieval.search(body.model_dump())
        for hit in result['results']:
            existing = app.state.store.get('assets', hit['asset_id'])
            if existing is None:
                asset = dict(id=hit['asset_id'], name='Archive search match', camera_id=hit.get('camera_id'), location=hit['location'],
                    coordinate_precision='unlocated', lat=None, lon=None, source_uri=hit['source_uri'], original_video=hit.get('original_video'),
                    duration_sec=hit['end_sec'], playback_url=f"/api/assets/{hit['asset_id']}/media", capability='indexed_archive',
                    provenance=hit['provenance'], timeline=[{'source':hit['source_uri'], 'start_sec':hit['start_sec'], 'end_sec':hit['end_sec']}])
                app.state.store.put('assets', asset)
            else:
                if hit['source_uri'] and not existing.get('source_uri'):
                    existing['source_uri'] = hit['source_uri']
                timeline = existing.setdefault('timeline', [])
                key = (hit['source_uri'], hit['start_sec'], hit['end_sec'])
                known = {(row.get('source') or row.get('source_uri'), row.get('start_sec'), row.get('end_sec')) for row in timeline}
                if key not in known:
                    timeline.append({'source': hit['source_uri'], 'start_sec': hit['start_sec'], 'end_sec': hit['end_sec']})
                existing['duration_sec'] = max(existing.get('duration_sec', 0), hit['end_sec'])
                app.state.store.put('assets', existing)
        activity('retrieval', f"VSS hybrid search returned {len(result['results'])} evidence spans.", evidence_ids=[x['evidence_id'] for x in result['results']], latency_ms=round((time.perf_counter()-start)*1000, 1))
        return externalize(result)

    @app.post('/api/analysis/jobs', status_code=202)
    async def analyze(body: AnalysisRequest, request: Request):
        asset = require('assets', body.asset_id)
        async def work(id, cancel, progress):
            progress(.2)
            result = await evidence_for(asset)
            progress(.85)
            if not cancel.is_set():
                if asset['provenance']['data_origin'] == 'archive' and result['evidence']:
                    # A review queue item is not a confirmed obstruction or present-day observation.
                    incident_id = 'review-' + asset['id']
                    incident = dict(id=incident_id, title='Archive evidence ready for review',
                        description='Review the stored detections and Cosmos explanation before deciding whether an obstruction is present. Historical evidence does not establish current road conditions.',
                        severity='low', status='open', camera_id=asset.get('camera_id'), asset_id=asset['id'], road_id=None,
                        evidence_ids=[e['id'] for e in result['evidence']], timestamp=utcnow(), confidence=None,
                        data_origin='archive', recommendation=None, assessment='unassessed')
                    app.state.store.put('incidents', incident, insert_only=True)
                    result['incident'] = app.state.store.get('incidents', incident_id)
                activity('perception', 'Stored detection sidecars and reasoning inspected; this did not submit new model processing.',
                         mode=asset['provenance']['execution_mode'], evidence_ids=[e['id'] for e in result['evidence']])
            return externalize(result)
        return await app.state.jobs.submit('analysis', body.model_dump(), work, request.headers.get('idempotency-key'))

    @app.post('/api/ask')
    async def ask(body: AskRequest):
        ctx = {}
        asset_id = body.asset_id
        if body.incident_id:
            incident = require('incidents', body.incident_id)
            ctx['incident'] = incident
            asset_id = asset_id or incident.get('asset_id')
        if asset_id:
            bundle = await evidence_for(require('assets', asset_id))
            ctx['evidence'] = bundle['evidence']
            ctx['reasoning'] = bundle['reasoning']
            ctx['asset'] = bundle['asset']
        if body.forecast_id:
            ctx['forecast'] = require('forecasts', body.forecast_id)
        if body.simulation_id:
            ctx['simulation'] = require('simulations', body.simulation_id)
        if not ctx:
            raise ProviderError('insufficient_evidence', 'Select evidence, a forecast, or a completed scenario first.', 422)
        if app.state.demo:
            ids = [x['id'] for x in ctx.get('evidence', [])]
            answer = 'DEMO operator brief: Review the generated obstruction span [demo-obstruction-span]. The illustration is synthetic and establishes no real incident. Verify actual indexed footage and its location before an operational decision.' if ids else 'DEMO operator brief: This output uses synthetic scenario assumptions; it establishes no observed road condition.'
            if 'simulation' in ctx:
                sim = ctx['simulation']
                ids.append(sim['id'])
                answer += f"\n\nSUMO scenario comparison [{sim['id']}]: {json.dumps(sim.get('comparison', {}), sort_keys=True)}. Compare equal demand and seeds; these results apply only to the assumed scenario."
            if 'forecast' in ctx:
                forecast = ctx['forecast']
                ids.append(forecast['id'])
                answer += f"\n\nForecast [{forecast['id']}] uses {forecast['mode']} mode with {forecast['data_origin']} inputs. It is independent of the illustrated obstruction."
            result = {'answer': answer, 'evidence_ids': ids, 'provider': 'Deterministic demo template', 'model': None, 'execution_mode': 'mock', 'latency_ms': 0, 'notes': ['W&B inference has not run. This template demonstrates citation flow only.']}
        else:
            # Keep registered evidence/context bounded; no settings or bearer credentials are included.
            result = await app.state.operations.recommend(body.question, ctx)
            for provider in app.state.providers:
                if provider['id'] == 'wandb':
                    provider.update(status='ready', checked_at=utcnow(), detail='Evidence-backed operational inference succeeded.', model=result['model'], latency_ms=result['latency_ms'])
        activity('operations', 'Evidence-linked operator brief prepared.', result['execution_mode'], result['evidence_ids'], result['latency_ms'])
        return result

    @app.get('/api/incidents')
    async def incidents():
        return {'incidents': current_incidents()}

    @app.post('/api/incidents/{id}/acknowledge')
    async def acknowledge(id: str):
        incident = require('incidents', id)
        incident.update(status='acknowledged')
        app.state.store.put('incidents', incident)
        return incident

    @app.get('/api/roads')
    async def roads():
        return {'roads': app.state.roads}

    @app.get('/api/risk')
    async def risk():
        return current_risk()

    @app.post('/api/forecasts')
    async def forecast(body: ForecastRequest):
        from backend.forecasting import forecast as compute_forecast
        road = next((r for r in app.state.roads if r['id'] == body.road_id), None)
        if not road:
            raise ProviderError('road_not_found', 'Select a known road segment.', 404)
        result = compute_forecast(road, body.horizons, body.mode, app.state.store.list('sensor_history', 50000))
        app.state.store.put('forecasts', result)
        activity('forecast', f"{result['mode']} forecast prepared with explicit evaluation/provenance.", result['execution_mode'], [result['id']])
        return result

    @app.get('/api/forecasts/{id}')
    async def get_forecast(id: str):
        return require('forecasts', id)

    @app.post('/api/simulations', status_code=202)
    async def simulate(body: SimulationScenario, request: Request):
        from backend.simulation import SimulationRunner
        scenario = body.model_dump()
        run_id = f'sim-{uuid4().hex[:16]}'
        loop = asyncio.get_running_loop()
        async def work(job_id, cancel, progress):
            progress(.02)
            runner = SimulationRunner(settings)
            result = await asyncio.to_thread(runner.run, deepcopy(scenario), run_id, cancel,
                lambda value: loop.call_soon_threadsafe(progress, value))
            if cancel.is_set():
                return {}
            playback = result.pop('playback')
            result.update(id=run_id, job_id=job_id, state='succeeded', scenario=scenario, playback_url=f'/api/simulations/{run_id}/playback', created_at=utcnow())
            app.state.store.put('playback', {'id':run_id, **playback})
            app.state.store.put('simulations', result)
            for provider in app.state.providers:
                if provider['id'] == 'sumo':
                    provider.update(status='ready', checked_at=utcnow(), detail='SUMO baseline, early and late clearance runs completed locally with paired synthetic inputs.', model=result.get('engine'))
            activity('simulation', 'SUMO baseline and two clearance scenarios completed with identical demand/seeds.', 'real_provider', [run_id])
            return externalize(result)
        return await app.state.jobs.submit('simulation', scenario, work, request.headers.get('idempotency-key'))

    @app.get('/api/simulations/{id}')
    async def simulation(id: str):
        return externalize(require('simulations', id))

    @app.get('/api/simulations/{id}/playback')
    async def playback(id: str):
        return require('playback', id)

    @app.get('/api/jobs/{id}')
    async def job(id: str):
        return require('jobs', id)

    @app.post('/api/jobs/{id}/cancel')
    async def cancel(id: str):
        return app.state.jobs.cancel(id)

    @app.post('/api/reingest/preview')
    async def preview(body: ReingestPreviewRequest):
        result = await app.state.reingestion.preview(require('assets', body.asset_id), body.prompt, body.keep_metadata)
        app.state.store.put('previews', {'id': result['preview_id'], 'preview': result})
        return result

    @app.post('/api/reingest/jobs', status_code=202)
    async def reingest(body: ReingestRequest, request: Request):
        if not settings.reingest_enabled:
            raise ProviderError('reingest_disabled', 'Shared archive writes are disabled. An owner must enable them after reviewing a concrete target/prompt/metadata request.', 403)
        selected = require('previews', body.preview_id)['preview']
        async def work(id, cancel, progress):
            before = await app.state.client.request('GET', '/dashboard/stats')
            submitted = await app.state.reingestion.submit(selected)
            upstream_id = submitted.get('job_id') or submitted['id']
            app.state.jobs.update(id, upstream_job_id=upstream_id)
            for attempt in range(90):
                if cancel.is_set():
                    return {}
                status = await app.state.reingestion.status(upstream_id)
                current = status.get('status') or status.get('state')
                if current in {'failed', 'error'}:
                    raise ProviderError('reingest_failed', 'The shared pipeline reported a failed re-ingestion.')
                if current in {'completed', 'succeeded', 'success'}:
                    after = await app.state.client.request('GET', '/dashboard/stats')
                    verification = {'before': before, 'after': after, 'status':'requires_review',
                        'target':selected['target'], 'required_checks':['Target appears fully indexed in Explore with expected segment count.', 'Rerun the traffic search and inspect refreshed reasoning.', 'Match DataEngine detector/reasoner/embedder/writer traces to this job.']}
                    return {'upstream_job_id': upstream_id, 'target': selected['target'], 'status':status,
                        'index_verification':verification, 'notes':['Review per-video unique_segments/expected_segments and DataEngine traces before declaring pipeline/model execution verified.']}
                progress(min(.9, .1+attempt*.009))
                await asyncio.sleep(2)
            raise ProviderError('reingest_pending', 'Monitoring window ended; upstream may still be running. Inspect its job before retrying.')
        return await app.state.jobs.submit('reingest', selected, work, f'preview:{body.preview_id}')

    @app.post('/api/clips')
    async def upload_disabled():
        raise ProviderError('uploads_disabled', 'New media ingestion is disabled by workshop rules. Select an indexed archive chunk.', 403)

    @app.post('/api/demo')
    async def demo():
        if not settings.demo_enabled:
            raise ProviderError('demo_disabled', 'Demo mode is disabled by server configuration.', 403)
        fixtures.seed(app.state.store, app.state.roads)
        app.state.demo = True
        return await overview()

    @app.get('/api/events')
    async def events(request: Request):
        queue = asyncio.Queue(maxsize=50)
        app.state.jobs.listeners.add(queue)
        async def stream():
            try:
                yield 'event: ready\ndata: {}\n\n'
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), 15)
                        yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                    except TimeoutError:
                        yield ': heartbeat\n\n'
            finally:
                app.state.jobs.listeners.discard(queue)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering':'no'})

    @app.get('/{path:path}')
    async def frontend(path: str, request: Request):
        if path.startswith('api/'):
            raise ProviderError('not_found', 'Unknown API route.', 404)
        dist = ROOT / 'frontend' / 'dist'
        candidate = (dist / path).resolve()
        if candidate.is_relative_to(dist.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        index = dist / 'index.html'
        if index.exists():
            return FileResponse(index)
        return JSONResponse({'message':'PharOS API is running. Build the frontend with npm ci && npm run build in frontend/.', 'api_docs':settings.api_base_path+'/docs'}, status_code=503)

    return app


def initial_providers(settings):
    from shutil import which
    result = []
    for id, name, configured, model in [
        ('vss','VAST archive / semantic search',settings.vss_configured,'Cosmos Embed1 / VastDB'),
        ('cosmos','NVIDIA Cosmos3-Reason',bool(settings.cosmos3_reason_url),settings.cosmos3_reason_model),
        ('yolo','YOLO11 detections',bool(settings.yolo_url),'yolo11s'),
        ('embed','Cosmos Embed1',bool(settings.cosmos_embed1_url),settings.cosmos_embed1_model),
        ('wandb','Weights & Biases inference',bool(settings.wandb_api_key),settings.wandb_model or None)]:
        result.append(dict(id=id,name=name,status='unverified' if configured else 'unavailable',detail='Configured; request checks to verify service health.' if configured else 'Workshop environment is not connected locally.',checked_at=None,latency_ms=None,model=model))
    result.append(dict(id='dataengine',name='VAST DataEngine · CoreWeave',status='unverified' if settings.vss_configured else 'unavailable',detail='Hosting relationship documented by workshop. New YOLO → Cosmos → Embed1 → VastDB processing requires a verified re-ingestion trace.',checked_at=None,latency_ms=None,model=None))
    audit_path = ROOT / 'backend' / 'data_adapters' / 'data' / 'discovery' / 'audit.json'
    audit = json.loads(audit_path.read_text()) if audit_path.exists() else {}
    result.append(dict(id='browser',name='Browser discovery · Playwright',status='ready' if audit else 'unverified',detail='Public NYC catalog discovery audit is bundled; current session Browser Use may be unavailable.' if audit else 'Run browser discovery to verify current source metadata.',checked_at=audit.get('completed_at'),latency_ms=None,model=None))
    result.append(dict(id='sumo',name='SUMO / TraCI simulation',status='unverified',detail='Runtime availability is verified when a scenario is executed.',checked_at=None,latency_ms=None,model=None))
    return result


app = create_app()
