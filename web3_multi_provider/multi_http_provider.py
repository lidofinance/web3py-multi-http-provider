import logging
from abc import ABC, abstractmethod
from typing import Any, Iterable

from eth_typing import URI
from web3 import HTTPProvider
from web3._utils.empty import Empty, empty
from web3.providers import JSONBaseProvider
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

from web3_multi_provider.exceptions import NoActiveProviderError, ProtocolNotSupported
from web3_multi_provider.http_provider_proxy import HTTPProviderProxy, ProviderInitialization
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
        exception_retry_configuration: ExceptionRetryConfiguration | Empty | None = empty,
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

        super().__init__()

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        return self._make_request_with_failover(
            method=method,
            params=params,
            provider_name=self.__class__.__name__,
            provider_iter=self.get_providers(),
        )

    @staticmethod
    def _make_request_with_failover(
        method: RPCEndpoint,
        params: Any,
        provider_name: str,
        provider_iter: Iterable[HTTPProvider],
    ) -> RPCResponse:
        exceptions: list[Exception] = []

        for provider in provider_iter:
            try:
                response = provider.make_request(method, params)
            except Exception as error:  # pylint: disable=broad-except
                exceptions.append(error)
                logger.warning({
                    "msg": f"Provider not responding.",
                    "error": str(error).replace(str(provider.endpoint_uri), "****"),
                })
            else:
                sanitize_poa_response(method, response)
                logger.debug({
                    "msg": f"Send request using {provider_name}.",
                    "method": method,
                    "params": str(params),
                })
                return response

        msg = f"No active provider available in {provider_name}."
        logger.debug({"msg": msg})
        raise NoActiveProviderError.from_exceptions(msg, exceptions)

    @abstractmethod
    def get_providers(self) -> Iterable[HTTPProvider]:
        raise NotImplementedError


class MultiProvider(BaseMultiProvider):
    """
    Provider that switches RPC endpoint to next if current is broken (round-robin).
    """

    _current_provider_index: int = 0

    def get_providers(self) -> Iterable[HTTPProvider]:
        count = len(self._providers)
        for _ in range(count):
            provider = self._providers[self._current_provider_index]
            self._current_provider_index = (self._current_provider_index + 1) % count
            yield provider


class FallbackProvider(BaseMultiProvider):
    """Basic fallback provider: tries each provider once, in order."""

    def get_providers(self) -> Iterable[HTTPProvider]:
        return iter(self._providers)
