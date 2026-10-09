"""Explicit deterministic demonstration data, never represented as provider output."""
from copy import deepcopy
from backend.models import utcnow

FIXTURE_TIME = '2026-10-09T12:00:00Z'


def provenance():
    return dict(source_url='pharos://fixtures/traffic-illustration-v1', captured_at=FIXTURE_TIME,
                processed_at=FIXTURE_TIME, data_origin='synthetic', execution_mode='mock',
                freshness='unknown', notes=['Generated traffic illustration, not camera footage.',
                  'No YOLO, Cosmos, W&B, VAST or CoreWeave execution is implied.'])


def demo_asset():
    return dict(id='demo-traffic', name='Lane obstruction · synthetic illustration', camera_id=None,
                location='Synthetic illustration · unlocated', coordinate_precision='unlocated', lat=None, lon=None,
                source_uri=None, original_video=None, duration_sec=30, playback_url='/api/assets/demo-traffic/media',
                capability='approved_video', provenance=provenance())


def demo_evidence():
    spans = [dict(id='demo-obstruction-span', asset_id='demo-traffic', source_uri=None,
                  start_sec=8, end_sec=22, summary='Synthetic example: a stationary illustrated truck occupies one lane while other illustrated vehicles pass.', provenance=provenance()),
             dict(id='demo-clearance-span', asset_id='demo-traffic', source_uri=None,
                  start_sec=22, end_sec=30, summary='Synthetic example: the illustrated obstruction is removed and vehicles continue across the frame.', provenance=provenance())]
    detections = [dict(id=f'demo-truck-{t}', evidence_id=spans[0]['id'], class_name='truck', confidence=1,
                       timestamp_sec=t, bbox=[290/640, 145/360, 358/640, 174/360], bbox_units='normalized',
                       track_id=None, model='fixture geometry (not YOLO)', execution_mode='mock') for t in [8, 12, 18, 21]]
    return dict(asset=demo_asset(), evidence=spans, detections=detections, tracks=[],
                reasoning='Illustrative briefing: the generated scene contains a truck-shaped obstruction from 00:08 to 00:22. These fixture annotations demonstrate the evidence UI; Cosmos has not analyzed this illustration. No real event, speed or collision risk is established.',
                availability={'detections':'demo annotations only', 'tracking':'unavailable: no application tracker ran on this illustration', 'reasoning':'demo narrative only'}, provenance=provenance())


def seed(store, roads):
    store.put('assets', demo_asset(), insert_only=True)
    store.put('evidence_bundles', {'id':'demo-traffic', **demo_evidence()}, insert_only=True)
    incident = dict(id='demo-obstruction', title='Possible lane obstruction', description='Demo incident for the generated traffic illustration. Review the annotated 00:08–00:22 span. This is not an observed NYC event.',
        severity='medium', status='open', camera_id=None, asset_id='demo-traffic', road_id=None,
        evidence_ids=['demo-obstruction-span'], timestamp=FIXTURE_TIME, confidence=1,
        data_origin='synthetic', recommendation=None)
    store.put('incidents', incident, insert_only=True)
    # Risk inputs are independent scenario assumptions on a genuine network, never archive claims.
    if roads:
        road = roads[min(1, len(roads)-1)]
        issued_at = utcnow()
        observation = dict(id='demo-scenario-observation', evidence_id='demo-scenario-input', road_id=road['id'],
            kind='obstruction', summary='Synthetic scenario assumption: one lane has reduced capacity.', confidence=.8,
            observed_at=issued_at, factors={'obstruction':1.0, 'persistence':.7, 'slowdown':.45, 'severity':.5, 'corroboration':0.0},
            provenance={**provenance(), 'captured_at':issued_at, 'processed_at':issued_at, 'notes':['Scenario issued timestamp, not an observation of a real event. Unrelated to any NYC camera or workshop archive footage.']})
        store.put('observations', observation, insert_only=True)
    for agent, message in [('context','Verified camera catalog is separate from archive evidence.'), ('perception','Synthetic illustration loaded; live model evidence awaits workshop connection.'), ('retrieval','Demo uses keyword matching. Semantic search requires VSS.'), ('forecast','Illustrative forecast is available; no live accuracy claim.'), ('simulation','SUMO runs synthetic demand on a versioned road network.'), ('operations','Demo brief is deterministic; W&B requires configured access.')]:
        store.put('activity',dict(id=f'demo-{agent}', agent=agent,status='demo',message=message,timestamp=FIXTURE_TIME,evidence_ids=[],execution_mode='mock',latency_ms=None),insert_only=True)


def search(query, top_k):
    words = {w.casefold().strip(',.?!') for w in query.split()}
    hits = []
    for span in demo_evidence()['evidence']:
        tokens = set(span['summary'].lower().split()) | {'traffic', 'lane', 'truck', 'vehicles'}
        overlap = words & tokens
        if overlap:
            hits.append(dict(id=span['id'], asset_id='demo-traffic', evidence_id=span['id'], source_uri=None, original_video=None,
                             start_sec=span['start_sec'], end_sec=span['end_sec'], summary=span['summary'],
                             score=len(overlap)/max(1,len(words)), camera_id=None,location=demo_asset()['location'],provenance=provenance()))
    return dict(query=query, results=sorted(hits,key=lambda x:-x['score'])[:top_k], chunk_results=[],
                engine='Demo keyword fallback (not semantic search)', execution_mode='mock',
                notes=['Only synthetic fixture captions are searched. Connect VSS for Cosmos Embed1 hybrid search.'])
