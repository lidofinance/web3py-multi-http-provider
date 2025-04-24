import logging
from queue import Empty
from typing import Optional, Union, Any, override, List, Tuple, cast

from eth_typing import URI
from web3 import HTTPProvider, JSONBaseProvider
from web3._utils.batching import sort_batch_response_by_response_ids
from web3._utils.empty import empty
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

import web3_multi_provider.metrics as metrics
from web3_multi_provider.exceptions import ProviderInitialization
from web3_multi_provider.http_session_manager_proxy import HTTPSessionManagerProxy
from web3_multi_provider.util import normalize_provider

logger = logging.getLogger(__name__)


class HTTPProviderProxy(HTTPProvider):
    def __init__(
        self,
        endpoint_uri: Optional[Union[URI, str]] = None,
        request_kwargs: Optional[Any] = None,
        session: Optional[Any] = None,
        layer: str = 'el',
        exception_retry_configuration: Optional[
            Union[ExceptionRetryConfiguration, Empty]
        ] = empty,
        **kwargs: Any,
    ) -> None:
        super().__init__(endpoint_uri, request_kwargs, session, exception_retry_configuration, **kwargs)
        self._uri = normalize_provider(self.endpoint_uri)
        self._chain_id = self._fetch_chain_id()
        self._network = metrics._CHAIN_ID_TO_NAME.get(self._chain_id, 'unknown')
        self._chain_id = str(self._chain_id)
        self._request_session_manager = HTTPSessionManagerProxy(chain_id=self._chain_id, uri=self._uri, network=self._network, layer='el')
        self._layer = layer
        if session:
            self._request_session_manager.cache_and_return_session(self.endpoint_uri, session)

    def _fetch_chain_id(self) -> int:
        try:
            resp = super().make_request(RPCEndpoint('eth_chainId'), [])
            return int(resp['result'], 16)
        except Exception as e:
            raise ProviderInitialization("Failed to fetch chain ID") from e

    @override
    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        status = 'fail'
        error_code = ''
        try:
            result = super().make_request(method, params)
            if 'error' in result and 'code' in result['error']:
                error_code = result['error']['code']
            if 'error' not in result:
                status = 'success'
            return result
        finally:
            metrics._RPC_SERVICE_REQUESTS.labels(self._network, self._layer, self._chain_id, self._uri, method, status, error_code).inc()

    @override
    def encode_rpc_request(self, method: RPCEndpoint, params: Any) -> bytes:
        payload = super().encode_rpc_request(method, params)
        metrics._RPC_SERVICE_REQUEST_PAYLOAD_BYTES.labels(self._network, self._layer, self._chain_id, self._uri).observe(len(payload))
        return payload

    @override
    def encode_batch_rpc_request(self, requests: List[Tuple[RPCEndpoint, Any]]) -> bytes:
        payload = super().encode_batch_rpc_request(requests)
        metrics._RPC_SERVICE_REQUEST_PAYLOAD_BYTES.labels(self._network, self._layer, self._chain_id, self._uri).observe(len(payload))
        return payload

    @override
    def decode_rpc_response(self, raw_response: bytes) -> RPCResponse:
        metrics._RPC_SERVICE_RESPONSE_PAYLOAD_BYTES.labels(self._network, self._layer, self._chain_id, self._uri).observe(len(raw_response))
        return JSONBaseProvider.decode_rpc_response(raw_response)

    @override
    def make_batch_request(self, batch_requests: List[Tuple[RPCEndpoint, Any]]):
        try:
            logger.debug(f"Making batch request HTTP, uri: `{self.endpoint_uri}`")
            request_data = self.encode_batch_rpc_request(batch_requests)
            raw_response = self._request_session_manager.make_post_request_batch(
                self.endpoint_uri, request_data, **self.get_request_kwargs()
            )
            logger.debug("Received batch response HTTP.")
            response = self.decode_rpc_response(raw_response)
            if not isinstance(response, list):
                # RPC errors return only one response with the error object
                return response
            return sort_batch_response_by_response_ids(
                cast(List[RPCResponse], sort_batch_response_by_response_ids(response))
            )
        finally:
            metrics._HTTP_RPC_BATCH_SIZE.labels(self._network, self._layer, self._chain_id, self._uri).observe(len(batch_requests))
