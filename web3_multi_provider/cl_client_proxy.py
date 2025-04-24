from typing import Optional, Dict, Any, Union, List

from typing_extensions import override
from web3.beacon import Beacon

from http_session_manager_proxy import HTTPSessionManagerProxy
from util import normalize_provider


class BeaconProxy(Beacon):

    def __init__(self, base_url: str, request_timeout: float = 10.0):
        super().__init__(base_url, request_timeout)
        self._request_session_manager = HTTPSessionManagerProxy(
            chain_id='',
            uri=normalize_provider(self.base_url),
            network='ethereum',
            layer='cl',
        )

    @override
    def _make_get_request(
        self, endpoint_url: str, params: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        return super()._make_get_request(endpoint_url, params)

    @override
    def _make_post_request(
        self, endpoint_url: str, body: Union[List[str], Dict[str, Any]]
    ) -> Dict[str, Any]:
        return super()._make_post_request(endpoint_url, body)
