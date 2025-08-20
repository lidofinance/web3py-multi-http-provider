import json
import logging
import re
import sys
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, cast
from urllib.parse import urlparse

import requests
from aiohttp import ClientResponse
from eth_typing import URI
from web3._utils.http_session_manager import HTTPSessionManager

from web3_multi_provider import metrics

logger = logging.getLogger(__name__)


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
        """
        Normalize Beacon API paths using official placeholder patterns.

        Based on https://ethereum.github.io/beacon-APIs/#/ specification.
        """
        try:
            if not endpoint:
                return None
            path = urlparse(str(endpoint)).path
            if not path:
                return None

            # Define placeholder mappings based on path context
            path_segments = [seg for seg in path.split("/") if seg]
            normalized_segments: List[str] = []

            for i, seg in enumerate(path_segments):
                # Get context segments
                prev_seg = path_segments[i - 1] if i > 0 else ""
                prev2_seg = path_segments[i - 2] if i >= 2 else ""

                # Skip empty segments
                if not seg:
                    continue

                # Validator blocks - slot numbers (must come before generic blocks check)
                if prev_seg == "blocks" and prev2_seg == "validator" and seg.isdigit():
                    normalized_segments.append("{slot}")
                    continue

                # Block identifiers - blocks, blinded_blocks, blob_sidecars
                elif (
                    prev_seg in ["blocks", "blinded_blocks", "blob_sidecars"]
                    or prev2_seg in ["blocks", "blinded_blocks", "blob_sidecars"]
                    or (prev_seg == "sync_committee" and prev2_seg == "rewards")
                    or (prev_seg == "rewards" and prev2_seg == "beacon")
                ) and (
                    seg.isdigit()
                    or seg.startswith("0x")
                    or seg in ["head", "genesis", "finalized", "justified"]
                ):
                    normalized_segments.append("{block_id}")
                    continue

                # State identifiers - states with slot numbers, state roots, or special values
                elif (
                    prev_seg in ["states", "state"] or prev2_seg in ["states", "state"]
                ) and (
                    seg.isdigit()
                    or seg.startswith("0x")
                    or seg in ["head", "genesis", "finalized", "justified"]
                ):
                    normalized_segments.append("{state_id}")
                    continue

                # Block root for light client bootstrap
                elif (
                    prev_seg == "bootstrap" and seg.startswith("0x") and len(seg) >= 66
                ):
                    normalized_segments.append("{block_root}")
                    continue

                # Peer identifiers
                elif prev_seg == "peers":
                    # Peer IDs can be multiaddr or ENR format
                    normalized_segments.append("{peer_id}")
                    continue

                # Epoch numbers - duties, rewards, liveness endpoints (must come before validator check)
                elif (
                    prev_seg
                    in [
                        "epoch",
                        "epochs",
                        "attester",
                        "proposer",
                        "sync",
                        "attestations",
                        "liveness",
                    ]
                    or prev_seg == "duties"
                ) and seg.isdigit():
                    normalized_segments.append("{epoch}")
                    continue

                # Validator identifiers - index, pubkey, or "all"
                elif (
                    prev_seg in ["validators", "validator"]
                    or "validator" in prev_seg
                    or (prev_seg == "duties" and prev2_seg == "validator")
                ) and (
                    seg.isdigit()
                    or seg.startswith("0x")
                    or seg == "all"
                    or re.fullmatch(r"[A-Fa-f0-9]{96}", seg)
                ):  # 48-byte pubkey
                    normalized_segments.append("{validator_id}")
                    continue

                # Slot numbers (general case, validator blocks handled above)
                elif prev_seg in ["slot", "slots"] and seg.isdigit():
                    normalized_segments.append("{slot}")
                    continue

                # Committee indices
                elif prev_seg == "committees" and seg.isdigit():
                    normalized_segments.append("{committee_index}")
                    continue

                # Generic hex hashes/roots (32+ bytes) - for block_root, state_root, etc.
                elif (
                    seg.startswith("0x") and len(seg) >= 66
                ):  # 0x + 64 chars = 32 bytes
                    normalized_segments.append("{root}")
                    continue

                # Generic numeric IDs not caught above
                elif seg.isdigit():
                    normalized_segments.append("{id}")
                    continue

                # Keep literal path segments
                else:
                    normalized_segments.append(seg)

            return "/" + "/".join(normalized_segments)

        except Exception as e:
            logger.debug("Error normalizing CL path: %s", e, exc_info=True)
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
            logger.debug("Error extracting methods", exc_info=True)

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
            logger.debug("Error observing request payload", exc_info=True)

    def _observe_response_payload_sync(self, response: requests.Response) -> None:
        try:
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                size = int(content_length)
                metrics._RPC_SERVICE_RESPONSE_PAYLOAD_BYTES.labels(
                    self._network, self._layer, self._chain_id, self._uri
                ).observe(size)
        except Exception:
            logger.debug("Error observing response payload", exc_info=True)

    def _observe_response_payload_async(self, response: ClientResponse) -> None:
        try:
            if response.content_length is not None:
                metrics._RPC_SERVICE_RESPONSE_PAYLOAD_BYTES.labels(
                    self._network, self._layer, self._chain_id, self._uri
                ).observe(int(response.content_length))
        except Exception:
            logger.debug("Error observing response payload", exc_info=True)

    def _record_rpc_request(
        self, methods: Optional[List[str]], http_success: str, error_code: str = ""
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
                    error_code,
                ).inc()
        except Exception:
            logger.debug("Error recording RPC request", exc_info=True)

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
        batched = batch_size_hint is not None
        error_code = ""
        try:
            response = func(*args, **kwargs)
            code = str(response.status_code)
            result = "success"
            if self._layer == "el":
                error_code = response.json().get("error", {}).get("code", "")
            # Observe response payload size when available
            self._observe_response_payload_sync(response)
            return response
        finally:
            duration = time.perf_counter() - start_time
            metrics._RPC_SERVICE_RESPONSE_SECONDS.labels(
                self._network, self._layer, self._chain_id, self._uri
            ).observe(duration)
            # Always record request payload size and RPC request labels regardless of outcome
            self._observe_request_payload(kwargs)
            self._record_rpc_request(
                self._extract_methods(args[0] if args else None, kwargs),
                result,
                error_code,
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
            if batched:
                try:
                    metrics._HTTP_RPC_BATCH_SIZE.labels(
                        self._network, self._layer, self._chain_id, self._uri
                    ).observe(int(batch_size_hint))
                except Exception:
                    logger.debug("Error observing batch size", exc_info=True)

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
        batched = batch_size_hint is not None
        # error code in async calls is not available because of the courutine consumption
        error_code = ""
        try:
            response = await func(*args, **kwargs)
            code = str(response.status)
            result = "success"
            # Observe response payload size when available
            self._observe_response_payload_async(response)
            return response
        finally:
            duration = time.perf_counter() - start_time
            metrics._RPC_SERVICE_RESPONSE_SECONDS.labels(
                self._network, self._layer, self._chain_id, self._uri
            ).observe(duration)
            # Always record request payload size and RPC request labels regardless of outcome
            self._observe_request_payload(kwargs)
            self._record_rpc_request(
                self._extract_methods(args[0] if args else None, kwargs),
                result,
                error_code,
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
            if batched:
                try:
                    metrics._HTTP_RPC_BATCH_SIZE.labels(
                        self._network, self._layer, self._chain_id, self._uri
                    ).observe(int(batch_size_hint))
                except Exception:
                    logger.debug("Error observing batch size", exc_info=True)

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
