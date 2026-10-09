from copy import deepcopy
from datetime import datetime,timedelta,timezone

import pytest

from backend.errors import ProviderError
from backend.forecasting import forecast, evaluate_baselines, illustrative_history, association
from backend.risk import score_roads
from backend.models import ForecastRun, RiskCell

NOW='2026-10-09T15:00:00Z'
ROAD={'id':'road-a','length_m':750,'speed_limit_kph':40,
      'geometry':{'type':'LineString','coordinates':[[-74,40.75],[-73.99,40.75]]}}


def sensor(minutes,speed=30,**overrides):
    date=datetime.fromisoformat(NOW.replace('Z','+00:00'))-timedelta(minutes=minutes)
    return {'id':str(minutes),'road_id':'road-a','observed_at':date.isoformat(),'speed_kph':speed,
            'provenance':{'data_origin':'public_sensor','execution_mode':'real_provider','source_url':'https://example.com/sensors'},**overrides}


def observation(**overrides):
    return {'id':'obs-a','evidence_id':'evidence-a','road_id':'road-a','observed_at':NOW,'confidence':.8,
            'factors':{'obstruction':1,'persistence':.7,'slowdown':.45,'severity':.5,'corroboration':0},
            'provenance':{'data_origin':'synthetic'},**overrides}


def test_illustrative_is_deterministic_and_split_evaluated():
    a=forecast(ROAD,[5,15,30],'illustrative',now=NOW)
    b=forecast(ROAD,[5,15,30],'illustrative',now=NOW)
    assert a['horizons']==b['horizons']
    assert a['data_origin']=='synthetic' and a['execution_mode']=='mock'
    evaluation=a['evaluation']
    assert evaluation['scope']=='synthetic_only'
    assert evaluation['train_window']['end'] < evaluation['validation_window']['start']
    assert evaluation['validation_window']['end'] < evaluation['test_window']['start']
    assert all(x['test_samples']>100 for x in evaluation['by_horizon'])
    assert all(x['lower_kph']<=x['speed_kph']<=x['upper_kph'] for x in a['horizons'])
    ForecastRun.model_validate(a)


def test_test_targets_cannot_train_validation_intervals():
    history=illustrative_history(ROAD,datetime.fromisoformat(NOW.replace('Z','+00:00')))
    altered=deepcopy(history)
    for item in altered[int(len(altered)*.8):]: item['speed_kph']+=15
    first=evaluate_baselines(history,[5]);second=evaluate_baselines(altered,[5])
    assert first['by_horizon'][0]['historical']['interval_radius_kph']==second['by_horizon'][0]['historical']['interval_radius_kph']
    assert first['by_horizon'][0]['historical']['mae_kph']!=second['by_horizon'][0]['historical']['mae_kph']


def test_persistence_uses_observed_speed_and_explicit_insufficient_evaluation():
    result=forecast(ROAD,[5,15,30],'persistence',[sensor(10,10),sensor(5,20),sensor(0,30)],now=NOW)
    assert result['data_origin']=='public_sensor'
    assert all(row['speed_kph']==30 for row in result['horizons'])
    assert result['horizons'][0]['travel_time_sec']==90
    assert result['horizons'][0]['lower_kph'] is None
    assert result['evaluation']['status']=='insufficient_history'


def test_future_observations_are_excluded():
    result=forecast(ROAD,[5],'persistence',[sensor(10),sensor(5),sensor(0),sensor(-5,180)],now=NOW)
    assert result['horizons'][0]['speed_kph']==30
    assert result['input_window']['samples']==3


@pytest.mark.parametrize('records',[
    [sensor(10,speed_kph=None),sensor(5,speed_kph=None),sensor(0,speed_kph=None)],
    [sensor(10,provenance={'data_origin':'synthetic','execution_mode':'mock'}),sensor(5),sensor(0)],
    [sensor(30),sensor(25),sensor(20)],
    [sensor(10,road_id='different'),sensor(5),sensor(0)]])
def test_unusable_live_history_is_not_replaced_with_demo(records):
    with pytest.raises(ProviderError): forecast(ROAD,[5],'persistence',records,now=NOW)


def test_zero_speed_does_not_invent_finite_travel_time():
    result=forecast(ROAD,[5],'persistence',[sensor(10,0),sensor(5,0),sensor(0,0)],now=NOW)
    assert result['horizons'][0]['travel_time_sec'] is None


@pytest.mark.parametrize('horizons',[[0],[5,5],[True],[60],[]])
def test_invalid_horizons(horizons):
    with pytest.raises(ProviderError): forecast(ROAD,horizons,'illustrative',now=NOW)


def test_geometry_requires_direction_and_review():
    match=association(ROAD,{'geometry':ROAD['geometry']})
    assert match['requires_review'] and match['distance_m']==0
    reverse={'geometry':{'coordinates':list(reversed(ROAD['geometry']['coordinates']))}}
    assert association(ROAD,reverse) is None
    assert association(ROAD,{'geometry':{'coordinates':[[-74,40],[-73.99,40]]}}) is None


def test_missing_coverage_stays_unknown():
    result=score_roads([ROAD],[],now=NOW)['cells'][0]
    assert result['score'] is None and result['level']=='unknown'
    assert result['coverage']==0 and result['confidence']==0


def test_risk_factor_contributions_and_deduplication():
    a=score_roads([ROAD],[observation()],now=NOW)['cells'][0]
    b=score_roads([ROAD],[observation(),observation(id='duplicate')],now=NOW)['cells'][0]
    assert a['score']==65.5
    assert a['coverage']==1 and a['level']=='medium'
    assert a['score']==b['score'] and a['confidence']==b['confidence']
    assert b['evidence_ids']==['evidence-a']
    RiskCell.model_validate(a)


def test_partial_coverage_is_separate_from_score():
    cell=score_roads([ROAD],[observation(factors={'obstruction':1})],now=NOW)['cells'][0]
    assert cell['score']==100 and cell['coverage']==.35


def test_stale_obstruction_cannot_become_green_from_a_fresh_unrelated_factor():
    stale=observation(observed_at='2026-10-09T12:00:00Z',factors={'obstruction':1})
    recent=observation(id='recent',evidence_id='recent',factors={'slowdown':0})
    cell=score_roads([ROAD],[stale,recent],now=NOW)['cells'][0]
    assert cell['level']=='stale' and cell['score']>0


def test_real_evidence_excludes_synthetic_and_untimed_is_unknown():
    real=observation(id='real',evidence_id='real',factors={'obstruction':0},provenance={'data_origin':'public_sensor'})
    cell=score_roads([ROAD],[observation(),real],now=NOW)['cells'][0]
    assert cell['score']==0 and cell['data_origin']=='public_sensor'
    missing=score_roads([ROAD],[observation(observed_at=None)],now=NOW)['cells'][0]
    assert missing['level']=='unknown'
