import time

from web3._utils.http import DEFAULT_HTTP_TIMEOUT

import web3_multi_provider.metrics as metrics
from typing import Any, Callable, Awaitable, Optional, Union, Dict

import requests
from aiohttp import ClientResponse
from eth_typing import URI
from web3._utils.http_session_manager import HTTPSessionManager


class HTTPSessionManagerProxy(HTTPSessionManager):
    def __init__(
        self,
        chain_id: int | str,
        uri: str,
        network: str,
        cache_size: int = 100,
        session_pool_max_workers: int = 5,
        layer: Optional[str] = None
    ):
        super().__init__(cache_size, session_pool_max_workers)
        self._chain_id = str(chain_id)
        self._uri = uri
        self._network = network
        self._layer = 'unknown' if layer is None else layer

    def _timed_call(self, func: Callable[..., requests.Response], batched: bool, *args: Any, **kwargs: Any) -> requests.Response:
        start_time = time.perf_counter()
        try:
            response = func(*args, **kwargs)
            metrics._HTTP_RPC_SERVICE_REQUESTS.labels(
                self._network,
                self._layer,
                self._chain_id,
                self._uri,
                str(batched),
                str(response.status_code),
            ).inc(1)
        finally:
            duration = time.perf_counter() - start_time
            metrics._RPC_SERVICE_RESPONSE_SECONDS.labels(self._network, self._layer, self._chain_id, self._uri).observe(duration)
        return response

    async def _timed_async_call(
        self,
        func: Callable[..., Awaitable[ClientResponse]],
        batched: bool,
        *args: Any,
        **kwargs: Any,
    ) -> ClientResponse:
        start_time = time.perf_counter()
        try:
            response = await func(*args, **kwargs)
            metrics._HTTP_RPC_SERVICE_REQUESTS.labels(
                self._network,
                self._layer,
                self._chain_id,
                self._uri,
                str(batched),
                str(response.status),
            ).inc(1)
        finally:
            duration = time.perf_counter() - start_time
            metrics._RPC_SERVICE_RESPONSE_SECONDS.labels(self._network, self._layer, self._chain_id, self._uri).observe(duration)
        return response

    def get_response_from_get_request(self, endpoint_uri: URI, *args: Any, **kwargs: Any) -> requests.Response:
        return self._timed_call(super().get_response_from_get_request, False, endpoint_uri, args, kwargs)

    def get_response_from_post_request(self, endpoint_uri: URI, *args: Any, **kwargs: Any) -> requests.Response:
        return self._timed_call(super().get_response_from_post_request, False, endpoint_uri, args, kwargs)

    def get_response_from_post_request_batch(self, endpoint_uri: URI, *args: Any, **kwargs: Any) -> requests.Response:
        return self._timed_call(super().get_response_from_post_request, True, endpoint_uri, args, kwargs)

    async def async_get_response_from_get_request(self, endpoint_uri: URI, *args: Any, **kwargs: Any) -> ClientResponse:
        return await self._timed_async_call(super().async_get_response_from_get_request, False, endpoint_uri, args, kwargs)

    async def async_get_response_from_post_request(self, endpoint_uri: URI, *args: Any, **kwargs: Any) -> ClientResponse:
        return await self._timed_async_call(super().async_get_response_from_post_request, False, endpoint_uri, args, kwargs)

    async def async_get_response_from_post_request_batch(self, endpoint_uri: URI, *args: Any, **kwargs: Any) -> ClientResponse:
        return await self._timed_async_call(super().async_get_response_from_post_request, True, endpoint_uri, args, kwargs)

    def make_post_request_batch(
        self, endpoint_uri: URI, data: Union[bytes, Dict[str, Any]], **kwargs: Any
    ) -> bytes:
        kwargs.setdefault("timeout", DEFAULT_HTTP_TIMEOUT)
        kwargs.setdefault("stream", False)

        start = time.time()
        timeout = kwargs["timeout"]

        with self.get_response_from_post_request_batch(
            endpoint_uri, data=data, **kwargs
        ) as response:
            response.raise_for_status()
            if kwargs.get("stream"):
                return self._handle_streaming_response(response, start, timeout)
            else:
                return response.content

    async def async_make_post_request_batch(
        self, endpoint_uri: URI, data: Union[bytes, Dict[str, Any]], **kwargs: Any
    ) -> bytes:
        response = await self.async_get_response_from_post_request_batch(
            endpoint_uri, data=data, **kwargs
        )
        response.raise_for_status()
        return await response.read()
