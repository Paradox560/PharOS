"""Read-only diagnostics preserve configured hosts and use model-specific paths."""
import asyncio
import time
import httpx
from backend.errors import ProviderError
from backend.retrieval.normalize import utcnow
from .operations import OperationsAgent


async def diagnostics(settings, client):
    async def vss():
        start = time.perf_counter()
        status = {"id": "vss", "name": "VAST archive / hybrid search", "status": "unavailable", "detail": "Workshop access not configured.", "checked_at": utcnow(), "latency_ms": None, "model": "Cosmos Embed1 / VastDB"}
        try:
            await client.request("GET", "/auth/me")
            stats = await client.request("GET", "/dashboard/stats")
            status.update(status="ready", detail="Authenticated archive and dashboard responded. New pipeline processing is not established by archive availability.")
        except ProviderError as exc:
            status.update(status="unavailable" if exc.code == "vss_unconfigured" else "error", detail=exc.message)
        status["latency_ms"] = round((time.perf_counter()-start)*1000, 1)
        return status

    async def gpu(identifier, name, url, model=None):
        status = {"id": identifier, "name": name, "status": "unavailable", "detail": "Direct endpoint not configured; stored results may still be available through VSS.", "checked_at": utcnow(), "latency_ms": None, "model": model}
        if not url:
            return status
        start = time.perf_counter()
        token = getattr(settings, "gpu_bearer_token", "")
        headers = {"Authorization": "Bearer " + token} if token else {}
        try:
            async with httpx.AsyncClient(timeout=getattr(settings, "request_timeout_seconds", 25), follow_redirects=False) as http:
                if identifier == "yolo":
                    response = await http.get(url.rstrip("/")+"/healthz", headers=headers)
                    body = response.json() if response.status_code == 200 else {}
                    healthy = body.get("ok") is True and body.get("model_loaded") is True
                else:
                    results = await asyncio.gather(*(http.get(url.rstrip("/")+path, headers=headers) for path in ("/v1/models", "/v1/health/ready", "/v1/health/live")))
                    healthy = all(r.status_code == 200 for r in results)
                    if healthy:
                        model_ids = [m.get("id") for m in results[0].json().get("data", [])]
                        healthy = model in model_ids if model else bool(model_ids)
                        status["model"] = model or (model_ids[0] if model_ids else None)
                status.update(status="ready" if healthy else "error", detail="Configured endpoint health verified. Health alone does not establish a new inference run." if healthy else "Configured model health/model checks did not pass; inspect the team's endpoint/auth configuration.")
        except (httpx.HTTPError, ValueError, TypeError):
            status.update(status="error", detail="Configured model endpoint could not be verified.")
        status["latency_ms"] = round((time.perf_counter()-start)*1000, 1)
        return status

    agent = OperationsAgent(settings)
    try:
        return await asyncio.gather(vss(), agent.diagnostics(),
            gpu("yolo", "YOLO11 on CoreWeave", getattr(settings, "yolo_url", ""), "yolo11s"),
            gpu("cosmos", "Cosmos3-Reason on CoreWeave", getattr(settings, "cosmos3_reason_url", ""), getattr(settings, "cosmos3_reason_model", "")),
            gpu("embed", "Cosmos Embed1 on CoreWeave", getattr(settings, "cosmos_embed1_url", ""), getattr(settings, "cosmos_embed1_model", "")))
    finally:
        await agent.close()
