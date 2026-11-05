import logging
from abc import ABC, abstractmethod
from typing import Any, Iterable

from eth_typing import URI
from web3 import HTTPProvider
from web3._utils.empty import Empty, empty
from web3.providers import JSONBaseProvider
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint, RPCResponse

from web3_multi_provider.cooldown import ProviderCooldown
from web3_multi_provider.exceptions import (
    ChainIdMismatchError,
    NoActiveProviderError,
    ProtocolNotSupported,
)
from web3_multi_provider.http_provider_proxy import HTTPProviderProxy
from web3_multi_provider.metrics import warn_if_prometheus_not_initialized
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
        warn_if_prometheus_not_initialized()
        self._hosts_uri = endpoint_urls
        self._providers = []

        if endpoint_urls:
            self.endpoint_uri = endpoint_urls[0]

        for endpoint_uri in endpoint_urls:
            if not endpoint_uri.startswith("http"):
                protocol = endpoint_uri.split("://")[0]
                raise ProtocolNotSupported(f'Protocol "{protocol}" is not supported.')

            provider = HTTPProviderProxy(
                endpoint_uri=endpoint_uri,
                request_kwargs=request_kwargs,
                session=session,
                exception_retry_configuration=exception_retry_configuration,
                **kwargs,
            )
            self._providers.append(provider)

        super().__init__()

    def _validate_chain_ids(self) -> None:
        """
        Validates that all providers have the same chain ID.

        Raises:
            ChainIdMismatchError: If providers have different chain IDs.
        """
        chain_ids: dict[str, list[str]] = {}

        for provider in self._providers:
            if hasattr(provider, "_chain_id") and provider._chain_id:
                chain_id = provider._chain_id
                endpoint_uri = str(provider.endpoint_uri)

                if chain_id not in chain_ids:
                    chain_ids[chain_id] = []
                chain_ids[chain_id].append(endpoint_uri)

        if len(chain_ids) > 1:
            mismatches = []
            for chain_id, endpoints in chain_ids.items():
                mismatches.append(f"Chain ID {chain_id}: {', '.join(endpoints)}")

            raise ChainIdMismatchError(
                f"Providers have different chain IDs:\n" + "\n".join(mismatches)
            )

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        response = self._make_request_with_failover(
            method=method,
            params=params,
            provider_name=self.__class__.__name__,
            provider_iter=self.get_providers(),
        )
        self._validate_chain_ids()
        return response

    def _make_request_with_failover(  # pylint: disable=inconsistent-return-statements
        self,
        method: RPCEndpoint,
        params: Any,
        provider_name: str,
        provider_iter: Iterable[HTTPProvider],
    ) -> RPCResponse:
        exceptions: list[Exception] = []
        try:
            for provider in provider_iter:
                index = self._endpoint_index(provider)
                try:
                    response = provider.make_request(method, params)
                except Exception as error:  # pylint: disable=broad-except
                    exceptions.append(error)
                    logger.warning(
                        {
                            "msg": "Provider not responding.",
                            "index": index,
                            "error": str(error).replace(
                                str(provider.endpoint_uri), "****"
                            ),
                        }
                    )
                    self._on_provider_failure(index)
                else:
                    self._on_provider_success(index)
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
        finally:
            # Break explicitly a reference cycle, as socket.create_connection does
            exceptions.clear()

    def _endpoint_index(self, provider: HTTPProvider) -> int:
        """Position of `provider` in the configured endpoint list, for logs and cooldowns.

        `get_providers` may reorder endpoints, so the position in the iteration is not it.
        """
        return next(i for i, p in enumerate(self._providers) if p is provider)

    def _on_provider_failure(self, index: int) -> None:
        """Called after the endpoint at `index` raised on a request."""

    def _on_provider_success(self, index: int) -> None:
        """Called after the endpoint at `index` answered a request."""

    @abstractmethod
    def get_providers(self) -> Iterable[HTTPProvider]:
        raise NotImplementedError


class MultiProvider(BaseMultiProvider):
    """
    Provider that switches RPC endpoint to next if current is broken (round-robin).
    """

    _current_provider_index: int = 0

    def get_providers(self) -> Iterable[HTTPProvider]:
        """Iterate providers in a round-robin sequence."""
        count = len(self._providers)
        for _ in range(count):
            provider = self._providers[self._current_provider_index]
            self._current_provider_index = (self._current_provider_index + 1) % count
            yield provider


class FallbackProvider(BaseMultiProvider):
    """Fallback provider: tries each provider once, in order.

    With `cooldown_seconds` > 0, a provider that failed is tried after the others until its
    cooldown ends.
    """

    def __init__(self, *args: Any, cooldown_seconds: float = 0, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._cooldown = ProviderCooldown(cooldown_seconds)

    def get_providers(self) -> Iterable[HTTPProvider]:
        if not self._cooldown.enabled:
            return iter(self._providers)
        return [self._providers[i] for i in self._cooldown.order(len(self._providers))]

    def _on_provider_failure(self, index: int) -> None:
        self._cooldown.mark_failed(index)

    def _on_provider_success(self, index: int) -> None:
        self._cooldown.mark_succeeded(index)
