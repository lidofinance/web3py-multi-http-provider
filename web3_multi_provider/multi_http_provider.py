import logging
from typing import Any, List, Optional, Union

from eth_typing import URI
from web3 import HTTPProvider
from web3.types import RPCEndpoint, RPCResponse

logger = logging.getLogger(__name__)


class NoActiveProvider(Exception):
    """Base exception if all providers are offline"""


class MultiHTTPProvider(HTTPProvider):
    """
    Provider that switches rpc endpoint if default one is broken.

    Does not support subscriptions for now.
    """

    _http_providers: List[HTTPProvider] = []
    _current_provider_index: int = 0
    _last_working_provider_index: int = 0

    def __init__(
        self,
        endpoint_urls: List[Union[URI, str]],
        request_kwargs: Optional[Any] = None,
        session: Optional[Any] = None,
    ):
        self._hosts_uri = endpoint_urls
        self._http_providers = [
            HTTPProvider(host_uri, request_kwargs, session)
            for host_uri in endpoint_urls
        ]

        super().__init__(endpoint_urls[0], request_kwargs, session)

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        try:
            response = self._http_providers[self._current_provider_index].make_request(
                method, params
            )
            logger.info(
                {
                    "msg": "Send request using MultiHTTPProvider.",
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
                raise NoActiveProvider(msg) from error

            return self.make_request(method, params)
