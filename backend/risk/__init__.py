"""Explainable road-operation priority, never collision probability."""
from __future__ import annotations

from datetime import datetime, timezone
import math

WEIGHTS = {'obstruction':.35,'persistence':.20,'slowdown':.20,'severity':.15,'corroboration':.10}
LEGEND = {'high':{'min':70,'color':'#fb7185'},'medium':{'min':35,'color':'#fbbf24'},
          'low':{'min':0,'color':'#a3e635'},'unknown':{'color':'#64748b'},'stale':{'color':'#a78bfa'}}


def _time(value):
    try:
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError,ValueError):
        return None


def _unit(value):
    try:
        number=float(value)
        return max(0,min(1,number)) if math.isfinite(number) else None
    except (ValueError,TypeError):
        return None


def score_roads(roads, observations, now=None):
    issued=_time(now) or datetime.now(timezone.utc)
    cells=[]
    notes=['Priority index describes supported road disruption, not accident probability.',
           'Scores use known factors only; coverage and confidence are independent of score.',
           'Repeated evidence and additional camera count do not add priority. Unobserved roads stay unknown.',
           'Archive, sensor and synthetic source labels are retained; synthetic observations are excluded when real evidence exists for the same road.']
    for road in roads:
        relevant=[o for o in observations if o.get('road_id')==road['id']]
        real=[o for o in relevant if o.get('provenance',{}).get('data_origin')!='synthetic']
        if real:
            relevant=real
        # Deduplicate each evidence/factor pair before choosing the strongest supported factor.
        unique={}
        for observation in relevant:
            timestamp=_time(observation.get('observed_at') or observation.get('provenance',{}).get('captured_at'))
            confidence=_unit(observation.get('confidence',0)) or 0
            if timestamp is None or (issued-timestamp).total_seconds() < -60:
                continue
            age=max(0,(issued-timestamp).total_seconds())
            if confidence<=0:
                continue
            evidence=observation.get('evidence_id') or observation.get('id')
            for key,weight in WEIGHTS.items():
                value=_unit(observation.get('factors',{}).get(key))
                if value is None:
                    continue
                item={'name':key,'value':value,'weight':weight,'evidence_id':evidence,
                      'observation_id':observation.get('id'),'observed_at':timestamp.isoformat().replace('+00:00','Z'),
                      'age_sec':round(age),'freshness':'fresh' if age<=900 else 'stale',
                      'confidence':confidence,'data_origin':observation.get('provenance',{}).get('data_origin','public_sensor')}
                pair=(evidence,key)
                old=unique.get(pair)
                if old is None or (item['observed_at'],confidence)>(old['observed_at'],old['confidence']):
                    unique[pair]=item
        candidates=list(unique.values())
        selected={}
        for item in candidates:
            old=selected.get(item['name'])
            if old is None or (item['freshness']=='fresh',item['value'],item['confidence'])>(old['freshness']=='fresh',old['value'],old['confidence']):
                selected[item['name']]=item
        factors=list(selected.values())
        coverage=sum(f['weight'] for f in factors)
        score=round(100*sum(f['weight']*f['value'] for f in factors)/coverage,1) if coverage else None
        level=('unknown' if score is None else 'stale' if any(f['freshness']=='stale' for f in factors) else 'high' if score>=70 else 'medium' if score>=35 else 'low')
        confidence=(sum(f['weight']*f['confidence']*max(.05,1-f['age_sec']/1800) for f in factors)/coverage if coverage else 0)
        origins={f['data_origin'] for f in factors}
        origin='synthetic' if origins=={'synthetic'} else 'public_sensor' if 'public_sensor' in origins else 'archive' if 'archive' in origins else 'current_snapshot' if 'current_snapshot' in origins else 'public_sensor'
        cells.append({'id':f"risk-{road['id']}",'road_id':road['id'],'score':score,'level':level,
                      'confidence':round(confidence,3),'coverage':round(coverage,3),'factors':factors,
                      'evidence_ids':sorted({f['evidence_id'] for f in factors if f['evidence_id']}),
                      'observed_at':max((f['observed_at'] for f in factors),default=None),'data_origin':origin})
    return {'cells':cells,'legend':LEGEND,'notes':notes}
