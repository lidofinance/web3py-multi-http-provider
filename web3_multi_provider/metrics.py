import os

PROMETHEUS_PREFIX = os.getenv("PROMETHEUS_PREFIX", "")

CHAIN_ID_TO_NAME = {
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


class DummyMetric:
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
            "Counter": lambda *args, **kw: DummyMetric(),
            "Histogram": lambda *args, **kw: DummyMetric(),
        }


RPC_SERVICE_REQUESTS = DummyMetric()
RPC_SERVICE_REQUEST_METHODS = DummyMetric()
RPC_SERVICE_RESPONSE = DummyMetric()
RPC_SERVICE_REQUEST_PAYLOAD_BYTES = DummyMetric()
RPC_SERVICE_RESPONSES_TOTAL_BYTES = DummyMetric()


def init_metrics(registry=None):
    _prom = _init_prometheus_metrics(registry)
    global RPC_SERVICE_REQUESTS, RPC_SERVICE_REQUEST_METHODS, RPC_SERVICE_RESPONSE
    global RPC_SERVICE_REQUEST_PAYLOAD_BYTES, RPC_SERVICE_RESPONSES_TOTAL_BYTES

    counter = _prom["Counter"]
    histogram = _prom["Histogram"]

    RPC_SERVICE_REQUESTS = counter(
        "rpc_service_request",
        "Tracks the cumulative number of RPC requests.",
        ["network", "chainId", "provider", "status"],
        namespace=PROMETHEUS_PREFIX,
    )

    RPC_SERVICE_REQUEST_METHODS = counter(
        "rpc_service_request_methods",
        "Tracks the number of RPC requests made, grouped by method.",
        ["network", "chainId", "provider", "method", "status"],
        namespace=PROMETHEUS_PREFIX,
    )

    RPC_SERVICE_RESPONSE = histogram(
        "rpc_service_response",
        "Measures the response time (in seconds) for RPC requests.",
        ["network", "chainId", "provider", "status"],
        namespace=PROMETHEUS_PREFIX,
    )

    RPC_SERVICE_REQUEST_PAYLOAD_BYTES = histogram(
        "rpc_service_request_payload_bytes",
        "Measures the size (in bytes) of RPC request payloads.",
        ["network", "chainId", "provider"],
        namespace=PROMETHEUS_PREFIX,
    )

    RPC_SERVICE_RESPONSES_TOTAL_BYTES = counter(
        "rpc_service_responses_total_bytes",
        "Measures the total responses bytes.",
        ["network", "chainId", "provider"],
        namespace=PROMETHEUS_PREFIX,
    )
