import logging
from typing import Any, List, Optional, Union

from eth_typing import URI
from web3 import HTTPProvider, WebsocketProvider
from web3._utils.rpc_abi import RPC
from web3.middleware.geth_poa import geth_poa_cleanup
from web3.types import RPCEndpoint, RPCResponse

logger = logging.getLogger(__name__)


class NoActiveProviderError(Exception):
    """Base exception if all providers are offline"""


class ProtocolNotSupported(Exception):
    """Supported protocols: http, https, ws, wss"""


class MultiProvider(HTTPProvider):
    """
    Provider that switches rpc endpoint to next if current is broken.
    """

    _http_providers: List[Union[HTTPProvider, WebsocketProvider]] = []
    _current_provider_index: int = 0
    _last_working_provider_index: int = 0

    def __init__(
        self,
        endpoint_urls: List[Union[URI, str]],
        request_kwargs: Optional[Any] = None,
        session: Optional[Any] = None,
        websocket_kwargs: Optional[Any] = None,
        websocket_timeout: Optional[Any] = None,
    ):
        logger.info({"msg": "Initialize MultiHTTPProvider"})
        self._hosts_uri = endpoint_urls
        self._http_providers = []

        for host_uri in endpoint_urls:
            if host_uri.startswith("ws"):
                self._http_providers.append(
                    WebsocketProvider(host_uri, websocket_kwargs, websocket_timeout)
                )
            elif host_uri.startswith("http"):
                self._http_providers.append(
                    HTTPProvider(host_uri, request_kwargs, session)
                )
            else:
                protocol = host_uri.split("://")[0]
                raise ProtocolNotSupported(f'Protocol "{protocol}" is not supported.')

        super().__init__(endpoint_urls[0], request_kwargs, session)

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        try:
            response = self._http_providers[self._current_provider_index].make_request(
                method, params
            )

            if method in (RPC.eth_getBlockByHash, RPC.eth_getBlockByNumber):
                if (
                    "result" in response
                    and "proofOfAuthorityData" not in response["result"]
                ):
                    response["result"] = geth_poa_cleanup(response["result"])

            logger.debug(
                {
                    "msg": "Send request using MultiProvider.",
                    "method": method,
                    "params": str(params),
                    "provider": self._http_providers[
                        self._current_provider_index
                    ].endpoint_uri,
                }
            )
            self._last_working_provider_index = self._current_provider_index
            return response

        except Exception as error:  # pylint: disable=W0703
            logger.warning(
                {
                    "msg": "Provider not responding.",
                    "error": str(error),
                    "provider": self._http_providers[
                        self._current_provider_index
                    ].endpoint_uri,
                }
            )

            self._current_provider_index = (self._current_provider_index + 1) % len(
                self._hosts_uri
            )

            if self._last_working_provider_index == self._current_provider_index:
                msg = "No active provider available."
                logger.error({"msg": msg})
                raise NoActiveProviderError(msg) from error

            return self.make_request(method, params)


class MultiHTTPProvider(MultiProvider):
    """
    Deprecated. Use MultiProvider instead
    """

    def __init__(
        self,
        endpoint_urls: List[Union[URI, str]],
        request_kwargs: Optional[Any] = None,
        session: Optional[Any] = None,
    ):
        import warnings

        warnings.warn(
            "MultiHTTPProvider is deprecated. Use MultiProvider instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(endpoint_urls, request_kwargs, session)
