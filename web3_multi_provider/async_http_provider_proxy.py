import logging
from queue import Empty
from typing import Any, cast, List, Optional, override, Tuple, Union

from eth_typing import URI
from web3 import AsyncHTTPProvider, JSONBaseProvider
from web3._utils.batching import sort_batch_response_by_response_ids
from web3._utils.empty import empty
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

import web3_multi_provider.metrics as metrics
from web3_multi_provider.http_session_manager_proxy import HTTPSessionManagerProxy
from web3_multi_provider.metrics_decorator import observe_batch_size, observe_input_payload, observe_output_payload, record_rpc_call
from web3_multi_provider.util import normalize_provider

logger = logging.getLogger(__name__)


class AsyncHTTPProviderProxy(AsyncHTTPProvider):
    """
    An asynchronous extension of Web3's AsyncHTTPProvider that adds Prometheus metrics tracking.

    This proxy handles request success/failure tracking, request and response payload size observation,
    and lazy chain ID initialization to tag metrics with network-specific labels.

    Metrics collected include:
    - RPC call success/failure counts
    - Request payload sizes
    - Response payload sizes
    - Batch request sizes
    """

    def __init__(
        self,
        endpoint_uri: Optional[Union[URI, str]] = None,
        request_kwargs: Optional[Any] = None,
        layer: str = 'el',
        exception_retry_configuration: Optional[
            Union[ExceptionRetryConfiguration, Empty]
        ] = empty,
        **kwargs: Any,
    ) -> None:
        """
        Initializes the asynchronous provider with metric tagging metadata.

        Args:
            endpoint_uri (Optional[Union[URI, str]]): The Ethereum RPC endpoint URI.
            request_kwargs (Optional[Any]): Extra request arguments.
            layer (str): The blockchain layer (e.g., 'el' for Execution Layer).
            exception_retry_configuration (Optional): Configuration for retry behavior.
            **kwargs: Additional arguments passed to the base class.
        """
        super().__init__(endpoint_uri, request_kwargs, exception_retry_configuration, **kwargs)
        self._chain_id: Optional[int] = None
        self._network: Optional[str] = None
        self._uri: str = normalize_provider(self.endpoint_uri)
        self._layer = layer

    async def _ensure_chain_info_initialized(self) -> None:
        """
        Lazily fetches chain ID and maps it to a network name for metric labeling.
        Also sets up the request session manager for batch requests.
        """
        if self._chain_id is not None:
            return
        self._chain_id = await self._fetch_chain_id()
        self._network = metrics._CHAIN_ID_TO_NAME.get(self._chain_id, 'unknown')
        self._request_session_manager = HTTPSessionManagerProxy(
            chain_id=self._chain_id,
            uri=self._uri,
            network=self._network,
            layer=self._layer
        )

    async def _fetch_chain_id(self) -> int:
        """
        Makes an RPC call to retrieve the Ethereum chain ID.

        Returns:
            int: The current chain ID.

        Raises:
            RuntimeError: If the call to `eth_chainId` fails.
        """
        try:
            resp = await super().make_request(RPCEndpoint('eth_chainId'), [])
            return int(resp['result'], 16)
        except Exception as e:
            raise RuntimeError('Failed to fetch chain ID') from e

    @override
    @record_rpc_call('_RPC_SERVICE_REQUESTS')
    async def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        """
        Makes an async JSON-RPC request, tagging metrics with status and error code.

        Args:
            method (RPCEndpoint): The RPC method to call.
            params (Any): Parameters for the method.

        Returns:
            RPCResponse: The decoded response.
        """
        await self._ensure_chain_info_initialized()
        return await super().make_request(method, params)

    @override
    @observe_output_payload('_RPC_SERVICE_REQUEST_PAYLOAD_BYTES')
    def encode_rpc_request(self, method: RPCEndpoint, params: Any) -> bytes:
        """
        Encodes a single RPC request into bytes and observes its size.

        Args:
            method (RPCEndpoint): The method name.
            params (Any): Parameters to encode.

        Returns:
            bytes: The encoded request.
        """
        return super().encode_rpc_request(method, params)

    @override
    @observe_output_payload('_RPC_SERVICE_REQUEST_PAYLOAD_BYTES')
    def encode_batch_rpc_request(self, requests: List[Tuple[RPCEndpoint, Any]]) -> bytes:
        """
        Encodes a list of RPC requests into a batch payload and observes size.

        Args:
            requests (List[Tuple[RPCEndpoint, Any]]): RPC method/param pairs.

        Returns:
            bytes: Encoded batch request.
        """
        return super().encode_batch_rpc_request(requests)

    @override
    @observe_input_payload('_RPC_SERVICE_RESPONSE_PAYLOAD_BYTES')
    def decode_rpc_response(self, raw_response: bytes) -> RPCResponse:
        """
        Decodes a raw byte response into a structured JSON-RPC response and records response size.

        Args:
            raw_response (bytes): Raw HTTP response content.

        Returns:
            RPCResponse: Parsed RPC response.
        """
        return JSONBaseProvider.decode_rpc_response(raw_response)

    @override
    @observe_batch_size('_HTTP_RPC_BATCH_SIZE')
    async def make_batch_request(
        self, batch_requests: List[Tuple[RPCEndpoint, Any]]
    ) -> Union[List[RPCResponse], RPCResponse]:
        """
        Makes a batched RPC request and records batch size and metrics.

        Args:
            batch_requests (List[Tuple[RPCEndpoint, Any]]): A list of RPC method/param pairs.

        Returns:
            Union[List[RPCResponse], RPCResponse]: A sorted list of RPC responses or a single error response.
        """
        await self._ensure_chain_info_initialized()
        logger.debug(f"Making batch request HTTP - uri: `{self.endpoint_uri}`")
        request_data = self.encode_batch_rpc_request(batch_requests)
        raw_response = await self._request_session_manager.async_make_post_request_batch(
            self.endpoint_uri,
            request_data,
            **self.get_request_kwargs()
        )
        logger.debug("Received batch response HTTP.")
        response = self.decode_rpc_response(raw_response)
        if not isinstance(response, list):
            return response
        return sort_batch_response_by_response_ids(
            cast(List[RPCResponse], response)
        )

