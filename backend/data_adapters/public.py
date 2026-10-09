"""Bounded public metadata/context collection; public camera media stays opt-in."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import httpx

from backend.errors import ProviderError

CAMERA_PAGE = 'https://webcams.nyctmc.org/cameras-list'
CAMERA_API = 'https://webcams.nyctmc.org/cameras/graphql'
SPEED_API = 'https://data.cityofnewyork.us/resource/i4gi-tjb9.json'
REPORT_API = 'https://data.cityofnewyork.us/resource/erm2-nwe9.json'
WEATHER_API = 'https://api.weather.gov/stations/KNYC/observations/latest'
CATALOG_QUERY = 'query { cameras { id name area latitude longitude isOnline } }'
DATA_DIR = Path(__file__).parent / 'data'


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def source_time(value, local=False):
    if not value:
        return None
    try:
        date = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if date.tzinfo is None:
            if not local:
                return None
            date = date.replace(tzinfo=ZoneInfo('America/New_York'))
        return date.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, TypeError):
        return None


def freshness(captured_at, max_age):
    captured = source_time(captured_at)
    if not captured:
        return 'unknown'
    seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(captured.replace('Z', '+00:00'))).total_seconds()
    return 'fresh' if -60 <= seconds <= max_age else 'stale'


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def coordinates(lat, lon):
    lat, lon = number(lat), number(lon)
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None, None
    return lat, lon


def provenance(url, captured_at, max_age, notes=()):
    return {'source_url':url, 'captured_at':captured_at, 'processed_at':utc_now(),
            'data_origin':'public_sensor', 'execution_mode':'real_provider',
            'freshness':freshness(captured_at,max_age), 'notes':list(notes)}


def camera_from_catalog(row, verified_at, cached=True):
    if not isinstance(row.get('id'), str) or not isinstance(row.get('name'), str):
        raise ValueError('Camera id and name are required')
    lat, lon = coordinates(row.get('latitude'), row.get('longitude'))
    camera_id = row['id']
    return {'id':camera_id, 'name':row['name'], 'borough':row.get('area'), 'corridor':None,
            'lat':lat, 'lon':lon, 'coordinate_precision':'catalog' if lat is not None else 'unlocated',
            'coordinate_source':CAMERA_API, 'capability':'public_snapshot',
            'status':('cached' if cached else 'available') if row.get('isOnline') else 'unavailable',
            'snapshot_url':f'/api/cameras/{camera_id}/snapshot', 'source_url':CAMERA_PAGE,
            'catalog_verified_at':verified_at,
            'provenance':{'source_url':CAMERA_PAGE, 'captured_at':None, 'processed_at':verified_at,
                'data_origin':'current_snapshot', 'execution_mode':'real_provider', 'freshness':'unknown',
                'notes':['Coordinates and online state from NYC DOT public catalog; image capture time unavailable.',
                         'Catalog metadata does not establish camera image availability or developer feed permission.']}}


def normalize_speed(rows):
    if not isinstance(rows, list):
        raise ValueError('Speed feed must be an array')
    records = []
    for row in rows[:500]:
        if not isinstance(row, dict) or not row.get('link_id'):
            continue
        captured = source_time(row.get('data_as_of'), local=True)
        points = []
        for pair in str(row.get('link_points', '')).split():
            components = pair.split(',')
            if len(components) == 2:
                lat, lon = coordinates(*components)
                if lat is not None:
                    points.append([lon, lat])
        raw = number(row.get('speed'))
        records.append({'id':f"speed-{row['link_id']}-{captured}", 'kind':'traffic_speed',
            'source_id':'nyc-dot-speed', 'sensor_id':str(row['link_id']), 'name':row.get('link_name'),
            'borough':row.get('borough'), 'observed_at':captured, 'speed_native':raw,
            'speed_unit':'source_unspecified', 'speed_kph':None,
            'travel_time_sec':number(row.get('travel_time')),
            'source_status':row.get('status'),
            'geometry':{'type':'LineString','coordinates':points} if len(points)>1 else None,
            'provenance':provenance(SPEED_API,captured,900,
                ['Socrata floating timestamp interpreted in America/New_York.',
                 'Published speed metadata omits units. Native speed is retained; km/h conversion is unavailable.',
                 'Link points may be truncated by the source; geometry is context, not a validated routable network.'])})
    return records


def normalize_reports(rows):
    if not isinstance(rows,list):
        raise ValueError('311 feed must be an array')
    records = []
    for row in rows[:100]:
        if not isinstance(row,dict) or not row.get('unique_key'):
            continue
        lat, lon = coordinates(row.get('latitude'),row.get('longitude'))
        captured = source_time(row.get('created_date'),local=True)
        records.append({'id':f"311-{row['unique_key']}", 'kind':'service_report', 'source_id':'nyc-311',
            'summary':' · '.join(str(row.get(key,'')) for key in ('complaint_type','descriptor')).strip(' ·'),
            'status':row.get('status'), 'borough':row.get('borough'), 'lat':lat, 'lon':lon,
            'observed_at':captured, 'provenance':provenance(REPORT_API,captured,172800,
                ['Unverified service request; report creation time is not independently observed incident time.',
                 'Source updates daily. Missing coordinates remain unlocated.'])})
    return records


def normalize_weather(data):
    props = data.get('properties') if isinstance(data,dict) else None
    if not isinstance(props,dict) or not props.get('timestamp'):
        raise ValueError('Weather observation properties are missing')
    captured = source_time(props['timestamp'])
    def measurement(name, unit):
        item = props.get(name) or {}
        return number(item.get('value')) if item.get('unitCode') == unit else None
    return [{'id':f'weather-KNYC-{captured}', 'kind':'weather', 'source_id':'nws-knyc',
             'station_id':'KNYC', 'observed_at':captured, 'summary':props.get('textDescription'),
             'temperature_c':measurement('temperature','wmoUnit:degC'),
             'visibility_m':measurement('visibility','wmoUnit:m'),
             'precipitation_last_hour_m':measurement('precipitationLastHour','wmoUnit:m'),
             'geometry':data.get('geometry'), 'provenance':provenance(WEATHER_API,captured,7200,
                 ['Central Park station observation; not a measurement at each camera or archive location.'])}]


class PublicSources:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.client = httpx.AsyncClient(transport=transport, timeout=getattr(settings,'request_timeout_seconds',25),
            follow_redirects=False, headers={'User-Agent':'PharOS/0.1 (NYC road operations context; local review)', 'Accept':'application/json'})
        self.cache_dir = Path(getattr(settings,'source_cache_dir', 'data/sources'))
        self.ttl = max(60,min(3600,int(getattr(settings,'source_cache_ttl_seconds',300))))
        self._locks = {key:asyncio.Lock() for key in ('cameras','nyc-dot-speed','nyc-311','nws-knyc','snapshot')}
        self._last_attempt = {}
        self._cache = {}
        self._snapshot_cache = {}
        seed = json.loads((DATA_DIR / 'nyc_cameras_verified.json').read_text())
        self._camera_catalog = {x['id']:camera_from_catalog(x,seed['verified_at']) for x in seed['cameras']}
        saved = self._load('cameras')
        if saved:
            self._camera_catalog = {x['id']:x for x in saved.get('cameras',[]) if x.get('id')}

    async def close(self):
        await self.client.aclose()

    def _load(self,key):
        if key in self._cache:
            return deepcopy(self._cache[key])
        try:
            item = json.loads((self.cache_dir / f'{key}.json').read_text())
            if isinstance(item,dict):
                self._cache[key] = item
                return deepcopy(item)
        except (OSError,ValueError):
            pass
        return None

    def _save(self,key,item):
        self._cache[key] = deepcopy(item)
        try:
            self.cache_dir.mkdir(parents=True,exist_ok=True)
            target = self.cache_dir / f'{key}.json'
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps(item,ensure_ascii=False))
            temporary.replace(target)
        except OSError:
            # The in-memory cache still works on a read-only deployment filesystem.
            pass

    async def _json(self,method,url,**kwargs):
        try:
            response = await self.client.request(method,url,**kwargs)
            response.raise_for_status()
            if len(response.content) > 4_000_000:
                raise ProviderError('source_too_large','Public metadata response exceeded the size bound.')
            return response.json()
        except (httpx.HTTPError,ValueError):
            raise ProviderError('public_source_unavailable','Public source request failed; cached data may be available.') from None

    async def cameras(self):
        cameras = deepcopy(list(self._camera_catalog.values()))
        enabled = getattr(self.settings,'nyc_camera_snapshots_enabled',False)
        for camera in cameras:
            camera['snapshot_access'] = 'enabled' if enabled else 'agreement_required'
            if not enabled:
                camera['snapshot_url'] = None
        return {'cameras':cameras,'source':CAMERA_PAGE,'status':'cached'}

    async def _refresh_cameras(self):
        async with self._locks['cameras']:
            now = time.monotonic()
            if now-self._last_attempt.get('cameras',-1e10) < self.ttl:
                return await self.cameras()
            self._last_attempt['cameras'] = now
            data = await self._json('POST',CAMERA_API,json={'query':CATALOG_QUERY})
            rows = data.get('data',{}).get('cameras') if isinstance(data,dict) else None
            if not isinstance(rows,list) or not rows or data.get('errors'):
                raise ProviderError('camera_schema','Public catalog returned no valid camera records.')
            verified = utc_now()
            try:
                cameras = [camera_from_catalog(row,verified,False) for row in rows[:1500]]
            except (ValueError,TypeError,AttributeError):
                raise ProviderError('camera_schema','Public camera catalog schema changed.') from None
            self._camera_catalog = {x['id']:x for x in cameras}
            self._save('cameras',{'cameras':cameras,'fetched_at':verified})
            result = await self.cameras()
            result['status'] = 'available'
            return result

    async def _context_source(self,key,url,normalizer,params=None,max_age=900):
        async with self._locks[key]:
            cached = self._load(key)
            now = time.monotonic()
            can_fetch = (getattr(self.settings,'public_sources_enabled',True)
                         and now-self._last_attempt.get(key,-1e10) >= self.ttl
                         and (not cached or freshness(cached.get('fetched_at'),self.ttl) != 'fresh'))
            error = None
            if can_fetch:
                self._last_attempt[key] = now
                try:
                    data = await self._json('GET',url,params=params)
                    records = normalizer(data)
                    cached = {'records':records,'fetched_at':utc_now()}
                    self._save(key,cached)
                except (ProviderError,ValueError,TypeError,KeyError):
                    error = 'Request failed or source schema changed.'
            if not cached:
                return {'id':key,'source_url':url,'status':'unavailable','checked_at':utc_now(),
                        'record_count':0,'error':error or 'No cached records; public requests disabled or rate bounded.'}, []
            records = deepcopy(cached['records'])
            for record in records:
                record['provenance']['freshness'] = freshness(record['provenance'].get('captured_at'),max_age)
            source = {'id':key,'source_url':url,'status':'available' if can_fetch and not error else 'cached',
                      'checked_at':cached['fetched_at'],'record_count':len(records),
                      'freshness':'fresh' if records and all(r['provenance']['freshness']=='fresh' for r in records) else 'stale'}
            if error:
                source['error'] = error
            return source, records

    async def context(self):
        results = await asyncio.gather(
            self._context_source('nyc-dot-speed',SPEED_API,normalize_speed,{'$limit':500,'$order':'data_as_of DESC'},900),
            self._context_source('nyc-311',REPORT_API,normalize_reports,
                {'$select':'unique_key,created_date,complaint_type,descriptor,status,borough,latitude,longitude',
                 '$where':"agency='DOT'",'$order':'created_date DESC','$limit':100},172800),
            self._context_source('nws-knyc',WEATHER_API,normalize_weather,max_age=7200))
        return {'sources':[source for source,_ in results], 'records':[record for _,records in results for record in records]}

    async def refresh(self):
        camera_error = None
        try:
            cameras = await self._refresh_cameras() if getattr(self.settings,'public_sources_enabled',True) else await self.cameras()
        except ProviderError as exc:
            cameras = await self.cameras()
            camera_error = exc.message
        context = await self.context()
        source = {'id':'nyc-cameras','source_url':CAMERA_API,'status':cameras['status'],'record_count':len(cameras['cameras'])}
        if camera_error:
            source['error'] = camera_error
        sources = [source,*context['sources']]
        return {'cameras':cameras['cameras'],'sources':sources,'records':context['records'],
                'status':'available' if all(x['status']=='available' for x in sources) else 'partial'}

    async def snapshot(self,camera):
        if not getattr(self.settings,'nyc_camera_snapshots_enabled',False):
            raise ProviderError('camera_agreement_required','NYC DOT developer camera access must be enabled after its data-sharing agreement.',403)
        camera_id = camera.get('id') if isinstance(camera,dict) else str(camera)
        if camera_id not in self._camera_catalog:
            raise ProviderError('unknown_camera','Camera was not found in the verified public catalog.',404)
        async with self._locks['snapshot']:
            previous = self._snapshot_cache.get(camera_id)
            if previous and time.monotonic()-previous[0]<30:
                return previous[1],previous[2]
            # URL is built only from a verified catalog ID, never caller supplied URLs.
            url = f'https://webcams.nyctmc.org/api/cameras/{camera_id}/image'
            try:
                async with self.client.stream('GET',url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get('content-type','').split(';')[0]
                    if content_type not in {'image/jpeg','image/png','image/webp'}:
                        raise ProviderError('invalid_snapshot','Camera source did not return a supported image.')
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content)>8_000_000:
                            raise ProviderError('snapshot_too_large','Camera image exceeded the size bound.')
                    value = bytes(content)
            except httpx.HTTPError:
                raise ProviderError('snapshot_unavailable','The public camera image is unavailable.') from None
            if len(self._snapshot_cache)>=32:
                self._snapshot_cache.pop(next(iter(self._snapshot_cache)))
            self._snapshot_cache[camera_id] = (time.monotonic(),value,content_type)
            return value,content_type
