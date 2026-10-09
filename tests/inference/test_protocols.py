import json
import unittest
from types import SimpleNamespace

import httpx

from backend.errors import ProviderError
from backend.retrieval import VSSClient, RetrievalAdapter
from backend.inference import OperationsAgent
from backend.inference.detections import normalize_detections


def settings(**overrides):
    values = dict(ingress_url="https://team.example", username="team-8", password="secret-password", request_timeout_seconds=1,
                  wandb_base_url="https://api.inference.wandb.ai/v1", wandb_api_key="private-key", wandb_team="assigned-team", wandb_project="pharos", wandb_model="configured-model", wandb_weave_enabled=False)
    return SimpleNamespace(**(values | overrides))


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_jwt_cached_refresh_exactly_once(self):
        calls = []
        logins = 0
        def handle(request):
            nonlocal logins
            calls.append(request)
            if request.url.path.endswith("/auth/login"):
                logins += 1
                return httpx.Response(200, json={"access_token": f"token-{logins}"})
            if request.headers.get("Authorization") == "Bearer token-1":
                return httpx.Response(401, json={"detail": "private upstream information"})
            return httpx.Response(200, json={"ok": True})
        client = VSSClient(settings(), httpx.MockTransport(handle))
        self.assertEqual(await client.request("GET", "/auth/me"), {"ok": True})
        await client.request("GET", "/metadata/schema")
        self.assertEqual(logins, 2)
        self.assertEqual(len(calls), 5)
        self.assertTrue(all(r.url.path.startswith("/api/v1/") for r in calls))
        await client.close()

    async def test_persistent_401_stops_and_conceals_secrets(self):
        calls = []
        def handle(request):
            calls.append(request.url.path)
            return httpx.Response(200, json={"access_token": "secret-token"}) if request.url.path.endswith("login") else httpx.Response(401, text="secret-password secret-token")
        client = VSSClient(settings(), httpx.MockTransport(handle))
        with self.assertRaises(ProviderError) as caught:
            await client.request("GET", "/auth/me")
        self.assertEqual(len(calls), 4)
        self.assertNotIn("secret", str(caught.exception))
        await client.close()

    async def test_range_stream_query_jwt_and_cleanup(self):
        captured = []
        def handle(request):
            captured.append(request)
            if request.url.path.endswith("login"):
                return httpx.Response(200, json={"access_token": "server-only-token"})
            return httpx.Response(206, content=b"clip", headers={"Content-Range": "bytes 10-13/100", "Accept-Ranges": "bytes", "Content-Type": "video/mp4"})
        client = VSSClient(settings(), httpx.MockTransport(handle))
        response = await RetrievalAdapter(client).media({"original_video": "s3://licensed-bucket/original.mp4"}, "bytes=10-13")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(await response.aread(), b"clip")
        self.assertEqual(captured[-1].headers["Range"], "bytes=10-13")
        self.assertEqual(captured[-1].url.params["source"], "s3://licensed-bucket/original.mp4")
        self.assertEqual(captured[-1].url.params["token"], "server-only-token")
        self.assertNotIn("Authorization", captured[-1].headers)
        await response.aclose()
        await client.close()

    async def test_invalid_media_source_and_range_rejected(self):
        adapter = RetrievalAdapter(None)
        with self.assertRaises(ProviderError):
            await adapter.media({"source_uri": "https://arbitrary.example"})
        with self.assertRaises(ProviderError) as caught:
            await adapter.media({"source_uri": "s3://registered/segment"}, "bytes=0-1,3-4")
        self.assertEqual(caught.exception.status_code, 416)

    async def test_search_preserves_segment_parent_and_timing(self):
        source = "s3://team8-segments/capture space/seg%20a.mp4"
        parent = "s3://team8-chunks/capture space.mp4"
        class Client:
            async def request(self, method, path, json=None, params=None):
                assert json['llm_top_n'] == 1  # Team 8 live 422 rejects zero.
                return {"results": [{"source": source, "original_video": parent, "start_sec": 20.25, "end_sec": 25.75, "similarity_score": .8, "location": "toronto", "reasoning_content": "A vehicle waits."}], "chunk_results": [{"original_video": parent, "best_match_start_sec": 20.25, "best_match_end_sec": 25.75}]}
        result = await RetrievalAdapter(Client()).search({"query": "stopped vehicle"})
        hit = result["results"][0]
        self.assertEqual((hit["source_uri"], hit["original_video"], hit["start_sec"], hit["end_sec"]), (source, parent, 20.25, 25.75))
        self.assertEqual(hit["location"], "toronto")
        self.assertEqual(result["chunk_results"][0]["original_video"], parent)

    async def test_metadata_filters_resolved_before_search(self):
        class Client:
            async def request(self, method, path, **kwargs):
                return {"schema": [{"name": "location", "options": ["toronto"]}]}
        with self.assertRaises(ProviderError) as caught:
            await RetrievalAdapter(Client()).search({"query": "traffic", "metadata_filters": {"location": "NYC"}})
        self.assertEqual(caught.exception.code, "unknown_metadata_value")

    async def test_missing_sidecar_is_explicit_unavailable(self):
        class Client:
            async def request(self, method, path, **kwargs):
                if path.endswith("detections"):
                    raise ProviderError("vss_not_found", "Missing sidecar.", 404)
                return {"reasoning_content": "A vehicle is visible.", "start_sec": 5, "end_sec": 10}
        result = await RetrievalAdapter(Client()).evidence({"id": "a", "source_uri": "s3://bucket/segment", "original_video": "s3://bucket/parent"})
        self.assertEqual(result["detections"], [])
        self.assertEqual(result["tracks"], [])
        self.assertIn("unavailable", result["availability"]["detections"])
        self.assertEqual(result["availability"]["reasoning"], "available")

    async def test_operations_projects_citations_and_latency(self):
        captured = []
        def handle(request):
            captured.append(request)
            return httpx.Response(200, json={"model": "actual-model", "choices": [{"message": {"content": json.dumps({"claims": [{"text": "Review the reported obstruction.", "evidence_ids": ["evidence-1"]}], "uncertainties": ["Archive footage is historical."]})}}], "usage": {"total_tokens": 99}})
        agent = OperationsAgent(settings(), httpx.MockTransport(handle))
        result = await agent.recommend("What should an operator review?", {"evidence": [{"id": "evidence-1", "summary": "Possible blockage"}]})
        self.assertEqual(result["evidence_ids"], ["evidence-1"])
        self.assertEqual(result["execution_mode"], "real_provider")
        self.assertEqual(result["model"], "actual-model")
        self.assertGreaterEqual(result["latency_ms"], 0)
        self.assertEqual(captured[0].headers["OpenAI-Project"], "assigned-team/pharos")
        self.assertNotIn("private-key", captured[0].content.decode())
        await agent.close()

    async def test_operations_rejects_fabricated_citation(self):
        def handle(request):
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"claims":[{"text":"Clear the road","evidence_ids":["made-up"]}]}'}}]})
        agent = OperationsAgent(settings(), httpx.MockTransport(handle))
        with self.assertRaises(ProviderError) as caught:
            await agent.recommend("what now", {"evidence": [{"id": "known"}]})
        self.assertEqual(caught.exception.code, "wandb_ungrounded_response")
        await agent.close()

    async def test_operations_provider_error_redacted(self):
        agent = OperationsAgent(settings(), httpx.MockTransport(lambda request: httpx.Response(500, text="private-key https://internal/?token=secret")))
        with self.assertRaises(ProviderError) as caught:
            await agent.recommend("what now", {"evidence": [{"id": "known"}]})
        self.assertNotIn("private-key", str(caught.exception))
        self.assertNotIn("token", str(caught.exception))
        await agent.close()


class TrackingTests(unittest.TestCase):
    def test_aggregate_counts_never_become_tracks(self):
        ds, ts, availability = normalize_detections({"object_classes": ["car"], "counts": {"car": 5}}, "e")
        self.assertEqual(ds, [])
        self.assertEqual(ts, [])
        self.assertIn("unavailable", availability["tracking"])

    def test_one_frame_detections_not_tracking(self):
        ds, ts, availability = normalize_detections({"frames": [{"timestamp_sec": 0, "detections": [{"class_name": "car", "confidence": .9, "bbox": [.1, .1, .3, .4]}]}]}, "e", 10)
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0]["timestamp_sec"], 10)
        self.assertEqual(ts, [])

    def test_temporal_iou_tracks_explicit_application_source(self):
        frames = [{"timestamp_sec": t, "detections": [{"class_name": "car", "confidence": .9, "bbox": [.1+t*.01, .1, .3+t*.01, .4]}]} for t in [0, .5, 1]]
        ds, ts, status = normalize_detections({"frames": frames}, "e")
        self.assertEqual(len(ts), 1)
        self.assertEqual(ts[0]["source"], "application")
        self.assertFalse(ts[0]["calibrated"])
        self.assertEqual(len(ts[0]["detection_ids"]), 3)
