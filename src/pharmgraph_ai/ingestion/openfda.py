import asyncio
import typing
from collections.abc import Mapping

import httpx

type JSON = dict[str, typing.Any]


class OpenFDAError(Exception):
    """Base exception for openFDA API errors."""


class OpenFDARateLimitError(OpenFDAError):
    """openFDA API rate limit exceeded."""


class OpenFDAClient:
    BASE_URL = "https://api.fda.gov"

    MAX_LIMIT = 1000
    MAX_SKIP = 25_000

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")

        self._max_retries = max_retries
        self._owns_client = client is None

        self._client = client or httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            params={"api_key": api_key} if api_key else None,
        )

    async def search_labels(
        self,
        query: str,
        *,
        limit: int = 100,
        skip: int = 0,
    ) -> list[JSON]:
        return await self._search(
            endpoint="/drug/label.json",
            query=query,
            limit=limit,
            skip=skip,
        )

    async def search_ndc(
        self,
        query: str,
        *,
        limit: int = 100,
        skip: int = 0,
    ) -> list[JSON]:
        return await self._search(
            endpoint="/drug/ndc.json",
            query=query,
            limit=limit,
            skip=skip,
        )

    async def __aenter__(self) -> typing.Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _search(
        self,
        endpoint: str,
        query: str,
        *,
        limit: int = 100,
        skip: int = 0,
    ) -> list[JSON]:
        if not query.strip():
            raise ValueError("query must not be empty")

        if not 1 <= limit <= self.MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {self.MAX_LIMIT}")

        if not 0 <= skip <= self.MAX_SKIP:
            raise ValueError(f"skip must be between 0 and {self.MAX_SKIP}")

        if skip + limit > self.MAX_SKIP + self.MAX_LIMIT:
            raise ValueError("pagination exceeds openFDA limits")

        response = await self._request(
            endpoint=endpoint,
            params={
                "search": query,
                "limit": limit,
                "skip": skip,
            },
        )

        return response["results"]

    async def _request(self, endpoint: str, *, params: Mapping[str, str | int]) -> JSON:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(endpoint, params=params)

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == self._max_retries:
                    raise OpenFDAError("openFDA request failed") from exc

                await asyncio.sleep(2**attempt)
                continue

            if response.status_code == 404:
                return {"results": []}

            if response.status_code in self.RETRYABLE_STATUS_CODES:
                if attempt < self._max_retries:
                    retry_after = response.headers.get("Retry-After")

                    delay = 2**attempt
                    if retry_after and retry_after.isdecimal():
                        delay = max(delay, int(retry_after))

                    await asyncio.sleep(delay)

                    continue

                if response.status_code == 429:
                    raise OpenFDARateLimitError("openFDA rate limit exceeded")

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise OpenFDAError(
                    f"openFDA returned HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                ) from exc

            try:
                payload = response.json()
            except ValueError as exc:
                raise OpenFDAError("Invalid JSON response from openFDA") from exc

            if not isinstance(payload, dict):
                raise OpenFDAError("Unexpected openFDA response")

            if not isinstance(payload.get("results"), list):
                raise OpenFDAError("Missing results in openFDA response")

            return payload

        raise OpenFDAError("Request retry limit exceeded")
