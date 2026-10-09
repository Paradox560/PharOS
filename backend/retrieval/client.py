"""Authenticated server-side transport for the workshop VSS API.

Never expose the upstream Response.request URL: playback URLs contain a JWT.
Only public, fixed error messages leave this boundary.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import httpx

from backend.errors import ProviderError


class VSSClient:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self._token: str | None = None
        self._login_lock = asyncio.Lock()
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=getattr(settings, "request_timeout_seconds", 25.0),
            follow_redirects=False,
        )

    def _url(self, path: str) -> str:
        base = str(getattr(self.settings, "ingress_url", "")).rstrip("/")
        if not base:
            raise ProviderError("vss_unconfigured", "Workshop VSS connection is not configured.")
        parsed = urlsplit(base)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderError("vss_configuration", "Workshop VSS base URL is invalid.")
        if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path or ".." in path:
            raise ProviderError("vss_invalid_path", "Invalid workshop API route.", 400)
        if base.endswith("/api/v1"):
            base = base[:-7]
        return base + (path if path.startswith("/api/v1/") else "/api/v1" + path)

    async def _login(self, stale_token=None) -> str:
        async with self._login_lock:
            # Concurrent 401s refresh the shared session once.
            if self._token and (stale_token is None or self._token != stale_token):
                return self._token
            if not getattr(self.settings, "username", "") or not getattr(self.settings, "password", ""):
                raise ProviderError("vss_unconfigured", "Workshop VSS credentials are unavailable.")
            try:
                response = await self._http.post(self._url("/auth/login"), json={
                    "username": self.settings.username, "password": self.settings.password,
                })
                if response.status_code in {401, 403}:
                    raise ProviderError("vss_authentication", "Workshop VSS authentication failed.")
                self._check(response)
                data = response.json()
                token = data.get("access_token") if isinstance(data, dict) else None
                if not isinstance(token, str) or not token:
                    raise ProviderError("vss_protocol", "Workshop VSS returned an invalid authentication response.")
                self._token = token
                return token
            except httpx.HTTPError:
                raise ProviderError("vss_connection", "Workshop VSS could not be reached.") from None
            except ValueError:
                raise ProviderError("vss_protocol", "Workshop VSS returned invalid JSON.") from None

    @staticmethod
    def _check(response: httpx.Response):
        status = response.status_code
        if status < 400 and status not in range(300, 400):
            return
        if status in {401, 403}:
            raise ProviderError("vss_authentication", "Workshop VSS authorization failed.")
        if status == 404:
            raise ProviderError("vss_not_found", "Requested workshop evidence is unavailable.", 404)
        if status == 416:
            raise ProviderError("media_range", "Requested media range is not satisfiable.", 416)
        if status == 429:
            raise ProviderError("vss_rate_limited", "Workshop VSS request limit reached. Try again shortly.", 429)
        if 400 <= status < 500:
            raise ProviderError("vss_request_rejected", "Workshop VSS rejected this request.", 400)
        raise ProviderError("vss_upstream", "Workshop VSS is temporarily unavailable.")

    async def _send(self, method, path, json=None, params=None, *, headers=None, stream=False):
        token = await self._login()
        # Exactly two attempts: original and one refreshed authorization retry.
        for attempt in range(2):
            query = dict(params or {})
            request_headers = dict(headers or {})
            if path.removeprefix("/api/v1") in {"/videos/stream", "/videos/playback-url"}:
                query["token"] = token
            else:
                request_headers["Authorization"] = "Bearer " + token
            try:
                request = self._http.build_request(method, self._url(path), json=json, params=query, headers=request_headers)
                response = await self._http.send(request, stream=stream)
            except httpx.HTTPError:
                raise ProviderError("vss_connection", "Workshop VSS could not be reached.") from None
            if response.status_code == 401 and attempt == 0:
                await response.aclose()
                token = await self._login(stale_token=token)
                continue
            try:
                self._check(response)
            except ProviderError:
                await response.aclose()
                raise
            return response
        raise ProviderError("vss_authentication", "Workshop VSS authentication failed.")

    async def request(self, method: str, path: str, json=None, params=None):
        response = await self._send(method, path, json=json, params=params)
        try:
            return response.json()
        except ValueError:
            raise ProviderError("vss_protocol", "Workshop VSS returned invalid JSON.") from None
        finally:
            await response.aclose()

    async def stream(self, path: str, params=None, headers=None) -> httpx.Response:
        """Caller owns aclose(); forward only safe media headers to the browser."""
        return await self._send("GET", path, params=params, headers=headers, stream=True)

    async def close(self):
        self._token = None
        await self._http.aclose()
