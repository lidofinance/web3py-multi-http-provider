import dataclasses
from unittest.mock import patch, MagicMock, Mock

import pytest


@dataclasses.dataclass
class MockMetrics:
    rpc_service_requests: Mock
    rpc_service_request_methods: Mock
    rpc_service_response: Mock
    rpc_service_request_payload_bytes: Mock
    rpc_service_responses_total_bytes: Mock


@pytest.fixture(autouse=True)
def mock_metrics() -> MockMetrics:
    with (
        patch("web3_multi_provider.metrics.RPC_SERVICE_REQUESTS.labels", return_value=MagicMock()) as req,
        patch("web3_multi_provider.metrics.RPC_SERVICE_REQUEST_METHODS.labels", return_value=MagicMock()) as methods,
        patch("web3_multi_provider.metrics.RPC_SERVICE_REQUEST_PAYLOAD_BYTES.labels", return_value=MagicMock()) as payload,
        patch("web3_multi_provider.metrics.RPC_SERVICE_RESPONSES_TOTAL_BYTES.labels", return_value=MagicMock()) as resp_bytes,
        patch("web3_multi_provider.metrics.RPC_SERVICE_RESPONSE.labels", return_value=MagicMock()) as response,
    ):
        yield MockMetrics(
            rpc_service_requests=req,
            rpc_service_request_methods=methods,
            rpc_service_request_payload_bytes=payload,
            rpc_service_responses_total_bytes=resp_bytes,
            rpc_service_response=response,
        )
