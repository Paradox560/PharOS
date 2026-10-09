from dataclasses import dataclass, field
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def env(name: str, default: str = '') -> str:
    return os.environ.get(name, default)


def flag(name: str, default: bool = False) -> bool:
    return env(name, str(default)).lower() in {'1', 'true', 'yes'}


@dataclass(frozen=True)
class Settings:
    username: str = field(default_factory=lambda: env('USERNAME'))
    password: str = field(default_factory=lambda: env('PASSWORD'), repr=False)
    ingress_url: str = field(default_factory=lambda: env('INGRESS_URL'))
    pipeline: str = field(default_factory=lambda: env('PIPELINE'))
    s3_endpoint: str = field(default_factory=lambda: env('S3_ENDPOINT'))
    access_key: str = field(default_factory=lambda: env('ACCESS_KEY'), repr=False)
    secret_key: str = field(default_factory=lambda: env('SECRET_KEY'), repr=False)
    s3_chunks_bucket: str = field(default_factory=lambda: env('S3_CHUNKS_BUCKET'))
    s3_segments_bucket: str = field(default_factory=lambda: env('S3_SEGMENTS_BUCKET'))
    vdb_endpoint: str = field(default_factory=lambda: env('VDB_ENDPOINT', env('S3_ENDPOINT')))
    vastdb_bucket: str = field(default_factory=lambda: env('VASTDB_BUCKET'))
    vdb_schema: str = field(default_factory=lambda: env('VDB_SCHEMA', 'vss-schema'))
    vdb_collection: str = field(default_factory=lambda: env('VDB_COLLECTION', 'vss-collection'))
    vdb_prompts_collection: str = field(default_factory=lambda: env('VDB_PROMPTS_COLLECTION', 'vss-prompts-events'))
    wandb_api_key: str = field(default_factory=lambda: env('WANDB_API_KEY'), repr=False)
    wandb_team: str = field(default_factory=lambda: env('WANDB_TEAM'))
    wandb_project: str = field(default_factory=lambda: env('WANDB_PROJECT'))
    wandb_base_url: str = field(default_factory=lambda: env('WANDB_BASE_URL', 'https://api.inference.wandb.ai/v1'))
    wandb_model: str = field(default_factory=lambda: env('WANDB_MODEL'))
    wandb_weave_enabled: bool = field(default_factory=lambda: flag('WANDB_WEAVE_ENABLED'))
    cosmos3_reason_url: str = field(default_factory=lambda: env('COSMOS3_REASON_URL'))
    cosmos3_reason_model: str = field(default_factory=lambda: env('COSMOS3_REASON_MODEL', 'nvidia/cosmos3-reason'))
    cosmos_embed1_url: str = field(default_factory=lambda: env('COSMOS_EMBED1_URL'))
    cosmos_embed1_model: str = field(default_factory=lambda: env('COSMOS_EMBED1_MODEL', 'nvidia/cosmos-embed1'))
    yolo_url: str = field(default_factory=lambda: env('YOLO_URL'))
    gpu_bearer_token: str = field(default_factory=lambda: env('GPU_BEARER_TOKEN'), repr=False)
    database_path: str = field(default_factory=lambda: env('PHAROS_DATABASE', str(ROOT / 'data' / 'pharos.sqlite3')))
    output_dir: str = field(default_factory=lambda: env('PHAROS_OUTPUT_DIR', str(ROOT / 'data' / 'runs')))
    api_base_path: str = field(default_factory=lambda: env('PHAROS_BASE_PATH', '').rstrip('/'))
    demo_enabled: bool = field(default_factory=lambda: flag('PHAROS_DEMO', True))
    reingest_enabled: bool = field(default_factory=lambda: flag('PHAROS_REINGEST_ENABLED'))
    public_sources_enabled: bool = field(default_factory=lambda: flag('PHAROS_PUBLIC_SOURCES', True))
    nyc_camera_snapshots_enabled: bool = field(default_factory=lambda: flag('NYC_CAMERA_SNAPSHOTS_ENABLED'))
    source_cache_ttl_seconds: int = field(default_factory=lambda: int(env('SOURCE_CACHE_TTL_SECONDS', '300')))
    source_cache_dir: str = field(default_factory=lambda: env('SOURCE_CACHE_DIR', str(ROOT / 'data' / 'sources')))
    request_timeout_seconds: float = 25.0
    max_concurrent_jobs: int = 2
    job_timeout_seconds: int = 180
    history_retention_days: int = field(default_factory=lambda: int(env('PHAROS_HISTORY_RETENTION_DAYS', '30')))
    sumo_binary: str = field(default_factory=lambda: env('SUMO_BINARY', 'sumo'))

    @property
    def vss_configured(self) -> bool:
        return bool(self.ingress_url and self.username and self.password)
