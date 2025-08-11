import time
from typing import Any, Awaitable, Callable, Dict, Optional, Union

import requests
from aiohttp import ClientResponse
from eth_typing import URI
from web3._utils.http import DEFAULT_HTTP_TIMEOUT
from web3._utils.http_session_manager import HTTPSessionManager

import web3_multi_provider.metrics as metrics


class HTTPSessionManagerProxy(HTTPSessionManager):
    """
    A metrics-instrumented extension of `HTTPSessionManager` for monitoring and profiling
    HTTP request performance and behavior for Ethereum JSON-RPC interactions.

    This proxy logs request counts, response statuses, and response latencies
    using Prometheus metrics for both sync and async GET/POST operations.
    """

    def __init__(
        self,
        chain_id: int | str,
        uri: str,
        network: str,
        cache_size: int = 100,
        session_pool_max_workers: int = 5,
        layer: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        """
        Initialize the session manager and configure monitoring labels.

        Args:
            chain_id (int | str): Blockchain chain ID.
            uri (str): RPC endpoint URI.
            network (str): Name of the network (e.g. 'ethereum').
            cache_size (int): LRU cache size for session reuse.
            session_pool_max_workers (int): Max threads for request pooling.
            layer (Optional[str]): Layer identifier (e.g. 'el' or 'cl'). Defaults to 'unknown'.
        """
        super().__init__(cache_size, session_pool_max_workers)
        self._chain_id = str(chain_id)
        self._uri = uri
        self._network = network
        self._layer = "unknown" if layer is None else layer
        if session is not None:
            self.cache_and_return_session(self._uri, session)

    def _timed_call(
        self,
        func: Callable[..., requests.Response],
        batched: bool,
        *args: Any,
        **kwargs: Any,
    ) -> requests.Response:
        """
        Wraps a synchronous HTTP call to measure latency and count status.

        Args:
            func (Callable): Function to call (e.g., super().post).
            batched (bool): Whether this is a batch RPC call.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            requests.Response: HTTP response object.
        """
        start_time = time.perf_counter()
        result = "fail"
        code = "unknown"
        try:
            response = func(*args, **kwargs)
            code = str(response.status_code)
            result = "success"
            return response
        finally:
            duration = time.perf_counter() - start_time
            metrics._HTTP_RPC_SERVICE_REQUESTS.labels(
                self._network,
                self._layer,
                self._chain_id,
                self._uri,
                str(batched),
                code,
                result,
            ).inc()
            metrics._RPC_SERVICE_RESPONSE_SECONDS.labels(
                self._network, self._layer, self._chain_id, self._uri
            ).observe(duration)

    async def _timed_async_call(
        self,
        func: Callable[..., Awaitable[ClientResponse]],
        batched: bool,
        *args: Any,
        **kwargs: Any,
    ) -> ClientResponse:
        """
        Wraps an asynchronous HTTP call to measure latency and count status.

        Args:
            func (Callable): Awaitable function (e.g., async POST).
            batched (bool): Whether this is a batch RPC call.
            *args: Positional args.
            **kwargs: Keyword args.

        Returns:
            ClientResponse: The aiohttp response.
        """
        start_time = time.perf_counter()
        result = "fail"
        code = "unknown"
        try:
            response = await func(*args, **kwargs)
            code = str(response.status)
            result = "success"
            return response
        finally:
            duration = time.perf_counter() - start_time
            metrics._HTTP_RPC_SERVICE_REQUESTS.labels(
                self._network,
                self._layer,
                self._chain_id,
                self._uri,
                str(batched),
                code,
                result,
            ).inc()
            metrics._RPC_SERVICE_RESPONSE_SECONDS.labels(
                self._network, self._layer, self._chain_id, self._uri
            ).observe(duration)

    def get_response_from_get_request(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> requests.Response:
        """
        Performs a timed GET request using the session manager.

        Args:
            endpoint_uri (URI): Endpoint to request.
            *args: Additional arguments.
            **kwargs: Request options.

        Returns:
            requests.Response: HTTP response.
        """
        return self._timed_call(
            super().get_response_from_get_request, False, endpoint_uri, *args, **kwargs
        )

    def get_response_from_post_request(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> requests.Response:
        """
        Performs a timed POST request using the session manager.

        Args:
            endpoint_uri (URI): Endpoint to request.
            *args: Additional arguments.
            **kwargs: Request options.

        Returns:
            requests.Response: HTTP response.
        """
        return self._timed_call(
            super().get_response_from_post_request, False, endpoint_uri, *args, **kwargs
        )

    def get_response_from_post_request_batch(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> requests.Response:
        """
        Performs a timed POST batch request.

        Args:
            endpoint_uri (URI): Batch endpoint.
            *args: Request arguments.
            **kwargs: Request options.

        Returns:
            requests.Response: HTTP response.
        """
        return self._timed_call(
            super().get_response_from_post_request, True, endpoint_uri, *args, **kwargs
        )

    async def async_get_response_from_get_request(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> ClientResponse:
        """
        Performs an async GET request with metrics.

        Args:
            endpoint_uri (URI): Endpoint URI.
            *args: Additional args.
            **kwargs: Additional kwargs.

        Returns:
            ClientResponse: AIOHTTP response object.
        """
        return await self._timed_async_call(
            super().async_get_response_from_get_request,
            False,
            endpoint_uri,
            *args,
            **kwargs,
        )

    async def async_get_response_from_post_request(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> ClientResponse:
        """
        Performs an async POST request with metrics.

        Args:
            endpoint_uri (URI): RPC endpoint.
            *args: Arguments.
            **kwargs: Keyword args.

        Returns:
            ClientResponse: AIOHTTP response.
        """
        return await self._timed_async_call(
            super().async_get_response_from_post_request,
            False,
            endpoint_uri,
            *args,
            **kwargs,
        )

    async def async_get_response_from_post_request_batch(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> ClientResponse:
        """
        Performs an async batch POST request with metrics.

        Args:
            endpoint_uri (URI): Endpoint URI.
            *args: Batch args.
            **kwargs: Keyword args.

        Returns:
            ClientResponse: AIOHTTP response.
        """
        return await self._timed_async_call(
            super().async_get_response_from_post_request,
            True,
            endpoint_uri,
            *args,
            **kwargs,
        )

    def make_post_request_batch(
        self, endpoint_uri: URI, data: Union[bytes, Dict[str, Any]], **kwargs: Any
    ) -> bytes:
        """
        Submits a batch POST request and returns the response payload.

        Args:
            endpoint_uri (URI): Target endpoint.
            data (bytes | Dict[str, Any]): Serialized RPC payload.
            **kwargs: HTTP options like timeout, stream, etc.

        Returns:
            bytes: Raw HTTP response content or streaming chunk.
        """
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
        """
        Asynchronously performs a batch POST request and returns the raw content.

        Args:
            endpoint_uri (URI): Target endpoint.
            data (bytes | Dict[str, Any]): RPC payload.
            **kwargs: Optional arguments passed to the request.

        Returns:
            bytes: Raw HTTP response content.
        """
        response = await self.async_get_response_from_post_request_batch(
            endpoint_uri, data=data, **kwargs
        )
        response.raise_for_status()
        return await response.read()
