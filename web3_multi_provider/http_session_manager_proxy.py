import json
import re
import sys
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union, cast
from urllib.parse import urlparse

import requests
from aiohttp import ClientResponse
from eth_typing import URI
from web3._utils.http import DEFAULT_HTTP_TIMEOUT
from web3._utils.http_session_manager import HTTPSessionManager

from web3_multi_provider import metrics


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
            self.cache_and_return_session(cast(URI, self._uri), session)

    def _normalize_cl_path(self, endpoint: Optional[str]) -> Optional[str]:
        try:
            if not endpoint:
                return None
            path = urlparse(str(endpoint)).path
            if not path:
                return None
            parts: List[str] = []
            for seg in path.split("/"):
                if not seg:
                    continue
                if seg.isdigit():
                    parts.append("{num}")
                    continue
                if seg.startswith("0x") and len(seg) > 10:
                    parts.append("{hash}")
                    continue
                if re.fullmatch(r"[A-Fa-f0-9]{32,}", seg):
                    parts.append("{hash}")
                    continue
                parts.append(seg)
            return "/" + "/".join(parts)
        except Exception:
            return None

    def _extract_methods(
        self, endpoint_arg: Any, kwargs: Dict[str, Any]
    ) -> Optional[List[str]]:
        # For CL requests, derive method from the normalized endpoint path
        if self._layer == "cl":
            norm = self._normalize_cl_path(
                str(endpoint_arg) if endpoint_arg is not None else None
            )
            return [norm] if norm else None

        # For EL (and other JSON-RPC), extract method(s) from payload
        methods: List[str] = []
        try:
            payload: Any = None
            if "json" in kwargs and kwargs["json"] is not None:
                payload = kwargs["json"]
            elif "data" in kwargs and kwargs["data"] is not None:
                body = kwargs["data"]
                if isinstance(body, (bytes, bytearray)):
                    text = body.decode("utf-8", errors="ignore")
                else:
                    text = str(body)
                payload = json.loads(text)

            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict) and isinstance(item.get("method"), str):
                        methods.append(item["method"])
            elif isinstance(payload, dict) and isinstance(payload.get("method"), str):
                methods.append(payload["method"])
        except Exception:
            pass

        return methods or None

    def _observe_request_payload(self, kwargs: Dict[str, Any]) -> None:
        try:
            if "data" in kwargs and kwargs["data"] is not None:
                body = kwargs["data"]
                size = (
                    len(body)
                    if isinstance(body, (bytes, bytearray))
                    else sys.getsizeof(body)
                )
                metrics._RPC_SERVICE_REQUEST_PAYLOAD_BYTES.labels(
                    self._network, self._layer, self._chain_id, self._uri
                ).observe(size)
            elif "json" in kwargs and kwargs["json"] is not None:
                size = sys.getsizeof(kwargs["json"])  # approximation
                metrics._RPC_SERVICE_REQUEST_PAYLOAD_BYTES.labels(
                    self._network, self._layer, self._chain_id, self._uri
                ).observe(size)
        except Exception:
            pass

    def _observe_response_payload_sync(self, response: requests.Response) -> None:
        try:
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                size = int(content_length)
                metrics._RPC_SERVICE_RESPONSE_PAYLOAD_BYTES.labels(
                    self._network, self._layer, self._chain_id, self._uri
                ).observe(size)
        except Exception:
            pass

    def _observe_response_payload_async(self, response: ClientResponse) -> None:
        try:
            if response.content_length is not None:
                metrics._RPC_SERVICE_RESPONSE_PAYLOAD_BYTES.labels(
                    self._network, self._layer, self._chain_id, self._uri
                ).observe(int(response.content_length))
        except Exception:
            pass

    def _record_rpc_request(
        self, methods: Optional[List[str]], http_success: str
    ) -> None:
        try:
            if not methods:
                return
            for m in methods:
                metrics._RPC_REQUEST.labels(
                    self._network,
                    self._layer,
                    self._chain_id,
                    self._uri,
                    m,
                    http_success,
                    "",
                ).inc()
        except Exception:
            pass

    def _timed_call(
        self,
        func: Callable[..., requests.Response],
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
        # Optional hint to avoid re-parsing request payloads
        batch_size_hint = kwargs.pop("_batch_size", None)
        batched = str(batch_size_hint is not None)
        try:
            response = func(*args, **kwargs)
            code = str(response.status_code)
            result = "success"
            # Observe response payload size when available
            self._observe_response_payload_sync(response)
            return response
        finally:
            duration = time.perf_counter() - start_time
            # Always record request payload size and RPC request labels regardless of outcome
            self._observe_request_payload(kwargs)
            self._record_rpc_request(
                self._extract_methods(args[0] if args else None, kwargs),
                result,
            )
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
            if batched and batch_size_hint is not None:
                try:
                    metrics._HTTP_RPC_BATCH_SIZE.labels(
                        self._network, self._layer, self._chain_id, self._uri
                    ).observe(int(batch_size_hint))
                except Exception:
                    pass

    async def _timed_async_call(
        self,
        func: Callable[..., Awaitable[ClientResponse]],
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
        # Optional hint to avoid re-parsing request payloads
        batch_size_hint = kwargs.pop("_batch_size", None)
        batched = str(batch_size_hint is not None)
        try:
            response = await func(*args, **kwargs)
            code = str(response.status)
            result = "success"
            # Observe response payload size when available
            self._observe_response_payload_async(response)
            return response
        finally:
            duration = time.perf_counter() - start_time
            # Always record request payload size and RPC request labels regardless of outcome
            self._observe_request_payload(kwargs)
            self._record_rpc_request(
                self._extract_methods(args[0] if args else None, kwargs),
                result,
            )
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
            if batched and batch_size_hint is not None:
                try:
                    metrics._HTTP_RPC_BATCH_SIZE.labels(
                        self._network, self._layer, self._chain_id, self._uri
                    ).observe(int(batch_size_hint))
                except Exception:
                    pass

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
            super().get_response_from_get_request,
            endpoint_uri,
            *args,
            **kwargs,
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
            super().get_response_from_post_request,
            endpoint_uri,
            *args,
            **kwargs,
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
            endpoint_uri,
            *args,
            **kwargs,
        )
