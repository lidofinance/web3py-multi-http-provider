import logging
from abc import ABC
from typing import Any

from eth_typing import URI
from web3 import HTTPProvider
from web3._utils.empty import Empty, empty
from web3.providers import JSONBaseProvider
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

from http_provider_proxy import HTTPProviderProxy, ProviderInitialization
from web3_multi_provider.exceptions import NoActiveProviderError, ProtocolNotSupported
from web3_multi_provider.util import sanitize_poa_response

logger = logging.getLogger(__name__)


class BaseMultiProvider(JSONBaseProvider, ABC):
    """Base provider for providers with multiple endpoints"""

    _providers: list[HTTPProvider] = []

    def __init__(  # pylint: disable=too-many-arguments
        self,
        endpoint_urls: list[URI | str],
        request_kwargs: Any | None = None,
        session: Any | None = None,
        exception_retry_configuration: (
            ExceptionRetryConfiguration | Empty | None
        ) = empty,
        **kwargs: Any,
    ):
        logger.debug({"msg": f"Initialize {self.__class__.__name__}"})
        self._hosts_uri = endpoint_urls
        self._providers = []

        if endpoint_urls:
            self.endpoint_uri = endpoint_urls[0]

        for endpoint_uri in endpoint_urls:
            if not endpoint_uri.startswith("http"):
                protocol = endpoint_uri.split("://")[0]
                raise ProtocolNotSupported(f'Protocol "{protocol}" is not supported.')

            try:
                provider = HTTPProviderProxy(
                    endpoint_uri=endpoint_uri,
                    request_kwargs=request_kwargs,
                    session=session,
                    exception_retry_configuration=exception_retry_configuration,
                    **kwargs,
                )
                self._providers.append(provider)
            except ProviderInitialization as e:
                logger.error({
                    "msg": "Failed to initialize a provider",
                    "error": str(e).replace(str(endpoint_uri), "****"),
                })
                continue
        super().__init__()


class MultiProvider(BaseMultiProvider):
    """
    Provider that switches rpc endpoint to next if current is broken.
    """

    _current_provider_index: int = 0

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        providers_count = len(self._providers)

        for _ in range(providers_count):
            active_provider = self._providers[self._current_provider_index]

            try:
                response = active_provider.make_request(method, params)
            except Exception as error:  # pylint: disable=broad-except
                self._current_provider_index = (
                                                   self._current_provider_index + 1
                                               ) % providers_count
                logger.warning(
                    {
                        "msg": "Provider not responding.",
                        "error": str(error).replace(
                            str(active_provider.endpoint_uri), "****"
                        ),
                    }
                )
            else:
                sanitize_poa_response(method, response)

                logger.debug(
                    {
                        "msg": "Send request using MultiProvider.",
                        "method": method,
                        "params": str(params),
                    }
                )
                return response

        msg = "No active provider available."
        logger.debug({"msg": msg})
        raise NoActiveProviderError(msg)


class FallbackProvider(BaseMultiProvider):
    """Basic fallback provider"""

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        for provider in self._providers:
            try:
                response = provider.make_request(method, params)
            except Exception as error:  # pylint: disable=broad-except
                logger.warning(
                    {
                        "msg": "Provider not responding.",
                        "error": str(error).replace(str(provider.endpoint_uri), "****"),
                    }
                )
            else:
                sanitize_poa_response(method, response)

                logger.debug(
                    {
                        "msg": "Send request using FallbackProvider.",
                        "method": method,
                        "params": str(params),
                    }
                )
                return response

        msg = "No active provider available."
        logger.debug({"msg": msg})
        raise NoActiveProviderError(msg)
