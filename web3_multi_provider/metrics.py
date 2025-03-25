import os

from prometheus_client import Counter, Histogram

PROMETHEUS_PREFIX = os.getenv('PROMETHEUS_PREFIX', '')

RPC_SERVICE_REQUESTS = Counter(
    'rpc_service_request',
    'Tracks the cumulative number of RPC requests.',
    ['network', 'chainId', 'provider', 'status'],
    namespace=PROMETHEUS_PREFIX,
)

RPC_SERVICE_REQUEST_METHODS = Counter(
    'rpc_service_request_methods',
    'Tracks the number of RPC requests made, grouped by method.',
    ['network', 'chainId', 'provider', 'method', 'status'],
    namespace=PROMETHEUS_PREFIX,
)

RPC_SERVICE_RESPONSE = Histogram(
    'rpc_service_response',
    'Measures the response time (in seconds) for RPC requests.',
    ['network', 'chainId', 'provider', 'status'],
    namespace=PROMETHEUS_PREFIX,
)

RPC_SERVICE_REQUEST_PAYLOAD_BYTES = Histogram(
    'rpc_service_request_payload_bytes',
    'Measures the size (in bytes) of RPC request payloads.',
    ['network', 'chainId', 'provider'],
    namespace=PROMETHEUS_PREFIX,
)

RPC_SERVICE_RESPONSES_TOTAL_BYTES = Counter(
    'rpc_service_responses_total_bytes',
    'Measures the total responses bytes.',
    ['network', 'chainId', 'provider'],
    namespace=PROMETHEUS_PREFIX,
)

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
