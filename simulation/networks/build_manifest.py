"""Generate inspectable road geometry and select a connected northbound 1st Ave route."""
from pathlib import Path
import hashlib
from datetime import datetime, timezone
import json
import sumolib

ROOT = Path(__file__).resolve().parent
netfile = ROOT/'nyc-demo-corridor.net.xml.gz'
net = sumolib.net.readNet(str(netfile))
candidates = {}
for edge in net.getEdges():
    if edge.getName() != '1st Avenue' or not edge.allows('passenger'):
        continue
    points = [net.convertXY2LonLat(*p) for p in edge.getShape()]
    if 40.730 <= points[0][1] <= 40.741 and 40.730 <= points[-1][1] <= 40.742:
        candidates[edge.getID()] = edge


def longest(edge, seen=()):
    if edge.getID() in seen:
        return []
    options = [longest(n, (*seen, edge.getID())) for n in edge.getOutgoing() if n.getID() in candidates and n.getID() not in seen]
    return [edge] + max(options, key=lambda path: sum(e.getLength() for e in path), default=[])

route = max((longest(e) for e in candidates.values()), key=lambda path: sum(e.getLength() for e in path))
assert len(route) >= 5
for a, b in zip(route, route[1:]):
    assert b in a.getOutgoing(), (a.getID(), b.getID())
    assert any(c.getFromLane().allows('passenger') and c.getToLane().allows('passenger') for c in a.getOutgoing()[b])
blockage = min(route, key=lambda e: abs(sum(net.convertXY2LonLat(*p)[1] for p in e.getShape())/len(e.getShape()) - 40.733))
# Avoid a trivial tiny junction-adjacent link; choose an actual block long enough to hold a queue.
blockage = min((e for e in route if e.getLength() > 45), key=lambda e: abs(sum(net.convertXY2LonLat(*p)[1] for p in e.getShape())/len(e.getShape()) - 40.733))
source_url = 'https://api.openstreetmap.org/api/0.6/map?bbox=-73.986,40.730,-73.976,40.741'
assumptions = [
    'OpenStreetMap road geometry and one-way direction imported on 2026-10-09; network is a bounded Manhattan extract.',
    'Northbound 1st Avenue through-route; nearby cross streets are retained in the network but receive no synthetic cross traffic.',
    'OSM lane and speed tags are retained where present; netconvert defaults and lane connections fill missing attributes.',
    'Traffic signals are imported/guessed with SUMO static timing, not observed NYC signal plans.',
    'Passenger cars only; bus-priority restrictions, cyclists, pedestrians, turn demand, parking and real signal coordination are not calibrated.',
    'Demand is synthetic and this model has not been validated against observed corridor speeds or flows.',
]
roads = []
for edge in route:
    points = [[round(v, 7) for v in net.convertXY2LonLat(*p)] for p in edge.getShape()]
    roads.append({'id': 'osm-'+edge.getID(), 'name': '1st Avenue · OSM '+edge.getID(), 'geometry': {'type':'LineString','coordinates':points},
                  'length_m': round(edge.getLength(), 2), 'lanes': edge.getLaneNumber(), 'speed_limit_kph': round(edge.getSpeed()*3.6, 2),
                  'provenance': {'source_url': source_url, 'captured_at': None, 'processed_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'data_origin':'public_sensor','execution_mode':'real_provider','freshness':'unknown','notes':['Static OpenStreetMap road geometry, not a traffic sensor measurement. © OpenStreetMap contributors, ODbL 1.0.', 'Lane connectivity and missing attributes are SUMO import assumptions.']}})
manifest = {'network_id':'nyc-demo-corridor','network_version':'osm-2026-10-09-v1','network_sha256':hashlib.sha256(netfile.read_bytes()).hexdigest(),
            'source_url':source_url,'original_download_sha256':'4d3f5113c524371596b905ec38c1314872b926ba1f3c08ca253e0a47df9e5369',
            'reduced_osm_sha256':hashlib.sha256((ROOT/'manhattan-source.osm.xml').read_bytes()).hexdigest(),
            'license':'ODbL-1.0','attribution':'© OpenStreetMap contributors','retrieved_date':'2026-10-09',
            'route_edges':[e.getID() for e in route], 'route_length_m':round(sum(e.getLength() for e in route),2),
            'blockage_edge':blockage.getID(),'blockage_road_id':'osm-'+blockage.getID(),
            'route_start_lonlat':roads[0]['geometry']['coordinates'][0], 'route_end_lonlat':roads[-1]['geometry']['coordinates'][-1],
            'assumptions':assumptions,
            'validation':{'contiguous_route':True,'passenger_lane_connections':True,'edge_count':len(route),'network_edges':len(net.getEdges()),'oneway_direction':'northbound'}}
(ROOT/'roads.json').write_text(json.dumps(roads,indent=2))
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({k:manifest[k] for k in ('route_edges','route_length_m','blockage_edge','route_start_lonlat','route_end_lonlat','validation')},indent=2))
