import logging
import math
import threading
import time
from typing import Callable, Sequence

import aiohttp
import requests

from web3_multi_provider import metrics

logger = logging.getLogger(__name__)

# Statuses that blame the request, not the endpoint: another endpoint would reject it too.
_REQUEST_ERROR_STATUSES = frozenset({400, 413, 414, 422})


def is_endpoint_failure(error: Exception) -> bool:
    """Whether `error` may mean the endpoint is unhealthy, rather than that the request was bad.

    False only for HTTP 400, 413, 414 and 422: the endpoint answered and rejected the request,
    and another endpoint would reject it too. Everything else counts, including errors this
    function does not know. A wrong guess is cheap in one direction and expensive in the
    other: a needless cooldown moves a healthy endpoint back for one window, while a missed
    one makes every request pay web3's retries on a broken endpoint, for example one that
    answers 401 because its API key expired. Errors cannot be classified by Python type:
    web3 raises the same `TypeError` and `ValueError` for bad params and for broken responses.
    """
    status = _http_status(error)
    return status is None or status not in _REQUEST_ERROR_STATUSES


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

    def reorder(self, order: list[int], *, probes_first: bool = False) -> list[int]:
        """`order` with cooling endpoints moved to the end, keeping relative order.

        Cooling endpoints are kept, so a request never has fewer endpoints to try than
        without a cooldown. Each index appears exactly once. Cooling endpoints are ordered
        by when their cooldown ends: the endpoint that failed longest ago is the most likely
        to have recovered. Ties keep their relative order.

        An endpoint whose cooldown has just ended is probed by this request. It keeps its
        place in `order`, unless `probes_first` is set: then it is tried first, so the probe
        actually reaches it. Set it when `order` does not express priority, as in
        round-robin, where an endpoint that is not probed is not back in the rotation.
        """
        if not self.enabled:
            return order
        with self._lock:
            now = self._clock()
            probes: list[int] = []
            healthy: list[int] = []
            cooling: list[tuple[float, int]] = []
            for index in order:
                until = self._until.get(index)
                if until is None:
                    healthy.append(index)
                elif until > now:
                    cooling.append((until, index))
                else:
                    self._start_probe(index, now)
                    (probes if probes_first else healthy).append(index)
            cooling.sort(key=lambda item: item[0])  # stable: ties keep `order`
            return probes + healthy + [index for _, index in cooling]

    def _start_probe(self, index: int, now: float) -> None:
        # Re-arm the cooldown before the probe runs, so concurrent requests keep the
        # endpoint last. A probe that never reports back (the request was cancelled, or
        # an earlier endpoint answered first) only delays the next probe by one window.
        # Because `reorder` sorts cooling endpoints by `_until`, such an endpoint still
        # comes before endpoints that failed after it, so it is not stuck behind
        # endpoints that are actually down.
        self._until[index] = now + self._seconds
        self._probing.add(index)

    def mark_failed(self, index: int, error: Exception) -> None:
        """Start or extend the cooldown of the endpoint at `index` if `error` counts.

        An error that does not count, such as HTTP 400, means the endpoint answered: it ends
        the cooldown like a success, so a probe that gets one does not keep the endpoint
        cooling for another window.
        """
        if not self.enabled:
            return
        if not self._is_failure(error):
            self.mark_succeeded(index)
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
        # The metric objects are package-private module globals in `metrics`, replaced
        # by init_metrics(); they must be read through the module at call time.
        # pylint: disable=protected-access
        try:
            metrics._PROVIDER_COOLDOWN_EVENTS.labels(label, event).inc()
        except Exception as error:  # pylint: disable=broad-except
            log = (
                logger.debug
                if isinstance(metrics._PROVIDER_COOLDOWN_EVENTS, metrics._DummyMetric)
                else logger.warning
            )
            log({"msg": "Failed to record cooldown metric.", "error": str(error)})
