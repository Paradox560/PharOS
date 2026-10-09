"""Reproduce the bounded road-only extract and SUMO network from downloaded OSM XML."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE_URL = 'https://api.openstreetmap.org/api/0.6/map?bbox=-73.986,40.730,-73.976,40.741'


def reduce_osm(path):
    raw = Path(path).read_bytes()
    root = ET.fromstring(raw)
    chosen = []
    for way in root.findall('way'):
        tags = {x.get('k'): x.get('v') for x in way.findall('tag')}
        if tags.get('highway') in {'primary','secondary','tertiary','residential','unclassified'}:
            chosen.append(way)
    node_ids = {n.get('ref') for w in chosen for n in w.findall('nd')}
    way_ids = {w.get('id') for w in chosen}
    reduced = ET.Element('osm', version='0.6', generator='PharOS bounded road-only extract', copyright='OpenStreetMap contributors', license='https://www.openstreetmap.org/copyright')
    for node in root.findall('node'):
        if node.get('id') in node_ids:
            reduced.append(node)
    reduced.extend(chosen)
    for rel in root.findall('relation'):
        tags = {x.get('k'): x.get('v') for x in rel.findall('tag')}
        if tags.get('type') == 'restriction' and all(m.get('ref') in (way_ids if m.get('type') == 'way' else node_ids) for m in rel.findall('member')):
            reduced.append(rel)
    for entity in reduced:
        entity.attrib.pop('user', None)
        entity.attrib.pop('uid', None)
        entity.attrib.pop('changeset', None)
    ET.indent(reduced)
    ET.ElementTree(reduced).write(ROOT/'manhattan-source.osm.xml', encoding='utf-8', xml_declaration=True)
    print('Source SHA256:', hashlib.sha256(raw).hexdigest(), 'ways:',len(chosen),'nodes:',len(node_ids))


def convert(binary='netconvert'):
    command = [binary, '--osm-files', str(ROOT/'manhattan-source.osm.xml'), '--output-file', str(ROOT/'nyc-demo-corridor.net.xml.gz'), '--geometry.remove', '--junctions.join', '--tls.guess-signals', '--tls.discard-simple', '--tls.join', '--tls.default-type', 'static', '--default.speed', '11.176', '--keep-edges.by-vclass', 'passenger', '--osm.all-attributes', '--output.street-names', 'true', '--no-warnings', 'true']
    subprocess.run(command, check=True)


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1] == 'reduce':
        reduce_osm(sys.argv[2])
    else:
        convert(sys.argv[1] if len(sys.argv)>1 else 'netconvert')
