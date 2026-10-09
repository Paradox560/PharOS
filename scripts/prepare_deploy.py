"""Generate reviewable workshop manifests; NEVER applies them or includes secrets."""
from __future__ import annotations
import argparse
import base64
import gzip
import io
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def bundle():
    files = []
    for folder in ('backend', 'services', 'frontend/src'):
        files += [p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in {'.py','.ts','.tsx','.css'} and '__pycache__' not in p.parts]
    files += [ROOT/name for name in ('requirements.txt','requirements-simulation.txt','frontend/package.json','frontend/package-lock.json','frontend/index.html','frontend/tsconfig.json','frontend/vite.config.ts','backend/data_adapters/data/nyc_cameras_verified.json','simulation/networks/manifest.json','simulation/networks/roads.json','simulation/networks/nyc-demo-corridor.net.xml.gz')]
    memory = io.BytesIO()
    with tarfile.open(fileobj=memory, mode='w') as tar:
        for path in sorted(set(files)):
            if not path.is_file():
                raise SystemExit(f'Missing required deployment input: {path.relative_to(ROOT)}')
            info = tar.gettarinfo(str(path), str(path.relative_to(ROOT)))
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            with path.open('rb') as file:
                tar.addfile(info, file)
    payload = gzip.compress(memory.getvalue(), mtime=0)
    encoded = base64.b64encode(payload).decode()
    if len(encoded) > 900_000:
        raise SystemExit(f'ConfigMap payload too large: {len(encoded)} encoded bytes (limit 900,000).')
    return encoded, len(payload), [str(p.relative_to(ROOT)) for p in sorted(set(files))]


def manifests(team: str, pvc: str | None):
    if not re.fullmatch(r'team-[1-9][0-9]*', team):
        raise SystemExit('Use the explicitly assigned team-N namespace.')
    payload, size, files = bundle()
    metadata = {'name':'pharos','namespace':team,'labels':{'app':'pharos'}}
    configmap = {'apiVersion':'v1','kind':'ConfigMap','metadata':{**metadata,'name':'pharos-code'},'binaryData':{'code.tar.gz':payload}}
    mounts = [{'name':'workspace','mountPath':'/workspace'}, {'name':'runtime','mountPath':'/runtime'}, {'name':'outputs','mountPath':'/data'}]
    volumes = [{'name':'code','configMap':{'name':'pharos-code'}}, {'name':'workspace','emptyDir':{}}, {'name':'runtime','emptyDir':{}}, {'name':'outputs', **({'persistentVolumeClaim':{'claimName':pvc}} if pvc else {'emptyDir':{}})}]
    deployment = {'apiVersion':'apps/v1','kind':'Deployment','metadata':metadata,'spec':{'replicas':1,'selector':{'matchLabels':{'app':'pharos'}},'template':{'metadata':{'labels':{'app':'pharos'}},'spec':{
        'initContainers':[
            {'name':'unpack','image':'python:3.12.11-slim','command':['python','-c',"import tarfile; tarfile.open('/bundle/code.tar.gz').extractall('/workspace', filter='data')"], 'volumeMounts':[{'name':'code','mountPath':'/bundle','readOnly':True},mounts[0]]},
            {'name':'build-ui','image':'node:22.18.0-slim','workingDir':'/workspace/frontend','command':['sh','-ec','npm ci --no-audit --no-fund && npm run build -- --base=/app/ && rm -rf node_modules'], 'volumeMounts':[mounts[0]],'resources':{'requests':{'cpu':'250m','memory':'512Mi'},'limits':{'cpu':'2','memory':'2Gi'}}},
            {'name':'install-runtime','image':'python:3.12.11-slim','workingDir':'/workspace','command':['sh','-ec','python -m venv /runtime/venv && /runtime/venv/bin/pip install --no-cache-dir -r requirements-simulation.txt && /runtime/venv/bin/sumo --version'], 'volumeMounts':mounts[:2], 'resources':{'requests':{'cpu':'250m','memory':'512Mi'},'limits':{'cpu':'2','memory':'2Gi'}}}
        ],
        'containers':[{'name':'pharos','image':'python:3.12.11-slim','workingDir':'/workspace','command':['/runtime/venv/bin/python','-m','uvicorn','backend.app:app','--host','0.0.0.0','--port','8080','--no-access-log'],
            'ports':[{'containerPort':8080}], 'envFrom':[{'secretRef':{'name':'pharos-workshop'}}],
            'env':[{'name':k,'value':v} for k,v in {'PHAROS_BASE_PATH':'/app','PHAROS_REQUIRE_AUTH':'true','PHAROS_DEMO':'false','PHAROS_REINGEST_ENABLED':'false','PHAROS_DATABASE':'/data/pharos.sqlite3','PHAROS_OUTPUT_DIR':'/data/runs','SOURCE_CACHE_DIR':'/data/sources'}.items()],
            'volumeMounts':mounts,'resources':{'requests':{'cpu':'250m','memory':'512Mi'},'limits':{'cpu':'2','memory':'2Gi'}},
            'readinessProbe':{'httpGet':{'path':'/api/health','port':8080},'periodSeconds':10},
            'livenessProbe':{'httpGet':{'path':'/api/health','port':8080},'initialDelaySeconds':30,'periodSeconds':20}}],
        'volumes':volumes}}}}
    service = {'apiVersion':'v1','kind':'Service','metadata':metadata,'spec':{'type':'ClusterIP','selector':{'app':'pharos'},'ports':[{'port':80,'targetPort':8080}]}}
    ingress = {'apiVersion':'networking.k8s.io/v1','kind':'Ingress','metadata':{**metadata,'annotations':{'nginx.ingress.kubernetes.io/use-regex':'true','nginx.ingress.kubernetes.io/rewrite-target':'/$2'}},'spec':{'ingressClassName':'nginx','rules':[{'host':f'video-lab-{team}.cosmos.vastdata.com','http':{'paths':[{'path':'/app(/|$)(.*)','pathType':'ImplementationSpecific','backend':{'service':{'name':'pharos','port':{'number':80}}}}]}}]}}
    return {'apiVersion':'v1','kind':'List','items':[configmap,deployment,service,ingress]}, {'team':team,'compressed_bytes':size,'encoded_bytes':len(payload),'files':files,'persistence':'existing PVC '+pvc if pvc else 'ephemeral emptyDir (lost on pod replacement)','downloads_required':['public runtime images','npm locked dependencies','pinned Python/SUMO wheels']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--team', required=True)
    parser.add_argument('--pvc', help='Existing approved claim in the assigned team namespace')
    parser.add_argument('--out', default=str(ROOT/'deploy'/'generated'))
    args = parser.parse_args()
    output = Path(args.out)
    output.mkdir(parents=True,exist_ok=True)
    payload, report = manifests(args.team,args.pvc)
    (output/'pharos.json').write_text(json.dumps(payload,indent=2))
    (output/'package-report.json').write_text(json.dumps(report,indent=2))
    print(f"Prepared {args.team}: {report['compressed_bytes']} compressed bytes / {report['encoded_bytes']} encoded bytes; no deployment applied.")


if __name__ == '__main__':
    main()
