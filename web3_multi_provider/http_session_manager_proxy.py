import time
import web3_multi_provider.metrics as metrics
from typing import Any, Callable, Awaitable

import requests
from aiohttp import ClientResponse
from eth_typing import URI
from web3._utils.http_session_manager import HTTPSessionManager


class HTTPSessionManagerProxy(HTTPSessionManager):
    def __init__(self, chain_id: int | str, uri: str, network: str, cache_size: int = 100, session_pool_max_workers: int = 5):
        super().__init__(cache_size, session_pool_max_workers)
        self._chain_id = str(chain_id)
        self._uri = uri
        self._network = network

    def _timed_call(self, func: Callable[..., requests.Response], *args: Any, **kwargs: Any) -> requests.Response:
        start_time = time.perf_counter()
        response = func(*args, **kwargs)
        duration = time.perf_counter() - start_time
        metrics._RPC_SERVICE_RESPONSE.labels(self._network, self._chain_id, self._uri, str(response.status_code)).observe(duration)
        return response

    async def _timed_async_call(self, func: Callable[..., Awaitable[ClientResponse]], *args: Any, **kwargs: Any) -> ClientResponse:
        start_time = time.perf_counter()
        response = await func(*args, **kwargs)
        duration = time.perf_counter() - start_time
        metrics._RPC_SERVICE_RESPONSE.labels(self._network, self._chain_id, self._uri, str(response.status)).observe(duration)
        return response

    def get_response_from_get_request(self, endpoint_uri: URI, *args: Any, **kwargs: Any) -> requests.Response:
        return self._timed_call(super().get_response_from_get_request, endpoint_uri, args, kwargs)

    def get_response_from_post_request(self, endpoint_uri: URI, *args: Any, **kwargs: Any) -> requests.Response:
        return self._timed_call(super().get_response_from_post_request, endpoint_uri, args, kwargs)

    async def async_get_response_from_get_request(self, endpoint_uri: URI, *args: Any, **kwargs: Any) -> ClientResponse:
        return await self._timed_async_call(super().async_get_response_from_get_request, endpoint_uri, args, kwargs)

    async def async_get_response_from_post_request(self, endpoint_uri: URI, *args: Any, **kwargs: Any) -> ClientResponse:
        return await self._timed_async_call(super().async_get_response_from_post_request, endpoint_uri, args, kwargs)
