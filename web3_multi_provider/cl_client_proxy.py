import sys
import web3_multi_provider.metrics as metrics
from typing import Optional, Dict, Any, Union, List

from typing_extensions import override
from web3.beacon import Beacon

from web3_multi_provider.http_session_manager_proxy import HTTPSessionManagerProxy
from web3_multi_provider.metrics_decorator import record_rpc_call
from web3_multi_provider.util import normalize_provider


class BeaconProxy(Beacon):

    def __init__(self, base_url: str, request_timeout: float = 10.0):
        super().__init__(base_url, request_timeout)
        self._network = 'ethereum'
        self._layer = 'cl'
        self._chain_id = ''
        self._uri = normalize_provider(self.base_url)
        self._request_session_manager = HTTPSessionManagerProxy(
            chain_id='',
            uri=normalize_provider(self.base_url),
            network=self._network,
            layer=self._layer,
        )

    @override
    @record_rpc_call('_RPC_SERVICE_REQUESTS')
    def _make_get_request(
        self, endpoint_url: str, params: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        resp = super()._make_get_request(endpoint_url, params)
        metrics._RPC_SERVICE_RESPONSE_PAYLOAD_BYTES.labels(
            self._network, self._layer, self._chain_id, self._uri
        ).observe(sys.getsizeof(resp))
        return resp

    @override
    @record_rpc_call('_RPC_SERVICE_REQUESTS')
    def _make_post_request(
        self, endpoint_url: str, body: Union[List[str], Dict[str, Any]]
    ) -> Dict[str, Any]:
        payload_size = sys.getsizeof(body)
        metrics._RPC_SERVICE_REQUEST_PAYLOAD_BYTES.labels(
            self._network, self._layer, self._chain_id, self._uri
        ).observe(payload_size)
        resp = super()._make_post_request(endpoint_url, body)
        metrics._RPC_SERVICE_RESPONSE_PAYLOAD_BYTES.labels(
            self._network, self._layer, self._chain_id, self._uri
        ).observe(sys.getsizeof(resp))
        return resp
