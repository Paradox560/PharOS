from __future__ import annotations

import asyncio
import re
from backend.errors import ProviderError
from backend.inference.detections import normalize_detections
from .normalize import normalize_hit, provenance, stable_id, timing


class RetrievalAdapter:
    def __init__(self, client):
        self.client = client

    async def search(self, payload):
        query = str(payload.get("query", "")).strip()
        if not query or len(query) > 2000:
            raise ProviderError("invalid_query", "Search query must contain 1–2000 characters.", 422)
        top_k = int(payload.get("top_k", 10))
        if not 1 <= top_k <= 100:
            raise ProviderError("invalid_top_k", "Search top_k must be between 1 and 100.", 422)
        filters = payload.get("metadata_filters") or {}
        if filters:
            schema = await self.client.request("GET", "/metadata/schema")
            columns = schema.get("schema", []) if isinstance(schema, dict) else []
            allowed = {f["name"]: f for f in columns if isinstance(f, dict) and "name" in f}
            for field, value in filters.items():
                if field not in allowed:
                    raise ProviderError("unknown_metadata_filter", "A requested field is not in the workshop metadata schema.", 422)
                options = allowed[field].get("options")
                values = value if isinstance(value, list) else [value]
                if options is None:
                    discovered = await self.client.request("GET", "/metadata/values", params={"field": field, "prefix": str(values[0]), "limit": 100})
                    options = discovered.get("values", [])
                if not all(v in options for v in values):
                    raise ProviderError("unknown_metadata_value", "A requested filter value is not present in the workshop metadata.", 422)
        body = {key: payload[key] for key in ("time_filter", "metadata_filters", "tags", "custom_start_date", "custom_end_date", "min_similarity", "hybrid_text_weight") if key in payload}
        body.update(query=query, top_k=top_k, llm_top_n=0)
        raw = await self.client.request("POST", "/search", json=body)
        if not isinstance(raw, dict) or not isinstance(raw.get("results", []), list):
            raise ProviderError("vss_protocol", "Workshop search returned an unsupported response.")
        hits = [normalize_hit(row) for row in raw.get("results", []) if isinstance(row, dict) and (row.get("source") or row.get("source_uri"))]
        return {"query": query, "results": hits, "chunk_results": raw.get("chunk_results", []), "engine": "VSS hybrid · Cosmos Embed1 + VastDB", "execution_mode": "real_provider", "notes": ["Segment hits retain exact sources and parent timing; chunk_results are parent-video groups."]}

    async def evidence(self, asset):
        # An archive card may contain several segments. Inspect a bounded first set.
        timeline = asset.get("timeline") or asset.get("segments") or []
        source = asset.get("source_uri") or asset.get("preview_source")
        segments = [s for s in timeline if isinstance(s, dict) and (s.get("source") or s.get("source_uri") or s.get("preview_source"))][:12]
        if not segments and source:
            segments = [{"source": source}]
        if not segments:
            return {"asset": asset, "evidence": [], "detections": [], "tracks": [], "reasoning": "No segment source is available for inspection.", "availability": {"detections": "unavailable", "tracking": "unavailable", "reasoning": "unavailable"}, "provenance": asset.get("provenance", provenance(asset))}
        evidence, detections, tracks, reasons, status = [], [], [], [], []
        for segment in segments:
            uri = segment.get("source") or segment.get("source_uri") or segment.get("preview_source")
            metadata = await self.client.request("GET", "/videos/metadata", params={"source": uri})
            row = metadata.get("metadata", metadata) if isinstance(metadata, dict) else {}
            row = {**segment, **row, "source": uri, "original_video": asset.get("original_video")}
            hit = normalize_hit(row)
            span = {k: hit[k] for k in ("source_uri", "start_sec", "end_sec", "summary", "provenance")}
            span.update(id=hit["evidence_id"], asset_id=asset["id"])
            evidence.append(span)
            reasons.append(span["summary"])
            try:
                sidecar = await self.client.request("GET", "/videos/detections", params={"source": uri})
                ds, ts, availability = normalize_detections(sidecar, span["id"], span["start_sec"])
                detections.extend(ds)
                tracks.extend(ts)
                status.append(availability)
            except ProviderError as exc:
                if exc.status_code != 404:
                    raise
                status.append({"detections": "unavailable: no YOLO sidecar for this segment", "tracking": "unavailable: temporal detections absent"})
        return {"asset": asset, "evidence": evidence, "detections": detections, "tracks": tracks,
                "reasoning": "\n\n".join(reasons), "availability": {
                    "detections": "available" if detections else status[0]["detections"],
                    "tracking": "available" if tracks else status[0]["tracking"],
                    "reasoning": "available" if any(r != "No indexed description available." for r in reasons) else "unavailable"},
                "provenance": asset.get("provenance", provenance(asset)),
                "notes": ["Application tracks are image-space IoU associations, not calibrated trajectories.", "Sidecar timestamps are segment-local unless time_reference explicitly says parent.", "Inspecting up to 12 returned segments per request."]}

    async def ask(self, payload):
        body = {key: payload[key] for key in ("question", "original_video", "top_k") if key in payload}
        return await self.client.request("POST", "/agent/ask", json=body)

    async def synthesize(self, payload):
        if not payload.get("original_video"):
            raise ProviderError("missing_parent", "A registered parent video is required.", 422)
        body = {key: payload[key] for key in ("original_video", "question", "max_segments", "system_prompt") if key in payload}
        return await self.client.request("POST", "/videos/synthesize", json=body)

    async def media(self, asset, range_header=None):
        source = asset.get("original_video") or asset.get("source_uri")
        if not isinstance(source, str) or not source.startswith("s3://"):
            raise ProviderError("media_unavailable", "This registered asset has no indexed media source.", 404)
        headers = {}
        if range_header:
            if not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", range_header):
                raise ProviderError("invalid_media_range", "Only one valid byte range is supported.", 416)
            headers["Range"] = range_header
        return await self.client.stream("/videos/stream", params={"source": source}, headers=headers)
