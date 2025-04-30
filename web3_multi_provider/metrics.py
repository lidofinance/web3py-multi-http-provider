import dataclasses
from typing import Final

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
    namespace: str = ''
    chain_id_to_name: dict[int, str] = dataclasses.field(default_factory=lambda: _DEFAULT_CHAIN_ID_TO_NAME.copy())


class _DummyMetric:
    def labels(self, *args, **kwargs):
        return self

    def inc(self, *args, **kwargs): pass

    def observe(self, *args, **kwargs): pass


def _init_prometheus_metrics(registry=None):
    try:
        from prometheus_client import Counter, Histogram, REGISTRY
        kwargs = {"registry": registry or REGISTRY}
        return {
            "Counter": lambda *args, **kw: Counter(*args, **kw, **kwargs),
            "Histogram": lambda *args, **kw: Histogram(*args, **kw, **kwargs),
        }
    except ImportError:
        return {
            "Counter": lambda *args, **kw: _DummyMetric(),
            "Histogram": lambda *args, **kw: _DummyMetric(),
        }


_HTTP_RPC_SERVICE_REQUESTS = _DummyMetric()
_HTTP_RPC_BATCH_SIZE = _DummyMetric()

_RPC_SERVICE_REQUESTS = _DummyMetric()
_HTTP_RPC_SERVICE_REQUESTS_SECONDS = _DummyMetric()
_RPC_SERVICE_REQUEST_PAYLOAD_BYTES = _DummyMetric()
_RPC_SERVICE_RESPONSE_PAYLOAD_BYTES = _DummyMetric()


def init_metrics(metrics_config: MetricsConfig = MetricsConfig(), registry=None):
    _prom = _init_prometheus_metrics(registry)
    global _HTTP_RPC_SERVICE_REQUESTS, _HTTP_RPC_BATCH_SIZE
    global _RPC_SERVICE_REQUESTS, _RPC_SERVICE_RESPONSE_SECONDS, _RPC_SERVICE_REQUEST_PAYLOAD_BYTES, _RPC_SERVICE_RESPONSE_PAYLOAD_BYTES
    global _CHAIN_ID_TO_NAME

    counter = _prom["Counter"]
    histogram = _prom["Histogram"]

    _CHAIN_ID_TO_NAME = metrics_config.chain_id_to_name

    _HTTP_RPC_SERVICE_REQUESTS = counter(
        "http_rpc_requests",
        "Counts total HTTP requests used by any layer (EL, CL, or other).",
        ["network", "layer", "chainId", "provider", "batched", "response_code", "result"],
        namespace=metrics_config.namespace,
    )

    _HTTP_RPC_BATCH_SIZE = histogram(
        "http_rpc_batch_size",
        "Distribution of how many JSON-RPC calls (or similar) are bundled in each HTTP request (batch size).",
        ["network", "layer", "chainId", "provider"],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_REQUESTS = counter(
        "rpc_service_request",
        "Total number of RPC requests.",
        ["network", "layer", "chainId", "provider", "method", "result", "rpc_error_code"],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_RESPONSE_SECONDS = histogram(
        "rpc_service_response_seconds",
        "Distribution of RPC response times (in seconds).",
        ["network", "layer", "chainId", "provider"],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_REQUEST_PAYLOAD_BYTES = histogram(
        "http_rpc_request_payload_bytes",
        "Distribution of request payload sizes (bytes) RPC calls.",
        ["network", "layer", "chainId", "provider"],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_RESPONSE_PAYLOAD_BYTES = histogram(
        "rpc_service_response_payload_bytes",
        "Distribution of response payload sizes (bytes) RPC calls.",
        ["network", "layer", "chainId", "provider"],
        namespace=metrics_config.namespace,
    )
