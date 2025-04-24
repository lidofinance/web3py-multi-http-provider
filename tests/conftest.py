import dataclasses
from unittest.mock import patch, MagicMock, Mock

import pytest

from web3_multi_provider.metrics import init_metrics, MetricsConfig


@dataclasses.dataclass
class MockMetrics:
    http_rpc_service_requests: Mock
    http_rpc_batch_size: Mock
    rpc_service_requests: Mock
    rpc_service_response_seconds: Mock
    rpc_service_request_payload_bytes: Mock
    rpc_service_response_payload_bytes: Mock


@pytest.fixture(scope="session", autouse=True)
def initialize_metrics():
    init_metrics(MetricsConfig(namespace="test"))
    yield


@pytest.fixture
def mock_metrics() -> MockMetrics:
    with (
        patch("web3_multi_provider.metrics._HTTP_RPC_SERVICE_REQUESTS.labels", return_value=MagicMock()) as req,
        patch("web3_multi_provider.metrics._HTTP_RPC_BATCH_SIZE.labels", return_value=MagicMock()) as batch,
        patch("web3_multi_provider.metrics._RPC_SERVICE_REQUESTS.labels", return_value=MagicMock()) as rpc_req,
        patch("web3_multi_provider.metrics._RPC_SERVICE_RESPONSE_SECONDS.labels", return_value=MagicMock()) as rpc_resp_sec,
        patch("web3_multi_provider.metrics._RPC_SERVICE_REQUEST_PAYLOAD_BYTES.labels", return_value=MagicMock()) as rpc_req_payload,
        patch("web3_multi_provider.metrics._RPC_SERVICE_RESPONSE_PAYLOAD_BYTES.labels", return_value=MagicMock()) as rpc_resp_payload,
    ):
        yield MockMetrics(
            http_rpc_service_requests=req,
            http_rpc_batch_size=batch,
            rpc_service_requests=rpc_req,
            rpc_service_response_seconds=rpc_resp_sec,
            rpc_service_request_payload_bytes=rpc_req_payload,
            rpc_service_response_payload_bytes=rpc_resp_payload,
        )
