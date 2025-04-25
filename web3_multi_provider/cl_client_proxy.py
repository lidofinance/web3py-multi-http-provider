import sys
import web3_multi_provider.metrics as metrics
from typing import Optional, Dict, Any, Union, List

from typing_extensions import override
from web3.beacon import Beacon

from web3_multi_provider.http_session_manager_proxy import HTTPSessionManagerProxy
from web3_multi_provider.metrics_decorator import record_rpc_call
from web3_multi_provider.util import normalize_provider


class BeaconProxy(Beacon):
    """
        A proxy extension of the Web3 `Beacon` client that integrates Prometheus-based
        metrics collection for GET and POST RPC requests on the consensus layer.

        It tracks:
        - Number of requests (success/failure)
        - Request payload sizes (POST)
        - Response payload sizes (GET & POST)
        """

    def __init__(self, base_url: str, request_timeout: float = 10.0):
        """
        Initialize the BeaconProxy instance.

        Args:
            base_url (str): The HTTP endpoint URL of the Beacon (Consensus Layer) node.
            request_timeout (float, optional): Request timeout in seconds. Defaults to 10.0.
        """
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
        """
        Make a GET request to the beacon node and record metrics.

        Args:
            endpoint_url (str): Full endpoint URL to query.
            params (Optional[Dict[str, str]]): Query string parameters.

        Returns:
            Dict[str, Any]: Decoded JSON response from the node.

        Metrics:
            - Increments `_RPC_SERVICE_REQUESTS` with status and error code (if any).
            - Observes `_RPC_SERVICE_RESPONSE_PAYLOAD_BYTES` using `sys.getsizeof` on the response.
        """
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
        """
        Make a POST request to the beacon node and record metrics.

        Args:
            endpoint_url (str): Full endpoint URL to post to.
            body (Union[List[str], Dict[str, Any]]): JSON-serializable body of the request.

        Returns:
            Dict[str, Any]: Decoded JSON response from the node.

        Metrics:
            - Observes `_RPC_SERVICE_REQUEST_PAYLOAD_BYTES` using `sys.getsizeof` on the body.
            - Observes `_RPC_SERVICE_RESPONSE_PAYLOAD_BYTES` using `sys.getsizeof` on the response.
            - Increments `_RPC_SERVICE_REQUESTS` with status and error code (if any).
        """
        payload_size = sys.getsizeof(body)
        metrics._RPC_SERVICE_REQUEST_PAYLOAD_BYTES.labels(
            self._network, self._layer, self._chain_id, self._uri
        ).observe(payload_size)
        resp = super()._make_post_request(endpoint_url, body)
        metrics._RPC_SERVICE_RESPONSE_PAYLOAD_BYTES.labels(
            self._network, self._layer, self._chain_id, self._uri
        ).observe(sys.getsizeof(resp))
        return resp
