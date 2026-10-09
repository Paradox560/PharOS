"""Persistence and historical baselines with honest chronological evaluation."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import math
import statistics
import uuid

from backend.errors import ProviderError
from .association import association

MODEL_VERSION='pharos-baselines-1'
STEP_MINUTES=5


def _date(value):
    try:
        date=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return date.astimezone(timezone.utc) if date.tzinfo else None
    except (ValueError,TypeError):
        return None


def _iso(value):
    return value.isoformat().replace('+00:00','Z')


def _number(value):
    try:
        number=float(value)
        return number if math.isfinite(number) else None
    except (ValueError,TypeError):
        return None


def illustrative_history(road,issued):
    """Four weeks of synthetic 5-minute values with fixed road-specific variation."""
    epoch=int(issued.timestamp())//300*300
    end=datetime.fromtimestamp(epoch,tz=timezone.utc)
    road_seed=int(hashlib.sha256(road['id'].encode()).hexdigest()[:8],16)
    speed_limit=_number(road.get('speed_limit_kph')) or 40
    values=[]
    for i in range(28*24*12):
        timestamp=end-timedelta(minutes=5*(28*24*12-1-i))
        hour=timestamp.hour+timestamp.minute/60
        # UTC profile is only an illustrative numerical fixture, not a city traffic model.
        peak=math.exp(-((hour-13)/1.6)**2)+.85*math.exp(-((hour-22)/1.8)**2)
        weekday=.65 if timestamp.weekday()>4 else 1
        variation=math.sin(i*1.137+road_seed%79)*1.6+math.sin(i*.093)*1.1
        speed=max(3,speed_limit*(.88-.5*peak*weekday)+variation)
        values.append({'observed_at':_iso(timestamp),'speed_kph':round(speed,3)})
    return values


def _historical(training):
    slots=defaultdict(list)
    for row in training:
        dt=_date(row['observed_at'])
        slots[(dt.weekday(),dt.hour,dt.minute//5)].append(row['speed_kph'])
    return {key:statistics.mean(value) for key,value in slots.items()}


def _prediction(history,target,fallback):
    return history.get((target.weekday(),target.hour,target.minute//5),fallback)


def _quantile(values,q):
    values=sorted(values)
    return values[min(len(values)-1,max(0,math.ceil((len(values)+1)*q)-1))] if values else None


def evaluate_baselines(history,horizons):
    """Train 60%, validate 20%, test 20%; fixed train means; validation-only bands.

    Test rolling origins use already-observed test samples for persistence, never
    future targets. Target gaps >30 seconds are excluded rather than fabricated.
    """
    if len(history)<72:
        return {'status':'insufficient_history','sample_count':len(history),'by_horizon':[],
                'notes':['At least 72 observations are required for chronological baseline evaluation.']}
    history=sorted(history,key=lambda x:x['observed_at'])
    cut1=int(len(history)*.6);cut2=int(len(history)*.8)
    training,validation,test=history[:cut1],history[cut1:cut2],history[cut2:]
    learned=_historical(training)
    by_time={_date(row['observed_at']):row['speed_kph'] for row in history}
    fallback=statistics.mean(row['speed_kph'] for row in training)
    rows=[]
    for minutes in horizons:
        errors={'validation':{'persistence':[],'historical':[]},'test':{'persistence':[],'historical':[]}}
        for label,subset in [('validation',validation),('test',test)]:
            first=_date(subset[0]['observed_at']);last=_date(subset[-1]['observed_at'])
            for origin in subset:
                target=_date(origin['observed_at'])+timedelta(minutes=minutes)
                if target>last or target<first or target not in by_time:
                    continue
                truth=by_time[target]
                persistence=origin['speed_kph']
                historical=_prediction(learned,target,fallback)
                errors[label]['persistence'].append(abs(truth-persistence))
                errors[label]['historical'].append(abs(truth-historical))
        result={'minutes':minutes,'test_samples':len(errors['test']['persistence'])}
        for method in ('persistence','historical'):
            validation_errors=errors['validation'][method]; test_errors=errors['test'][method]
            radius=_quantile(validation_errors,.9)
            result[method]={'mae_kph':round(statistics.mean(test_errors),3) if test_errors else None,
                'interval_radius_kph':round(radius,3) if radius is not None else None,
                'test_interval_coverage':round(sum(e<=radius for e in test_errors)/len(test_errors),3) if test_errors and radius is not None else None,
                'validation_samples':len(validation_errors)}
        rows.append(result)
    return {'status':'evaluated' if any(row['test_samples'] for row in rows) else 'insufficient_horizon_pairs',
            'sample_count':len(history),'split':'chronological_60_20_20',
            'train_window':{'start':training[0]['observed_at'],'end':training[-1]['observed_at'],'samples':len(training)},
            'validation_window':{'start':validation[0]['observed_at'],'end':validation[-1]['observed_at'],'samples':len(validation)},
            'test_window':{'start':test[0]['observed_at'],'end':test[-1]['observed_at'],'samples':len(test)},
            'by_horizon':rows,'notes':['Historical time-of-week means fit using training observations only.',
                'Unseen time-of-week slots fall back to training mean.',
                '90% nominal absolute-residual bands use validation residuals only; test coverage is measured separately.',
                'No temporal regression is fit; sufficient representative live history is not established.']}


def forecast(road,horizons,mode,records=None,now=None):
    issued=_date(now) if now else datetime.now(timezone.utc)
    if issued is None:
        raise ProviderError('invalid_time','Forecast issue time requires a UTC or offset timestamp.',422)
    if not isinstance(horizons,list) or not 1<=len(horizons)<=6 or any(type(h) is not int or h not in (5,15,30) for h in horizons) or len(set(horizons))!=len(horizons):
        raise ProviderError('invalid_horizons','Choose distinct horizons from 5, 15 and 30 minutes.',422)
    if mode not in ('illustrative','persistence'):
        raise ProviderError('invalid_forecast_mode','Forecast mode must be illustrative or persistence.',422)
    length=_number(road.get('length_m'))
    if not length or length<=0:
        raise ProviderError('invalid_road','Forecast road length must be a positive number in metres.',422)
    assumptions=[]
    if mode=='illustrative':
        history=illustrative_history(road,issued)
        origin='synthetic';execution='mock';source='pharos://fixtures/traffic-history-v1'
        assumptions=['All traffic history and predictions are synthetic numerical examples.',
            'A four-week illustrative UTC time-of-week pattern is unrelated to archive footage or measured NYC traffic.',
            'Historical means are a baseline; this is not a trained or validated real-world traffic model.']
    else:
        eligible={};origins=set();urls=set();future=0;unreviewed=0
        for record in records or []:
            mapping=association(road,record)
            if not mapping:
                continue
            if mapping.get('requires_review'):
                unreviewed+=1
                continue
            timestamp=_date(record.get('observed_at') or record.get('provenance',{}).get('captured_at'))
            speed=_number(record.get('speed_kph'))
            provenance=record.get('provenance',{})
            if not timestamp or timestamp>issued:
                future+=1
                continue
            if speed is None or not 0<=speed<=200 or provenance.get('data_origin')!='public_sensor' or provenance.get('execution_mode')!='real_provider':
                continue
            eligible[timestamp]={'observed_at':_iso(timestamp),'speed_kph':speed}
            origins.add(provenance.get('data_origin'))
            if provenance.get('source_url'):
                urls.add(provenance['source_url'])
        history=[eligible[k] for k in sorted(eligible)]
        if len(history)<3 or (_date(history[-1]['observed_at'])-_date(history[0]['observed_at'])).total_seconds()<600:
            raise ProviderError('insufficient_sensor_history','Persistence requires at least three unit-confirmed, explicitly road-associated sensor observations spanning ten minutes. Geometry candidates require review.',422)
        if (issued-_date(history[-1]['observed_at'])).total_seconds()>900:
            raise ProviderError('stale_sensor_history','Latest associated sensor observation is older than 15 minutes.',422)
        origin='public_sensor';execution='real_provider';source=sorted(urls)[0] if urls else 'pharos://sensors/associated'
        assumptions=['Persistence holds the last measured speed constant across forecast horizons.',
            'Only explicit road/sensor associations with confirmed km/h values are eligible; geometric candidates require review.',
            f'Excluded {future} future/untimed records and {unreviewed} unreviewed geometry candidates.',
            'Archive detections and single camera snapshots do not supply physical speed.']
    evaluation=evaluate_baselines(history,horizons)
    evaluation['data_origin']=origin
    evaluation['scope']='synthetic_only' if origin=='synthetic' else 'associated_sensor_history'
    learned=_historical(history)
    latest=history[-1]['speed_kph'];fallback=statistics.mean(x['speed_kph'] for x in history)
    outputs=[]
    for minutes in horizons:
        method='historical' if mode=='illustrative' else 'persistence'
        speed=_prediction(learned,issued+timedelta(minutes=minutes),fallback) if method=='historical' else latest
        metrics=next((x for x in evaluation['by_horizon'] if x['minutes']==minutes),{})
        radius=metrics.get(method,{}).get('interval_radius_kph')
        outputs.append({'minutes':minutes,'speed_kph':round(speed,2),
            'travel_time_sec':round(length/(speed/3.6),1) if speed>0 else None,
            'lower_kph':round(max(0,speed-radius),2) if radius is not None else None,
            'upper_kph':round(speed+radius,2) if radius is not None else None,
            'interval_method':'validation_absolute_residual_90pct' if radius is not None else 'unavailable'})
    return {'id':f'forecast-{uuid.uuid4()}','state':'succeeded','road_id':road['id'],'issued_at':_iso(issued),
        'mode':mode,'data_origin':origin,'execution_mode':execution,'horizons':outputs,'evaluation':evaluation,
        'model_version':MODEL_VERSION,'features':['last_measured_speed_kph','historical_utc_weekday_hour_5min_slot'],
        'input_window':{'start':history[0]['observed_at'],'end':history[-1]['observed_at'],'samples':len(history)},
        'assumptions':assumptions+['Travel time is road length divided by predicted mean speed; zero speed gives unavailable finite travel time.',
            'Uncertainty bands are empirical baseline errors, not calibrated physical or collision uncertainty.'],
        'provenance':{'source_url':source,'captured_at':history[-1]['observed_at'],'processed_at':_iso(issued),
            'data_origin':origin,'execution_mode':execution,'freshness':'fresh','notes':assumptions}}
