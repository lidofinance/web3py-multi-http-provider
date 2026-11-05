import json
import logging
import math
import threading
import time
from typing import Callable, Sequence

import aiohttp
import requests

from web3_multi_provider import metrics

logger = logging.getLogger(__name__)

_TRANSPORT_ERRORS = (
    ConnectionError,
    TimeoutError,
    requests.ConnectionError,
    requests.Timeout,
    aiohttp.ClientConnectionError,
)
_INVALID_JSON_ERRORS = (json.JSONDecodeError, requests.JSONDecodeError)


def is_endpoint_failure(error: Exception) -> bool:
    """Whether `error` says the endpoint is unhealthy, rather than that the request was bad.

    True for connection errors, timeouts, HTTP 429 and 5xx, and bodies that are not JSON.
    The sync provider reads the body as JSON before it checks the HTTP status, so a 429 or
    5xx with a plain-text body arrives as a JSON decode error without its status.
    """
    if isinstance(error, _TRANSPORT_ERRORS):
        return True
    status = _http_status(error)
    if status is not None:
        return status == 429 or status >= 500
    return isinstance(error, _INVALID_JSON_ERRORS)


def _http_status(error: Exception) -> int | None:
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return error.response.status_code
    if isinstance(error, aiohttp.ClientResponseError):
        return error.status
    return None


class ProviderCooldown:
    """Circuit breaker that moves recently failed endpoints to the end of the order.

    A failed request costs web3's in-provider retries before failover moves on. Trying a
    recently failed endpoint last pays that cost once per cooldown window instead of on
    every request. Only errors for which `is_failure` is true start a cooldown.

    When a cooldown ends, only one request probes the endpoint. The other requests keep it
    last until the probe reports a result, so a still-failing endpoint does not slow down
    every concurrent request at once. An endpoint stays on cooldown until it answers.

    All methods are thread-safe. They do no I/O, so the async providers can call them too.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        seconds: float,
        provider_labels: Sequence[str] = (),
        *,
        is_failure: Callable[[Exception], bool] = is_endpoint_failure,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError(
                "Cooldown must be a finite, non-negative number of seconds."
            )
        self._seconds = seconds
        self._provider_labels = provider_labels
        self._is_failure = is_failure
        self._clock = clock
        self._lock = threading.Lock()
        self._until: dict[int, float] = {}
        self._probing: set[int] = set()

    @property
    def enabled(self) -> bool:
        """Whether failed endpoints are moved back at all."""
        return self._seconds > 0

    def reorder(self, order: list[int]) -> list[int]:
        """`order` with cooling endpoints moved to the end, keeping relative order.

        Cooling endpoints are kept, so a request never has fewer endpoints to try than
        without a cooldown. Each index appears exactly once.
        """
        if not self.enabled:
            return order
        with self._lock:
            now = self._clock()
            healthy: list[int] = []
            cooling: list[int] = []
            for index in order:
                until = self._until.get(index)
                if until is None:
                    healthy.append(index)
                elif until > now:
                    cooling.append(index)
                else:
                    self._start_probe(index, now)
                    healthy.append(index)
            return healthy + cooling

    def _start_probe(self, index: int, now: float) -> None:
        # Re-arm the cooldown before the probe runs, so concurrent requests keep the
        # endpoint last. A probe that never reports back (the request was cancelled, or
        # an earlier endpoint answered first) only delays the next probe by one window.
        self._until[index] = now + self._seconds
        self._probing.add(index)

    def mark_failed(self, index: int, error: Exception) -> None:
        """Start or extend the cooldown of the endpoint at `index` if `error` counts."""
        if not self.enabled or not self._is_failure(error):
            return
        with self._lock:
            if index in self._probing:
                self._probing.discard(index)
                event = "probe_failed"
            elif index not in self._until:
                event = "entered"
            else:
                event = ""
            self._until[index] = self._clock() + self._seconds
        if event == "probe_failed":
            self._report(
                logging.WARNING, "Provider still failing after cooldown.", index, event
            )
        elif event == "entered":
            self._report(logging.WARNING, "Provider put on cooldown.", index, event)

    def mark_succeeded(self, index: int) -> None:
        """End the cooldown of the endpoint at `index`: it answered, so it is preferred again."""
        if not self.enabled:
            return
        with self._lock:
            self._probing.discard(index)
            recovered = self._until.pop(index, None) is not None
        if recovered:
            self._report(
                logging.INFO, "Provider recovered from cooldown.", index, "recovered"
            )

    def _report(self, level: int, msg: str, index: int, event: str) -> None:
        logger.log(level, {"msg": msg, "index": index, "seconds": self._seconds})
        label = (
            self._provider_labels[index]
            if index < len(self._provider_labels)
            else str(index)
        )
        try:
            metrics._PROVIDER_COOLDOWN_EVENTS.labels(label, event).inc()
        except Exception as error:  # pylint: disable=broad-except
            log = (
                logger.debug
                if isinstance(metrics._PROVIDER_COOLDOWN_EVENTS, metrics._DummyMetric)
                else logger.warning
            )
            log({"msg": "Failed to record cooldown metric.", "error": str(error)})
