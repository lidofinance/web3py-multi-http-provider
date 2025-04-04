import dataclasses

_CHAIN_ID_TO_NAME = {}

_DEFAULT_CHAIN_ID_TO_NAME = {
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
    namespace: str
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


_RPC_SERVICE_REQUESTS = _DummyMetric()
_RPC_SERVICE_REQUEST_METHODS = _DummyMetric()
_RPC_SERVICE_RESPONSE = _DummyMetric()
_RPC_SERVICE_REQUEST_PAYLOAD_BYTES = _DummyMetric()
_RPC_SERVICE_RESPONSES_TOTAL_BYTES = _DummyMetric()


def init_metrics(metrics_config: MetricsConfig, registry=None):
    _prom = _init_prometheus_metrics(registry)
    global _RPC_SERVICE_REQUESTS, _RPC_SERVICE_REQUEST_METHODS, _RPC_SERVICE_RESPONSE
    global _RPC_SERVICE_REQUEST_PAYLOAD_BYTES, _RPC_SERVICE_RESPONSES_TOTAL_BYTES
    global _CHAIN_ID_TO_NAME

    counter = _prom["Counter"]
    histogram = _prom["Histogram"]

    _CHAIN_ID_TO_NAME = metrics_config.chain_id_to_name

    _RPC_SERVICE_REQUESTS = counter(
        "rpc_service_request",
        "Tracks the cumulative number of RPC requests.",
        ["network", "chainId", "provider", "status"],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_REQUEST_METHODS = counter(
        "rpc_service_request_methods",
        "Tracks the number of RPC requests made, grouped by method.",
        ["network", "chainId", "provider", "method", "status"],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_RESPONSE = histogram(
        "rpc_service_response",
        "Measures the response time (in seconds) for RPC requests.",
        ["network", "chainId", "provider", "status"],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_REQUEST_PAYLOAD_BYTES = histogram(
        "rpc_service_request_payload_bytes",
        "Measures the size (in bytes) of RPC request payloads.",
        ["network", "chainId", "provider"],
        namespace=metrics_config.namespace,
    )

    _RPC_SERVICE_RESPONSES_TOTAL_BYTES = counter(
        "rpc_service_responses_total_bytes",
        "Measures the total responses bytes.",
        ["network", "chainId", "provider"],
        namespace=metrics_config.namespace,
    )
