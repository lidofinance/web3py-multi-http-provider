from queue import Empty
from typing import Optional, Union, Any, override

from eth_typing import URI
from web3 import JSONBaseProvider, AsyncHTTPProvider
from web3._utils.empty import empty
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

from web3_multi_provider.http_session_manager_proxy import HTTPSessionManagerProxy
from web3_multi_provider.metrics import RPC_SERVICE_REQUESTS, CHAIN_ID_TO_NAME, RPC_SERVICE_REQUEST_METHODS, \
    RPC_SERVICE_REQUEST_PAYLOAD_BYTES, RPC_SERVICE_RESPONSES_TOTAL_BYTES
from web3_multi_provider.util import normalize_provider


class AsyncHTTPProviderProxy(AsyncHTTPProvider):
    def __init__(
        self,
        endpoint_uri: Optional[Union[URI, str]] = None,
        request_kwargs: Optional[Any] = None,
        exception_retry_configuration: Optional[
            Union[ExceptionRetryConfiguration, Empty]
        ] = empty,
        **kwargs: Any,
    ) -> None:
        super().__init__(endpoint_uri, request_kwargs, exception_retry_configuration, **kwargs)
        self._network = None  # lazy init
        self._chain_id = None  # lazy init
        self._uri = normalize_provider(self.endpoint_uri)

    async def _fetch_chain_id(self) -> int:
        try:
            resp = await self.make_request(RPCEndpoint('eth_chainId'), [])
            return int(resp['result'], 16)
        except Exception as e:
            raise RuntimeError("Failed to fetch chain ID") from e

    @override
    async def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        if self._chain_id is None:
            self._chain_id = await self._fetch_chain_id()
            self._network = CHAIN_ID_TO_NAME.get(self._chain_id, 'unknown')
            self._request_session_manager = HTTPSessionManagerProxy(chain_id=self._chain_id, uri=self._uri, network=self._network)
        status = 'fail'
        try:
            result = await super().make_request(method, params)
            if 'error' not in result:
                status = 'success'
            return result
        finally:
            RPC_SERVICE_REQUESTS.labels(self._network, self._chain_id, self._uri, status)
            RPC_SERVICE_REQUEST_METHODS.labels(self._network, self._chain_id, self._uri, method, status)

    @override
    def encode_rpc_request(self, method: RPCEndpoint, params: Any) -> bytes:
        payload = super().encode_rpc_request(method, params)
        RPC_SERVICE_REQUEST_PAYLOAD_BYTES.labels(self._network, self._chain_id, self._uri).observe(len(payload))
        return payload

    @override
    def decode_rpc_response(self, raw_response: bytes) -> RPCResponse:
        RPC_SERVICE_RESPONSES_TOTAL_BYTES.labels(self._network, self._chain_id, self._uri).inc(len(raw_response))
        return JSONBaseProvider.decode_rpc_response(raw_response)
