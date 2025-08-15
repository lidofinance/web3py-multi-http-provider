import logging
from typing import Any, List, Optional, Tuple, Union, cast, override

from eth_typing import URI
from web3 import AsyncHTTPProvider
from web3._utils.batching import sort_batch_response_by_response_ids
from web3._utils.empty import Empty, empty
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

from web3_multi_provider import metrics
from web3_multi_provider.http_session_manager_proxy import HTTPSessionManagerProxy
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
        layer: str = "el",
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
        super().__init__(
            endpoint_uri, request_kwargs, exception_retry_configuration, **kwargs
        )
        self._chain_id: str = ""
        self._network: str = ""  # to pass fetching of the chain_id
        self._uri: str = normalize_provider(str(self.endpoint_uri))
        self._layer = layer

    async def _ensure_chain_info_initialized(self) -> None:
        """
        Lazily fetches chain ID and maps it to a network name for metric labeling.
        Also sets up the request session manager for batch requests.
        """
        if self._chain_id != "":
            return
        self._chain_id = str(await self._fetch_chain_id())
        self._network = metrics._CHAIN_ID_TO_NAME.get(int(self._chain_id), "unknown")
        self._request_session_manager: HTTPSessionManagerProxy = (
            HTTPSessionManagerProxy(
                chain_id=self._chain_id,
                uri=self._uri,
                network=self._network,
                layer=self._layer,
            )
        )

    async def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        await self._ensure_chain_info_initialized()
        return await super().make_request(method, params)

    async def _fetch_chain_id(self) -> int:
        """
        Makes an RPC call to retrieve the Ethereum chain ID.

        Returns:
            int: The current chain ID.

        Raises:
            RuntimeError: If the call to `eth_chainId` fails.
        """
        try:
            resp = await super().make_request(RPCEndpoint("eth_chainId"), [])
            return int(resp["result"], 16)
        except Exception as e:
            raise RuntimeError("Failed to fetch chain ID") from e

    async def make_batch_request(
        self, batch_requests: List[Tuple[RPCEndpoint, Any]]
    ) -> Union[List[RPCResponse], RPCResponse]:
        await self._ensure_chain_info_initialized()
        self.logger.debug(f"Making batch request HTTP - uri: `{self.endpoint_uri}`")
        request_data = self.encode_batch_rpc_request(batch_requests)
        raw_response = await self._request_session_manager.async_make_post_request(
            self.endpoint_uri,
            request_data,
            _batch_size=len(batch_requests),
            **self.get_request_kwargs(),
        )
        self.logger.debug("Received batch response HTTP.")
        response = self.decode_rpc_response(raw_response)
        if not isinstance(response, list):
            # RPC errors return only one response with the error object
            return response
        return sort_batch_response_by_response_ids(
            cast(List[RPCResponse], sort_batch_response_by_response_ids(response))
        )
