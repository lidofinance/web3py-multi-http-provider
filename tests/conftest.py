import dataclasses
from unittest.mock import MagicMock, Mock, patch

import pytest
import responses

from tests.mocked_requests import _AVAILABLE_ADDRESS, _NOT_AVAILABLE_ADDRESS_1, _NOT_AVAILABLE_ADDRESS_2, mock_response
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
        patch("web3_multi_provider.metrics._RPC_REQUEST.labels", return_value=MagicMock()) as rpc_req,
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


@pytest.fixture(autouse=True)
def http_responses(request):
    with responses.RequestsMock() as rsps:
        marker = request.node.get_closest_marker("http_mock")

        def _rsp_callback(request):
            cm = mock_response(request.url)
            if marker and marker.kwargs.get("custom_resp"):
                cm = mock_response(request.url, marker.kwargs["custom_resp"])
            resp = cm.__enter__()
            headers = {"Content-Type": "application/json", "Content-Length": str(len(resp.content))}
            return resp.status_code, headers, resp.content

        responses.add_callback(
            responses.POST,
            _AVAILABLE_ADDRESS,
            callback=_rsp_callback,
            content_type="application/json",
        )
        responses.add_callback(
            responses.POST,
            _NOT_AVAILABLE_ADDRESS_1,
            callback=_rsp_callback,
            content_type="application/json",
        )
        responses.add_callback(
            responses.POST,
            _NOT_AVAILABLE_ADDRESS_2,
            callback=_rsp_callback,
            content_type="application/json",
        )

        yield rsps
