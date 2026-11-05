"""The I/O-free part of failover, shared by the sync and async providers."""

# Selectors are strategies with a single method by design.
# pylint: disable=too-few-public-methods

import logging
import threading
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any, Callable, Generic, Protocol, Sequence, TypeVar

from web3.types import RPCEndpoint, RPCResponse

from web3_multi_provider.cooldown import ProviderCooldown
from web3_multi_provider.exceptions import ChainIdMismatchError, NoActiveProviderError
from web3_multi_provider.util import sanitize_poa_response


class EndpointSelector(ABC):
    """Order in which a request tries the endpoints.

    Implementations do no I/O and are thread-safe, so the sync and async providers share
    them.
    """

    def __init__(self, count: int):
        self._count = count

    @abstractmethod
    def order(self) -> list[int]:
        """Endpoint indexes for one request. Called once per request."""


class InOrderSelector(EndpointSelector):
    """Every request starts from the first endpoint."""

    def order(self) -> list[int]:
        return list(range(self._count))


class RoundRobinSelector(EndpointSelector):
    """Each request starts one endpoint further than the previous one."""

    def __init__(self, count: int):
        super().__init__(count)
        self._lock = threading.Lock()
        self._next = 0

    def order(self) -> list[int]:
        if not self._count:
            return []
        with self._lock:
            start = self._next
            self._next = (start + 1) % self._count
        return [(start + offset) % self._count for offset in range(self._count)]


class _Endpoint(Protocol):
    @property
    def endpoint_uri(self) -> Any:
        """URL the endpoint sends requests to."""


P = TypeVar("P", bound=_Endpoint)


def build_failover(  # pylint: disable=too-many-arguments
    providers: Sequence[P],
    selector_class: type[EndpointSelector],
    cooldown_seconds: float,
    cooldown_on: Callable[[Exception], bool],
    logger: logging.Logger,
) -> "Failover[P]":
    """Failover over `providers`, with endpoint metrics labelled like the HTTP metrics."""
    labels = [getattr(p, "_uri", str(i)) for i, p in enumerate(providers)]
    cooldown = ProviderCooldown(cooldown_seconds, labels, is_failure=cooldown_on)
    return Failover(providers, selector_class(len(providers)), cooldown, logger)


class Failover(Generic[P]):
    """Which endpoints a request tries, in which order, and what it learns from each try."""

    def __init__(
        self,
        providers: Sequence[P],
        selector: EndpointSelector,
        cooldown: ProviderCooldown,
        logger: logging.Logger,
    ):
        # The provider owns `providers` and may change its items; keep the same list.
        self.providers = providers
        self.selector = selector
        self.cooldown = cooldown
        self.logger = logger

    def plan(self) -> list[P]:
        """Endpoints in the order one request tries them.

        Call it once per request: it advances the round-robin position and may start a
        cooldown probe.
        """
        order = self.cooldown.reorder(self.selector.order())
        return [self.providers[index] for index in order]

    def attempt(
        self, provider_name: str, method: RPCEndpoint, params: Any
    ) -> "FailoverAttempt[P]":
        """Bookkeeping for one request. Use it as a context manager."""
        return FailoverAttempt(self, provider_name, method, params)

    def index_of(self, provider: P) -> int:
        """Position of `provider` in the configured endpoint list.

        The plan reorders endpoints, so the position in the plan is not it.
        """
        for index, configured in enumerate(self.providers):
            if configured is provider:
                return index
        raise ValueError("get_providers() returned an endpoint that is not configured.")

    def validate_chain_ids(self) -> None:
        """Raise `ChainIdMismatchError` if the endpoints serve different chains."""
        chain_ids: dict[str, list[str]] = {}
        for provider in self.providers:
            chain_id = getattr(provider, "_chain_id", "")
            if chain_id:
                chain_ids.setdefault(chain_id, []).append(str(provider.endpoint_uri))

        if len(chain_ids) > 1:
            mismatches = [
                f"Chain ID {chain_id}: {', '.join(endpoints)}"
                for chain_id, endpoints in chain_ids.items()
            ]
            raise ChainIdMismatchError(
                "Providers have different chain IDs:\n" + "\n".join(mismatches)
            )


class FailoverAttempt(Generic[P]):
    """One request across endpoints: logs each try and reports it to the cooldown."""

    def __init__(
        self,
        failover: Failover[P],
        provider_name: str,
        method: RPCEndpoint,
        params: Any,
    ):
        self._failover = failover
        self._provider_name = provider_name
        self._method = method
        self._params = params
        self._errors: list[Exception] = []

    def __enter__(self) -> "FailoverAttempt[P]":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Break explicitly a reference cycle, as socket.create_connection does
        self._errors.clear()

    def failed(self, provider: P, error: Exception) -> None:
        """Record that `provider` raised `error`."""
        index = self._failover.index_of(provider)
        self._errors.append(error)
        self._failover.logger.warning(
            {
                "msg": "Provider not responding.",
                "index": index,
                "error": str(error).replace(str(provider.endpoint_uri), "****"),
            }
        )
        self._failover.cooldown.mark_failed(index, error)

    def succeeded(self, provider: P, response: RPCResponse) -> RPCResponse:
        """Record that `provider` answered, and return its sanitized response."""
        self._failover.cooldown.mark_succeeded(self._failover.index_of(provider))
        sanitize_poa_response(self._method, response)
        self._failover.logger.debug(
            {
                "msg": f"Send request using {self._provider_name}.",
                "method": self._method,
                "params": str(self._params),
            }
        )
        return response

    def exhausted(self) -> Exception:
        """The error to raise when every endpoint failed, or none was tried."""
        msg = f"No active provider available in {self._provider_name}."
        self._failover.logger.debug({"msg": msg})
        return NoActiveProviderError.from_exceptions(msg, self._errors)
