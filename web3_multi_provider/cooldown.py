import logging
import math
import threading
import time

logger = logging.getLogger(__name__)


class ProviderCooldown:
    """Remembers which endpoints failed recently.

    A failed request costs web3's in-provider retries before failover moves on. Trying a recently
    failed endpoint last pays that cost once per cooldown window instead of on every request.

    When a cooldown ends, only one request probes the endpoint. The other requests keep it last
    until the probe reports a result, so a still-failing endpoint does not slow down every
    concurrent request at once.

    All methods are thread-safe. They do no I/O, so the async providers can call them too.
    """

    def __init__(self, seconds: float):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError(
                "Cooldown must be a finite, non-negative number of seconds."
            )
        self._seconds = seconds
        self._lock = threading.Lock()
        self._until: dict[int, float] = {}
        self._probing: set[int] = set()

    @property
    def enabled(self) -> bool:
        """Whether failed endpoints are moved back at all."""
        return self._seconds > 0

    def order(self, count: int) -> list[int]:
        """Endpoint indexes in configured order, with cooling endpoints moved to the end.

        Cooling endpoints are kept, so a request never has fewer endpoints to try than without
        a cooldown. Each index appears exactly once.
        """
        with self._lock:
            now = time.monotonic()
            healthy: list[int] = []
            cooling: list[int] = []
            for index in range(count):
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
        # Re-arm the cooldown before the probe runs, so concurrent requests keep the endpoint
        # last. A probe that never reports back (the request was cancelled, or an earlier
        # endpoint answered first) only delays the next probe by one window.
        self._until[index] = now + self._seconds
        self._probing.add(index)

    def mark_failed(self, index: int) -> None:
        """Start or extend the cooldown of the endpoint at `index`."""
        if not self.enabled:
            return
        with self._lock:
            now = time.monotonic()
            if index in self._probing:
                self._probing.discard(index)
                self._log(
                    logging.WARNING, "Provider still failing after cooldown.", index
                )
            elif self._until.get(index, 0) <= now:
                self._log(logging.WARNING, "Provider put on cooldown.", index)
            self._until[index] = now + self._seconds

    def mark_succeeded(self, index: int) -> None:
        """End the cooldown of the endpoint at `index`: it answered, so it is preferred again."""
        if not self.enabled:
            return
        with self._lock:
            self._probing.discard(index)
            if self._until.pop(index, None) is not None:
                self._log(logging.INFO, "Provider recovered from cooldown.", index)

    def _log(self, level: int, msg: str, index: int) -> None:
        logger.log(level, {"msg": msg, "index": index, "seconds": self._seconds})
