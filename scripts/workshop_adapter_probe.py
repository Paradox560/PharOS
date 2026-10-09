"""Execute the actual PharOS adapters read-only inside the assigned Team 8 VM.

Credentials stay in the VM. Only bounded, redacted proof is persisted. No upload,
re-ingestion, deployment, database writes, or pipeline changes are performed.
"""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import shlex
import time

from backend.config import Settings
from backend.errors import ProviderError
from backend.ingestion import ArchiveAdapter
from backend.ingestion.archive import normalize_asset
from backend.inference import OperationsAgent
from backend.retrieval import VSSClient, RetrievalAdapter
from backend.retrieval.normalize import utcnow


def load_assigned_environment():
    if os.environ.get('USERNAME') != 'team-8':
        raise RuntimeError('Assigned Team 8 environment identity is required.')
    allowed = {'USERNAME','PASSWORD','INGRESS_URL','PIPELINE','WANDB_API_KEY','WANDB_TEAM','WANDB_PROJECT','WANDB_BASE_URL','WANDB_MODEL'}
    path = Path('/config/team-8.config')
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip().removeprefix('export ')
            if '=' not in line or line.startswith('#'):
                continue
            key, value = line.split('=',1)
            if key in allowed and not os.environ.get(key):
                words = shlex.split(value, comments=True)
                if len(words) == 1:
                    os.environ[key] = words[0]


async def main():
    load_assigned_environment()
    previous = json.loads(Path('/tmp/pharos-readonly-proof.json').read_text())
    available = previous.get('wandb_model_ids', [])
    chosen = os.getenv('WANDB_MODEL') or ('openai/gpt-oss-120b' if 'openai/gpt-oss-120b' in available else '')
    settings = replace(Settings(), wandb_model=chosen)
    client = VSSClient(settings)
    retrieval = RetrievalAdapter(client)
    archive = ArchiveAdapter(client)
    operations = OperationsAgent(settings)
    proof = {'started_at':utcnow(), 'team':'team-8', 'new_pipeline_execution':False, 'checks':[]}
    async def check(name, call):
        start = time.perf_counter()
        result = await call
        proof['checks'].append({'name':name,'status':'succeeded','latency_ms':round((time.perf_counter()-start)*1000,1)})
        return result
    try:
        await check('authenticated_session', client.request('GET','/auth/me'))
        metadata = await check('metadata', archive.metadata())
        proof['custom_prompt_max_length'] = metadata.get('ingest_config',{}).get('custom_prompt_max_length')
        inventory = await check('normalized_inventory', archive.inventory(2,0))
        proof['inventory'] = {'total':inventory['total'],'returned':len(inventory['assets']),
            'duration_sec':inventory['assets'][0]['duration_sec'], 'coordinate_precision':inventory['assets'][0]['coordinate_precision']}
        result = await check('actual_retrieval_adapter_search', retrieval.search({'query':'dense highway traffic with vehicles','top_k':3,'time_filter':'all','metadata_filters':{'camera_id':'i24_cam-1'},'tags':[]}))
        proof['search'] = {'engine':result['engine'],'execution_mode':result['execution_mode'],'segments':len(result['results']),'chunks':len(result['chunk_results'])}
        if not result['results']:
            raise ProviderError('no_traffic_results','No indexed traffic result available for the read-only adapter proof.')
        hit = result['results'][0]
        proof['hit'] = hit
        asset = normalize_asset({'original_video':hit['original_video'],'preview_source':hit['source_uri'],
            'camera_id':hit['camera_id'],'location':hit['location'],'chunk_duration_sec':hit['end_sec'],
            'timeline':[{'source':hit['source_uri'],'segment_start_sec':hit['start_sec'],'segment_end_sec':hit['end_sec']}]})
        evidence = await check('actual_evidence_adapter', retrieval.evidence(asset))
        proof['evidence'] = {'reasoning_models':evidence.get('reasoning_models'), 'spans':evidence['evidence'],
            'detections':len(evidence['detections']),'tracks':len(evidence['tracks']), 'track_sources':sorted({x['source'] for x in evidence['tracks']}),
            'availability':evidence['availability'],'detection_sample':evidence['detections'][:2]}
        raw = await check('sidecar_schema_sample',client.request('GET','/videos/detections',params={'source':hit['source_uri']}))
        proof['sidecar_sample'] = {k:raw.get(k) for k in ['fps','video_shape','frame_count','detection_count','segment_source']}
        proof['sidecar_sample']['frames'] = raw.get('frames',[])[:3]
        media = await check('actual_same_origin_transport',retrieval.media(asset,'bytes=0-1023'))
        try:
            read = await media.aread()
            proof['media'] = {'status':media.status_code,'bytes':len(read),'content_range':media.headers.get('content-range')}
        finally:
            await media.aclose()
        answer = await check('actual_operations_agent',operations.recommend('Review whether the supplied archived traffic evidence supports an obstruction. Cite evidence IDs, explain uncertainty and propose an operator review step.', {'asset':asset,'evidence':evidence['evidence'],'reasoning':evidence['reasoning']}))
        proof['recommendation'] = answer
        dashboard = await check('index_health', client.request('GET','/dashboard/stats'))
        proof['index_health'] = {'overview':dashboard.get('overview'),'pipeline_alignment':dashboard.get('pipeline_alignment')}
        proof['status'] = 'passed'
    except ProviderError as error:
        proof['status'] = 'failed'
        proof['error'] = {'code':error.code,'message':error.message}
    finally:
        await asyncio.gather(client.close(),operations.close())
        proof['completed_at'] = utcnow()
        Path('/tmp/pharos-adapter-proof.json').write_text(json.dumps(proof,indent=2))
        print(json.dumps({'status':proof.get('status'),'checks':proof['checks'],'error':proof.get('error'),'proof':'/tmp/pharos-adapter-proof.json'}),flush=True)


if __name__ == '__main__':
    asyncio.run(main())
