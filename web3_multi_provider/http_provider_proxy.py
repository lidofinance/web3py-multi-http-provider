import logging
from queue import Empty
from typing import Any, List, Optional, Tuple, Union, cast, override

from eth_typing import URI
from web3 import HTTPProvider, JSONBaseProvider
from web3._utils.batching import sort_batch_response_by_response_ids
from web3._utils.empty import empty
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

import web3_multi_provider.metrics as metrics
from web3_multi_provider.exceptions import ProviderInitialization
from web3_multi_provider.http_session_manager_proxy import HTTPSessionManagerProxy
from web3_multi_provider.metrics_decorator import (
    observe_batch_size,
    observe_input_payload,
    observe_output_payload,
    record_rpc_call,
)
from web3_multi_provider.util import normalize_provider

logger = logging.getLogger(__name__)


class HTTPProviderProxy(HTTPProvider):
    """
    A metrics-aware HTTP JSON-RPC provider for Ethereum-like nodes.

    This class extends `web3.HTTPProvider` and wraps core RPC functionality
    to track performance and usage metrics via Prometheus. It adds support
    for tracking request success/failure rates, payload sizes, and batch statistics.

    Attributes:
        _layer (str): Network layer (e.g. 'el' for Execution Layer).
        _uri (str): Normalized provider URI.
        _chain_id (str): Chain ID retrieved via `eth_chainId`.
        _network (str): Human-readable network name based on chain ID.
        _request_session_manager (HTTPSessionManagerProxy): Manages HTTP sessions per endpoint.
    """

    def __init__(
        self,
        endpoint_uri: Optional[Union[URI, str]] = None,
        request_kwargs: Optional[Any] = None,
        session: Optional[Any] = None,
        layer: str = "el",
        exception_retry_configuration: Optional[
            Union[ExceptionRetryConfiguration, Empty]
        ] = empty,
        **kwargs: Any,
    ) -> None:
        """
        Initializes the HTTPProviderProxy instance and fetches the chain ID.

        Args:
            endpoint_uri (Optional[Union[URI, str]]): URI of the Ethereum node.
            request_kwargs (Optional[Any]): Additional request parameters.
            session (Optional[Any]): Optional requests.Session object to reuse connections.
            layer (str): Network layer label ('el' by default).
            exception_retry_configuration (Optional[Union[ExceptionRetryConfiguration, Empty]]):
                Configuration for retry logic.
            **kwargs: Additional arguments passed to base class.
        """
        super().__init__(
            endpoint_uri,
            request_kwargs,
            session,
            exception_retry_configuration,
            **kwargs,
        )
        self._layer = layer
        self._uri = normalize_provider(self.endpoint_uri)
        self._chain_id = ""
        self._network = ""  # to pass fetching of the chain_id
        self._chain_id = str(self._fetch_chain_id())
        self._network = metrics._CHAIN_ID_TO_NAME.get(int(self._chain_id), "unknown")

        self._request_session_manager = HTTPSessionManagerProxy(
            chain_id=self._chain_id,
            uri=self._uri,
            network=self._network,
            layer=self._layer,
        )
        if session:
            self._request_session_manager.cache_and_return_session(
                self.endpoint_uri, session
            )

    def _fetch_chain_id(self) -> int:
        """
        Retrieves the chain ID from the connected Ethereum node.

        Returns:
            int: The chain ID as an integer.

        Raises:
            ProviderInitialization: If the chain ID could not be retrieved.
        """
        try:
            resp = super().make_request(RPCEndpoint("eth_chainId"), [])
            return int(resp["result"], 16)
        except Exception as e:
            raise ProviderInitialization("Failed to fetch chain ID") from e

    @override
    @record_rpc_call("_RPC_REQUEST")
    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        """
        Makes a JSON-RPC request and records request metrics.

        Args:
            method (RPCEndpoint): RPC method name.
            params (Any): RPC parameters.

        Returns:
            RPCResponse: The raw RPC response.

        Metrics:
            - `_RPC_REQUEST`: Incremented with status and error code (if any).
        """
        return super().make_request(method, params)

    @override
    @observe_output_payload("_RPC_SERVICE_REQUEST_PAYLOAD_BYTES")
    def encode_rpc_request(self, method: RPCEndpoint, params: Any) -> bytes:
        """
        Encodes a single RPC request and observes payload size.

        Args:
            method (RPCEndpoint): RPC method.
            params (Any): Parameters for the method.

        Returns:
            bytes: Encoded request.
        """
        return super().encode_rpc_request(method, params)

    @override
    @observe_output_payload("_RPC_SERVICE_REQUEST_PAYLOAD_BYTES")
    def encode_batch_rpc_request(
        self, requests: List[Tuple[RPCEndpoint, Any]]
    ) -> bytes:
        """
        Encodes a batch of RPC requests and observes total payload size.

        Args:
            requests (List[Tuple[RPCEndpoint, Any]]): List of method/params pairs.

        Returns:
            bytes: Encoded batch request.
        """
        return super().encode_batch_rpc_request(requests)

    @override
    @observe_input_payload("_RPC_SERVICE_RESPONSE_PAYLOAD_BYTES")
    def decode_rpc_response(self, raw_response: bytes) -> RPCResponse:
        """
        Decodes a raw HTTP response into a parsed RPC result.

        Args:
            raw_response (bytes): HTTP response content.

        Returns:
            RPCResponse: Decoded RPC response.
        """
        return JSONBaseProvider.decode_rpc_response(raw_response)

    @override
    @observe_batch_size("_HTTP_RPC_BATCH_SIZE")
    def make_batch_request(self, batch_requests: List[Tuple[RPCEndpoint, Any]]):
        """
        Sends a batch of RPC requests and returns sorted results.

        Args:
            batch_requests (List[Tuple[RPCEndpoint, Any]]): List of RPC method/param tuples.

        Returns:
            Union[List[RPCResponse], RPCResponse]: Decoded response(s).

        Metrics:
            - `_HTTP_RPC_BATCH_SIZE`: Observes batch size.
        """
        logger.debug(f"Making batch request HTTP, uri: `{self.endpoint_uri}`")
        request_data = self.encode_batch_rpc_request(batch_requests)
        raw_response = self._request_session_manager.make_post_request_batch(
            self.endpoint_uri, request_data, **self.get_request_kwargs()
        )
        logger.debug("Received batch response HTTP.")
        response = self.decode_rpc_response(raw_response)
        if not isinstance(response, list):
            return response
        return sort_batch_response_by_response_ids(cast(List[RPCResponse], response))
