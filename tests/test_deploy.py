"""Review the generated deployment payload without contacting Kubernetes."""
import base64
import gzip
import hashlib
import io
import json
from pathlib import PurePosixPath
import tarfile

import pytest

from scripts.prepare_deploy import ROOT, manifests


@pytest.fixture(scope='module')
def prepared_package():
    documents, report = manifests('team-8', None)
    items = {item['kind']: item for item in documents['items']}
    encoded = items['ConfigMap']['binaryData']['code.tar.gz']
    compressed = base64.b64decode(encoded)
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(compressed)), mode='r:') as archive:
        members = archive.getmembers()
        payloads = {member.name: archive.extractfile(member).read() for member in members if member.isfile()}
    return items, report, encoded, compressed, members, payloads


def test_workshop_payload_excludes_secrets_media_and_generated_runtime(prepared_package):
    _, report, encoded, compressed, members, payloads = prepared_package
    assert len(encoded) == report['encoded_bytes'] < 900_000
    assert len(compressed) == report['compressed_bytes']
    assert len(members) == len(report['files'])
    assert set(payloads) == set(report['files'])
    forbidden_parts = {'.env', '.venv', 'node_modules', '__pycache__', '.git', 'data/runs'}
    for member in members:
        path = PurePosixPath(member.name)
        assert member.isfile(), 'A runtime bundle must not contain symlinks or special files.'
        assert not path.is_absolute() and '..' not in path.parts
        assert not forbidden_parts.intersection(path.parts)
        assert path.suffix.lower() not in {'.mp4', '.mov', '.jpg', '.png', '.webm', '.pem', '.key', '.sqlite', '.sqlite3'}
        assert 'secret' not in path.name.lower()
    assert 'simulation/networks/manhattan-source.osm.xml' not in payloads
    assert 'frontend/dist/index.html' not in payloads
    assert 'backend/simulation/runner.py' in payloads
    assert 'services/tracking/__init__.py' in payloads


def test_runtime_network_and_dependency_inputs_are_complete(prepared_package):
    _, _, _, _, _, payloads = prepared_package
    manifest = json.loads(payloads['simulation/networks/manifest.json'])
    network = payloads['simulation/networks/nyc-demo-corridor.net.xml.gz']
    roads = json.loads(payloads['simulation/networks/roads.json'])
    assert hashlib.sha256(network).hexdigest() == manifest['network_sha256']
    assert len(roads) == manifest['validation']['edge_count']
    assert manifest['license'] == 'ODbL-1.0'
    requirements = payloads['requirements-simulation.txt'].decode()
    assert requirements.startswith('-r requirements.txt')
    for dependency in ('eclipse-sumo', 'sumo-data', 'traci', 'sumolib'):
        assert f'{dependency}==1.27.1' in requirements
    package = json.loads(payloads['frontend/package.json'])
    lockfile = json.loads(payloads['frontend/package-lock.json'])
    assert lockfile['packages']['']['dependencies'] == package['dependencies']
    assert lockfile['packages']['']['devDependencies'] == package['devDependencies']


def test_team_namespace_ingress_paths_and_runtime_mounts(prepared_package):
    items, report, _, _, _, _ = prepared_package
    assert all(item['metadata']['namespace'] == 'team-8' for item in items.values())
    ingress = items['Ingress']
    assert ingress['metadata']['annotations']['nginx.ingress.kubernetes.io/rewrite-target'] == '/$2'
    assert ingress['spec']['rules'][0]['host'] == 'video-lab-team-8.cosmos.vastdata.com'
    path = ingress['spec']['rules'][0]['http']['paths'][0]
    assert path['path'] == '/app(/|$)(.*)'
    assert path['backend']['service']['name'] == 'pharos'
    assert items['Service']['spec']['type'] == 'ClusterIP'

    pod = items['Deployment']['spec']['template']['spec']
    initialization = {item['name']: item for item in pod['initContainers']}
    assert '--base=/app/' in initialization['build-ui']['command'][-1]
    assert 'npm ci' in initialization['build-ui']['command'][-1]
    assert 'requirements-simulation.txt' in initialization['install-runtime']['command'][-1]
    assert '/runtime/venv/bin/sumo --version' in initialization['install-runtime']['command'][-1]
    application = pod['containers'][0]
    assert application['command'][0] == '/runtime/venv/bin/python'
    assert application['workingDir'] == '/workspace'
    assert '--no-access-log' in application['command']
    environment = {item['name']: item['value'] for item in application['env']}
    assert environment['PHAROS_BASE_PATH'] == '/app'
    assert environment['PHAROS_DEMO'] == 'false'
    assert environment['PHAROS_REINGEST_ENABLED'] == 'false'
    assert environment['PHAROS_OUTPUT_DIR'] == '/data/runs'
    assert application['envFrom'] == [{'secretRef': {'name': 'pharos-workshop'}}]
    assert application['readinessProbe']['httpGet']['path'] == '/api/health'
    assert application['livenessProbe']['httpGet']['path'] == '/api/health'
    assert {item['mountPath'] for item in application['volumeMounts']} == {'/workspace', '/runtime', '/data'}
    assert 'ephemeral' in report['persistence']


def test_invalid_team_is_rejected_before_bundle_creation():
    for invalid in ('../team-8', 'team-0', 'team-8;echo', 'default', 'team-8/app'):
        with pytest.raises(SystemExit):
            manifests(invalid, None)


def test_changed_code_triggers_a_new_pod_instead_of_only_updating_configmap(monkeypatch):
    from scripts import prepare_deploy

    templates = []
    for source in (b'first application version', b'updated application version'):
        payload = gzip.compress(source, mtime=0)
        monkeypatch.setattr(prepare_deploy, 'bundle', lambda: (base64.b64encode(payload).decode(), len(payload), []))
        documents, _ = manifests('team-8', None)
        deployment = next(item for item in documents['items'] if item['kind'] == 'Deployment')
        template = deployment['spec']['template']
        assert template['metadata']['annotations']['pharos/code-sha256'] == hashlib.sha256(payload).hexdigest()
        templates.append(template)
    assert templates[0] != templates[1], 'Kubernetes must rerun init containers when packaged code changes.'
