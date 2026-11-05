# pylint: disable=duplicate-code
import logging
from abc import ABC
from typing import Any, Callable, Iterable

from eth_typing import URI
from web3 import AsyncHTTPProvider
from web3._utils.empty import Empty, empty
from web3.providers.async_base import AsyncJSONBaseProvider
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

from web3_multi_provider.async_http_provider_proxy import AsyncHTTPProviderProxy
from web3_multi_provider.cooldown import is_endpoint_failure

# Re-exported: these were importable from this module before the failover core moved out.
from web3_multi_provider.exceptions import (  # pylint: disable=unused-import
    ChainIdMismatchError,
    NoActiveProviderError,
    ProtocolNotSupported,
)
from web3_multi_provider.failover import (
    EndpointSelector,
    InOrderSelector,
    RoundRobinSelector,
    build_failover,
)
from web3_multi_provider.metrics import warn_if_prometheus_not_initialized
from web3_multi_provider.util import ensure_http_endpoint

logger = logging.getLogger(__name__)


class AsyncBaseMultiProvider(AsyncJSONBaseProvider, ABC):
    """Base async provider for providers with multiple endpoints.

    Subclasses choose the endpoint order with `_selector_class`. With `cooldown_seconds`
    > 0, an endpoint that failed with an error for which `cooldown_on` is true is tried
    after the others until its cooldown ends.
    """

    _selector_class: type[EndpointSelector] = InOrderSelector
    _providers: list[AsyncHTTPProvider]

    def __init__(  # pylint: disable=too-many-arguments
        self,
        endpoint_urls: list[URI | str],
        request_kwargs: Any | None = None,
        exception_retry_configuration: (
            ExceptionRetryConfiguration | Empty | None
        ) = empty,
        *,
        cooldown_seconds: float = 0,
        cooldown_on: Callable[[Exception], bool] = is_endpoint_failure,
        **kwargs: Any,
    ):
        logger.debug({"msg": f"Initialize {self.__class__.__name__}"})
        warn_if_prometheus_not_initialized()
        self._hosts_uri = endpoint_urls
        self._providers = []

        if endpoint_urls:
            self.endpoint_uri = endpoint_urls[0]

        for endpoint_uri in endpoint_urls:
            ensure_http_endpoint(endpoint_uri)
            provider = AsyncHTTPProviderProxy(
                endpoint_uri=endpoint_uri,
                request_kwargs=request_kwargs,
                exception_retry_configuration=exception_retry_configuration,
                **kwargs,
            )
            self._providers.append(provider)

        self._failover = build_failover(
            self._providers,
            self._selector_class,
            cooldown_seconds,
            cooldown_on,
            logger,
        )
        super().__init__()

    def _validate_chain_ids(self) -> None:
        """Raise `ChainIdMismatchError` if the endpoints serve different chains."""
        self._failover.validate_chain_ids()

    def get_providers(self) -> Iterable[AsyncHTTPProvider]:
        """Endpoints in the order one request tries them.

        Called once per request: it advances the round-robin position and may start a
        cooldown probe.
        """
        return self._failover.plan()

    async def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        response = await self._make_request_with_failover(method, params)
        self._validate_chain_ids()
        return response

    async def _make_request_with_failover(
        self, method: RPCEndpoint, params: Any
    ) -> RPCResponse:
        with self._failover.attempt(self.__class__.__name__, method, params) as attempt:
            for provider in self.get_providers():
                try:
                    response = await provider.make_request(method, params)
                except Exception as error:  # pylint: disable=broad-except
                    attempt.failed(provider, error)
                else:
                    return attempt.succeeded(provider, response)
            raise attempt.exhausted()


class AsyncMultiProvider(AsyncBaseMultiProvider):
    """Round-robin: each request starts one endpoint further than the previous one, and
    fails over to the next endpoints in turn."""

    _selector_class = RoundRobinSelector


class AsyncFallbackProvider(AsyncBaseMultiProvider):
    """Fallback: every request tries the endpoints in the configured order."""

    _selector_class = InOrderSelector
