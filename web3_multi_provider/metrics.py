"""Prometheus metrics initialization and no-op placeholders.

This module exposes helpers to initialize Prometheus counters/histograms and
provides dummy metrics for environments where Prometheus isn't configured.
"""

import dataclasses
from functools import partial
from typing import Any, Callable, Final

_CHAIN_ID_TO_NAME = {}

_DEFAULT_CHAIN_ID_TO_NAME: Final = {
    1: "ethereum",
    10: "optimism",
    137: "polygon",
    42161: "arbitrum",
    100: "gnosis",
    10200: "chiado",
    11155111: "sepolia",
    560048: "hoodi",
    17000: "holesky",
}


@dataclasses.dataclass
class MetricsConfig:
    namespace: str = ""
    chain_id_to_name: dict[int, str] = dataclasses.field(
        default_factory=_DEFAULT_CHAIN_ID_TO_NAME.copy,
    )


class _DummyMetric:
    """No-op metric used before initialization or in tests."""

    def labels(self, *args: object, **kwargs: object) -> "_DummyMetric":
        return self

    def inc(self, *args: object, **kwargs: object) -> None:  # pragma: no cover
        return None

    def observe(self, *args: object, **kwargs: object) -> None:  # pragma: no cover
        return None


def _init_prometheus_metrics(registry=None) -> dict[str, Callable[..., Any]]:
    # Import inside to avoid mandatory dependency at import time
    from prometheus_client import REGISTRY, Counter, Histogram

    reg = registry or REGISTRY
    return {
        "Counter": partial(Counter, registry=reg),
        "Histogram": partial(Histogram, registry=reg),
    }


_HTTP_RPC_SERVICE_REQUESTS: Any = _DummyMetric()
_HTTP_RPC_BATCH_SIZE: Any = _DummyMetric()

_RPC_REQUEST: Any = _DummyMetric()
_RPC_SERVICE_RESPONSE_SECONDS: Any = _DummyMetric()
_RPC_SERVICE_REQUEST_PAYLOAD_BYTES: Any = _DummyMetric()
_RPC_SERVICE_RESPONSE_PAYLOAD_BYTES: Any = _DummyMetric()


def init_metrics(
    metrics_config: MetricsConfig = MetricsConfig(), registry=None
) -> None:
    _prom = _init_prometheus_metrics(registry)
    global _HTTP_RPC_SERVICE_REQUESTS, _HTTP_RPC_BATCH_SIZE
    global _RPC_REQUEST, _RPC_SERVICE_RESPONSE_SECONDS, _RPC_SERVICE_REQUEST_PAYLOAD_BYTES, _RPC_SERVICE_RESPONSE_PAYLOAD_BYTES
    global _CHAIN_ID_TO_NAME

    counter: Any = _prom["Counter"]
    histogram: Any = _prom["Histogram"]

    _CHAIN_ID_TO_NAME = metrics_config.chain_id_to_name

    _HTTP_RPC_SERVICE_REQUESTS = counter(
        "http_rpc_requests",
        "Counts total HTTP requests used by any layer (EL, CL, or other).",
        [
            "network",
            "layer",
            "chain_id",
            "provider",
            "batched",
            "response_code",
            "result",
        ],
        namespace=metrics_config.namespace,
    )

    _HTTP_RPC_BATCH_SIZE = histogram(
        "http_rpc_batch_size",
        (
            "Distribution of how many JSON-RPC calls (or similar) are bundled in each "
            "HTTP request (batch size)."
        ),
        ["network", "layer", "chain_id", "provider"],
        namespace=metrics_config.namespace,
    )

    _RPC_REQUEST = counter(
        "rpc_request",
        "Total number of RPC requests.",
        [
            "network",
            "layer",
            "chain_id",
            "provider",
            "method",
            "result",
            "rpc_error_code",
        ],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_RESPONSE_SECONDS = histogram(
        "http_rpc_response_seconds",
        "Distribution of RPC response times (in seconds).",
        ["network", "layer", "chain_id", "provider"],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_REQUEST_PAYLOAD_BYTES = histogram(
        "http_rpc_request_payload_bytes",
        "Distribution of request payload sizes (bytes) RPC calls.",
        ["network", "layer", "chain_id", "provider"],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_RESPONSE_PAYLOAD_BYTES = histogram(
        "http_rpc_response_payload_bytes",
        "Distribution of response payload sizes (bytes) RPC calls.",
        ["network", "layer", "chain_id", "provider"],
        namespace=metrics_config.namespace,
    )
