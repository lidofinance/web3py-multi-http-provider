import logging
from typing import Any, List, Optional, Tuple, Union, cast, override

from eth_typing import URI
from web3 import HTTPProvider
from web3._utils.batching import sort_batch_response_by_response_ids
from web3._utils.empty import Empty, empty
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

from web3_multi_provider import metrics
from web3_multi_provider.exceptions import ProviderInitialization
from web3_multi_provider.http_session_manager_proxy import HTTPSessionManagerProxy
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
        self._uri = normalize_provider(str(self.endpoint_uri))
        self._chain_id = ""
        self._network = ""  # to pass fetching of the chain_id
        self._chain_id = str(self._fetch_chain_id())
        self._network = metrics._CHAIN_ID_TO_NAME.get(int(self._chain_id), "unknown")

        self._request_session_manager: HTTPSessionManagerProxy = (
            HTTPSessionManagerProxy(
                chain_id=self._chain_id,
                uri=self._uri,
                network=self._network,
                layer=self._layer,
            )
        )
        if session:
            self._request_session_manager.cache_and_return_session(
                cast(URI, self.endpoint_uri), session
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

    def make_batch_request(
        self, batch_requests: List[Tuple[RPCEndpoint, Any]]
    ) -> Union[List[RPCResponse], RPCResponse]:
        self.logger.debug(f"Making batch request HTTP, uri: `{self.endpoint_uri}`")
        request_data = self.encode_batch_rpc_request(batch_requests)
        raw_response = self._request_session_manager.make_post_request(
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
