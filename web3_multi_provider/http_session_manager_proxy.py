from typing import Any

import requests
from aiohttp import ClientResponse
from eth_typing import URI
from web3._utils.http_session_manager import HTTPSessionManager

from metrics import RPC_SERVICE_RESPONSE


class HTTPSessionManagerProxy(HTTPSessionManager):
    def __init__(self, chain_id: int | str, uri: str, network: str, cache_size: int = 100, session_pool_max_workers: int = 5):
        super().__init__(cache_size, session_pool_max_workers)
        self._chain_id = str(chain_id)
        self._uri = uri
        self._network = network

    def get_response_from_get_request(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> requests.Response:
        with RPC_SERVICE_RESPONSE.time() as t:
            response = super().get_response_from_get_request(endpoint_uri, args, kwargs)
            t.labels(self._network, self._chain_id, self._uri, str(response.status_code))
            return response

    def get_response_from_post_request(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> requests.Response:
        with RPC_SERVICE_RESPONSE.time() as t:
            response = super().get_response_from_post_request(endpoint_uri, args, kwargs)
            t.labels(self._network, self._chain_id, self._uri, str(response.status_code))
            return response

    async def async_get_response_from_get_request(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> ClientResponse:
        with RPC_SERVICE_RESPONSE.time() as t:
            response = await super().async_get_response_from_get_request(endpoint_uri, args, kwargs)
            t.labels(self._network, self._chain_id, self._uri, str(response.status))
            return response

    async def async_get_response_from_post_request(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> ClientResponse:
        with RPC_SERVICE_RESPONSE.time() as t:
            response = await super().async_get_response_from_post_request(endpoint_uri, args, kwargs)
            t.labels(self._network, self._chain_id, self._uri, str(response.status))
            return response
