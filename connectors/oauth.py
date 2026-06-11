"""connectors/oauth.py — OAuth2 client-credentials token manager for connectors.

Minimal, SDK-free implementation of RFC 6749 §4.4 (client credentials grant)
on top of httpx, with expiry-aware caching. Used by enterprise connectors
(Microsoft Graph / SharePoint). Outbound token requests go through the same
SSRF validation as every other connector hop.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from core.security import validate_outbound_url

#: Seconds before actual expiry at which a cached token is considered stale.
TOKEN_REFRESH_MARGIN_SECONDS = 60.0

_DEFAULT_TIMEOUT_SECONDS = 10.0


class OAuth2ClientCredentials:
    """Cached OAuth2 client-credentials token source.

    Args:
        token_url: The provider token endpoint.
        client_id: OAuth2 client identifier.
        client_secret: OAuth2 client secret.
        scope: Space-separated scopes (e.g. ``https://graph.microsoft.com/.default``).
        timeout_seconds: HTTP timeout for the token request.
        transport: Optional httpx transport (tests inject a MockTransport).
    """

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not token_url.strip():
            raise ValueError("token_url must be non-empty")
        if not client_id.strip() or not client_secret.strip():
            raise ValueError("client_id and client_secret must be non-empty")
        validate_outbound_url(token_url)

        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._timeout = timeout_seconds
        self._transport = transport

        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        """Return a valid access token, fetching/refreshing when stale."""
        async with self._lock:
            if (
                self._token is not None
                and time.monotonic() < self._expires_at - TOKEN_REFRESH_MARGIN_SECONDS
            ):
                return self._token
            token, expires_in = await self._fetch_token()
            self._token = token
            self._expires_at = time.monotonic() + expires_in
            return token

    async def _fetch_token(self) -> tuple[str, float]:
        validate_outbound_url(self._token_url)
        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport
        ) as client:
            response = await client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": self._scope,
                },
            )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token or not isinstance(token, str):
            raise ValueError("Token endpoint response is missing 'access_token'.")
        expires_in = float(payload.get("expires_in", 3600))
        return token, expires_in
