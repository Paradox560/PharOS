"""Conservative sensor-to-road association using coordinates and travel direction."""
from __future__ import annotations

import math


def _xy(coordinate,lat):
    return (float(coordinate[0])*111320*math.cos(math.radians(lat)),float(coordinate[1])*110540)


def _distance(point,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    length=dx*dx+dy*dy
    t=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length)) if length else 0
    return math.hypot(point[0]-a[0]-t*dx,point[1]-a[1]-t*dy)


def association(road,record,max_distance_m=60):
    """Explicit IDs win. Geometry needs aligned direction and a nearby midpoint.

    Returns a reviewable mapping or None. This is not map matching/calibration.
    """
    if record.get('road_id')==road['id']:
        return {'method':'explicit_road_id','distance_m':0,'confidence':1.0}
    if record.get('sensor_id') and record['sensor_id'] in road.get('sensor_ids',[]):
        return {'method':'configured_sensor_id','distance_m':0,'confidence':1.0}
    try:
        a=road.get('geometry',{}).get('coordinates',[])
        b=(record.get('geometry') or {}).get('coordinates',[])
        if len(a)<2 or len(b)<2:
            return None
        lat=float(a[0][1]); a=[_xy(x,lat) for x in a]; b=[_xy(x,lat) for x in b]
        if not all(math.isfinite(value) for point in a+b for value in point):
            return None
        av=(a[-1][0]-a[0][0],a[-1][1]-a[0][1]); bv=(b[-1][0]-b[0][0],b[-1][1]-b[0][1])
        denominator=math.hypot(*av)*math.hypot(*bv)
        alignment=(av[0]*bv[0]+av[1]*bv[1])/denominator if denominator else 0
        if alignment<.85:
            return None
        midpoint=((a[0][0]+a[-1][0])/2,(a[0][1]+a[-1][1])/2)
        distance=min(_distance(midpoint,x,y) for x,y in zip(b,b[1:]))
        if distance>max_distance_m:
            return None
        return {'method':'geometry_candidate','distance_m':round(distance,1),'direction_alignment':round(alignment,3),
                'confidence':round(.8*(1-distance/max_distance_m),3),
                'requires_review':True}
    except (TypeError,ValueError,KeyError,IndexError):
        return None
