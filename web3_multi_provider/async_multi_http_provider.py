# pylint: disable=duplicate-code
import logging
from abc import ABC, abstractmethod
from typing import Any, Iterable

from eth_typing import URI
from web3 import AsyncHTTPProvider
from web3._utils.empty import Empty, empty
from web3.providers.async_base import AsyncJSONBaseProvider
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

from web3_multi_provider.async_http_provider_proxy import AsyncHTTPProviderProxy
from web3_multi_provider.exceptions import NoActiveProviderError, ProtocolNotSupported
from web3_multi_provider.util import sanitize_poa_response

logger = logging.getLogger(__name__)


class AsyncBaseMultiProvider(AsyncJSONBaseProvider, ABC):
    """Base async provider for multiple endpoint handling strategies."""

    _providers: list[AsyncHTTPProvider]

    def __init__(  # pylint: disable=too-many-arguments
        self,
        endpoint_urls: list[URI | str],
        request_kwargs: Any | None = None,
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

            provider = AsyncHTTPProviderProxy(
                endpoint_uri=endpoint_uri,
                request_kwargs=request_kwargs,
                exception_retry_configuration=exception_retry_configuration,
                **kwargs,
            )
            self._providers.append(provider)

        super().__init__()

    async def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        return await self._make_request_with_failover(
            method=method,
            params=params,
            provider_name=self.__class__.__name__,
            provider_iter=self.get_providers(),
        )

    async def _make_request_with_failover(
        self,
        method: RPCEndpoint,
        params: Any,
        provider_name: str,
        provider_iter: Iterable[AsyncHTTPProvider],
    ) -> RPCResponse:
        exceptions: list[Exception] = []

        for provider in provider_iter:
            try:
                response = await provider.make_request(method, params)
            except Exception as error:  # pylint: disable=broad-except
                exceptions.append(error)
                logger.warning(
                    {
                        "msg": f"Provider not responding.",
                        "error": str(error).replace(str(provider.endpoint_uri), "****"),
                    }
                )
            else:
                sanitize_poa_response(method, response)
                logger.debug(
                    {
                        "msg": f"Send request using {provider_name}.",
                        "method": method,
                        "params": str(params),
                    }
                )
                return response

        msg = f"No active provider available in {provider_name}."
        logger.debug({"msg": msg})
        raise NoActiveProviderError.from_exceptions(msg, exceptions)

    @abstractmethod
    def get_providers(self) -> Iterable[AsyncHTTPProvider]:
        raise NotImplementedError


class AsyncMultiProvider(AsyncBaseMultiProvider):
    """Round-robin failover: rotates provider on failure."""

    _current_provider_index: int = 0

    def get_providers(self) -> Iterable[AsyncHTTPProvider]:
        count = len(self._providers)
        for _ in range(count):
            provider = self._providers[self._current_provider_index]
            self._current_provider_index = (self._current_provider_index + 1) % count
            yield provider


class AsyncFallbackProvider(AsyncBaseMultiProvider):
    """Simple fallback: tries providers in order."""

    def get_providers(self) -> Iterable[AsyncHTTPProvider]:
        return iter(self._providers)
