from typing import Optional, Dict, Any, Union, List

from typing_extensions import override
from web3.beacon import Beacon

import web3_multi_provider.metrics as metrics
from http_session_manager_proxy import HTTPSessionManagerProxy
from util import normalize_provider


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
    def _make_get_request(
        self, endpoint_url: str, params: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        status = 'failure'
        error_code = ''
        method = endpoint_url.removeprefix(self.base_url)
        try:
            result = super()._make_get_request(endpoint_url, params)
            if 'error' in result and 'code' in result['error']:
                error_code = result['error']['code']
            if 'error' not in result:
                status = 'success'
            return result
        finally:
            metrics._RPC_SERVICE_REQUESTS.labels(self._network, self._layer, self._chain_id, self._uri, method, status, error_code).inc()

    @override
    def _make_post_request(
        self, endpoint_url: str, body: Union[List[str], Dict[str, Any]]
    ) -> Dict[str, Any]:
        status = 'failure'
        error_code = ''
        method = endpoint_url.removeprefix(self.base_url)
        try:
            result = super()._make_get_request(endpoint_url, body)
            if 'error' in result and 'code' in result['error']:
                error_code = result['error']['code']
            if 'error' not in result:
                status = 'success'
            return result
        finally:
            metrics._RPC_SERVICE_REQUESTS.labels(self._network, self._layer, self._chain_id, self._uri, method, status, error_code).inc()
