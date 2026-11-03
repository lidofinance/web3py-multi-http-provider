import logging
import time

logger = logging.getLogger(__name__)


class ProviderCooldown:
    """Remembers which endpoints failed recently.

    A failed request costs web3's in-provider retries before failover moves on. Trying a recently
    failed endpoint last pays that cost once per cooldown window instead of on every request.
    """

    def __init__(self, seconds: float):
        if seconds < 0:
            raise ValueError("Cooldown must not be negative.")
        self._seconds = seconds
        self._until: dict[int, float] = {}

    @property
    def enabled(self) -> bool:
        """Whether failed endpoints are moved back at all."""
        return self._seconds > 0

    def order(self, count: int) -> list[int]:
        """Endpoint indexes in configured order, with cooling endpoints moved to the end.

        Cooling endpoints are kept, so a request never has fewer endpoints to try than without
        a cooldown.
        """
        now = time.monotonic()
        healthy = [i for i in range(count) if self._until.get(i, 0) <= now]
        cooling = [i for i in range(count) if self._until.get(i, 0) > now]
        return healthy + cooling

    def mark_failed(self, index: int) -> None:
        """Start or extend the cooldown of the endpoint at `index`."""
        now = time.monotonic()
        if self._until.get(index, 0) <= now:
            logger.warning(
                {
                    "msg": "Provider put on cooldown.",
                    "index": index,
                    "seconds": self._seconds,
                }
            )
        self._until[index] = now + self._seconds
