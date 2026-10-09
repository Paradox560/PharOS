"""Run on assigned workshop VM only. Write a private Secret file, never print values."""
import argparse
import json
import os
from pathlib import Path
import re

KEYS = ['USERNAME','PASSWORD','INGRESS_URL','PIPELINE','S3_ENDPOINT','ACCESS_KEY','SECRET_KEY',
        'S3_CHUNKS_BUCKET','S3_SEGMENTS_BUCKET','VDB_ENDPOINT','VASTDB_BUCKET','VDB_SCHEMA',
        'VDB_COLLECTION','VDB_PROMPTS_COLLECTION','WANDB_API_KEY','WANDB_TEAM','WANDB_PROJECT',
        'WANDB_MODEL','WANDB_BASE_URL','COSMOS3_REASON_URL','COSMOS3_REASON_MODEL','COSMOS_EMBED1_URL',
        'COSMOS_EMBED1_MODEL','YOLO_URL','GPU_BEARER_TOKEN','PHAROS_OPERATOR_USERNAME','PHAROS_OPERATOR_PASSWORD']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--team',required=True)
    parser.add_argument('--out',default='/tmp/pharos-workshop-secret.json')
    args = parser.parse_args()
    if not re.fullmatch(r'team-[1-9][0-9]*',args.team) or os.environ.get('USERNAME') != args.team:
        raise SystemExit('Assigned team and environment USERNAME must match exactly.')
    if not all(os.environ.get(name) for name in ['USERNAME','PASSWORD','INGRESS_URL']):
        raise SystemExit('Assigned workshop environment is missing required access. No Secret created.')
    if not os.environ.get('PHAROS_OPERATOR_PASSWORD'):
        raise SystemExit('Set an operator password privately before preparing the workshop Secret. No credentials printed.')
    secret = {'apiVersion':'v1','kind':'Secret','metadata':{'name':'pharos-workshop','namespace':args.team},'type':'Opaque','stringData':{name:os.environ[name] for name in KEYS if os.environ.get(name)}}
    # O_EXCL prevents following an existing symlink or overwriting a prior credential file.
    fd = os.open(args.out, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    with os.fdopen(fd,'w') as output:
        json.dump(secret,output)
    print('Private workshop Secret manifest prepared. No credentials printed; no resources applied.')
