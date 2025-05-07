import logging
from unittest.mock import patch

import pytest
import responses
from web3 import Web3

from tests.mocked_requests import _MOCK_REQUEST_POA_RESULT
from web3_multi_provider import MultiProvider
from web3_multi_provider.multi_http_provider import (
    FallbackProvider,
    NoActiveProviderError,
    ProtocolNotSupported,
)

@patch("web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id", return_value=1)
def test_protocols_support(mock_fetch_chain_id):
    MultiProvider(["http://127.0.0.1:9001"])
    MultiProvider(["https://127.0.0.1:9001"])

    with pytest.raises(ProtocolNotSupported):
        MultiProvider(["ipc://127.0.0.1:9001"])

    with pytest.raises(ProtocolNotSupported):
        MultiProvider(["ws://127.0.0.1:9001"])

    with pytest.raises(ProtocolNotSupported):
        MultiProvider(["wss://127.0.0.1:9001"])

@pytest.mark.parametrize("provider_cls", [MultiProvider, FallbackProvider])
@patch("web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id", return_value=1)
@responses.activate
def test_one_provider_works(mock_fetch_chain_id, provider_cls, caplog, mock_metrics):
    provider = provider_cls(
        [
            "http://127.0.0.1:9001",
            "http://127.0.0.1:9000",
        ],
        exception_retry_configuration=None,
    )

    w3 = Web3(provider)

    with caplog.at_level(logging.DEBUG):
        w3.eth.get_block("latest")
        w3.eth.get_block("latest")

    expected_provider_name = provider_cls.__name__

    assert mock_metrics.rpc_service_requests.return_value.inc.call_count > 0
    assert mock_metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
    assert mock_metrics.http_rpc_service_requests.return_value.inc.call_count > 0
    assert mock_metrics.rpc_service_response_payload_bytes.return_value.observe.call_count > 0
    assert mock_metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0

    assert {"msg": "Provider not responding.", "error": "Mocked connection error."} == caplog.records[3].msg
    assert {"msg": f"Send request using {expected_provider_name}.", "method": "eth_getBlockByNumber", "params": "('latest', False)"} == \
           caplog.records[7].msg
    # Make sure second request will be directory to second provider and will ignore second one
    assert {"msg": f"Send request using {expected_provider_name}.", "method": "eth_getBlockByNumber", "params": "('latest', False)", } == \
           caplog.records[13].msg


class TestHttpProvider:
    @pytest.fixture(autouse=True)
    def __inject_fixtures(self, caplog, mock_metrics):
        self._caplog = caplog
        self._metrics = mock_metrics

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    def test_nothing_works(self, mock_fetch_chain_id):
        self._caplog.set_level(logging.WARNING)

        provider = MultiProvider(
            [
                "http://127.0.0.1:9001",
                "http://127.0.0.1:9002",
            ],
            exception_retry_configuration=None,
        )

        w3 = Web3(provider)

        with self._caplog.at_level(logging.DEBUG):
            with pytest.raises(NoActiveProviderError):
                w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.http_rpc_service_requests.return_value.observe.call_count == 0
        assert self._metrics.rpc_service_response_payload_bytes.return_value.observe.call_count == 0

        # Make sure there is no inf recursion
        assert len(self._caplog.records) == 8

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @pytest.mark.http_mock(custom_resp=_MOCK_REQUEST_POA_RESULT)
    def test_poa_blockchain(self, mock_fetch_chain_id):
        provider = MultiProvider(["http://127.0.0.1:9000"])

        w3 = Web3(provider)

        with self._caplog.at_level(logging.DEBUG):
            block = w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_response_payload_bytes.return_value.observe.call_count > 0

        assert {"msg": "PoA blockchain cleanup response."} in [log.msg for log in self._caplog.records]
        assert block.get("proofOfAuthorityData", None) is not None

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    def test_pos_blockchain(self, mock_fetch_chain_id):
        provider = MultiProvider(["http://127.0.0.1:9000"])

        w3 = Web3(provider)

        with self._caplog.at_level(logging.DEBUG):
            block = w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.http_rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_response_payload_bytes.return_value.observe.call_count > 0

        assert block.get("proofOfAuthorityData", None) is None

        assert {"msg": "PoA blockchain cleanup response."} not in [log.msg for log in self._caplog.records]


class TestFallbackProvider:

    @pytest.fixture(autouse=True)
    def __inject_fixtures(self, caplog, mock_metrics):
        self._caplog = caplog
        self._metrics = mock_metrics

    def test_no_endpoints(self):
        w3 = Web3(FallbackProvider([]))

        with pytest.raises(RuntimeError):
            w3.eth.get_block("latest")

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    def test_one_endpoint(self, mock_fetch_chain_id):
        w3 = Web3(
            FallbackProvider(
                [
                    "http://127.0.0.1:9000",
                ],
                exception_retry_configuration=None,
            )
        )
        w3.eth.get_block("latest")
        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.http_rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_response_payload_bytes.return_value.observe.call_count > 0
        assert len(responses.calls) == 1

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    def test_first_working(self, mock_fetch_chain_id):
        w3 = Web3(
            FallbackProvider(
                [
                    "http://127.0.0.1:9000",
                    "http://127.0.0.1:9001",
                ],
                exception_retry_configuration=None,
            )
        )
        w3.eth.get_block("latest")
        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.http_rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_response_payload_bytes.return_value.observe.call_count > 0
        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == "http://127.0.0.1:9000/"

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    def test_all_endpoints_fail(self, mock_fetch_chain_id):
        w3 = Web3(
            FallbackProvider(
                [
                    "http://127.0.0.1:9001",
                    "http://127.0.0.1:9002",
                    "http://127.0.0.1:9003",
                ],
                exception_retry_configuration=None,
            )
        )

        with pytest.raises(NoActiveProviderError):
            w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.http_rpc_service_requests.return_value.inc.call_count == 3
        assert self._metrics.rpc_service_response_payload_bytes.return_value.inc.call_count == 0
        assert len(responses.calls) == 3
        assert responses.calls[0].request.url == "http://127.0.0.1:9001/"
        assert responses.calls[1].request.url == "http://127.0.0.1:9002/"
        assert responses.calls[2].request.url == "http://127.0.0.1:9003/"

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    def test_one_endpoint_works(self, mock_fetch_chain_id):
        w3 = Web3(
            FallbackProvider(
                [
                    "http://127.0.0.1:9001",
                    "http://127.0.0.1:9000",
                ],
                exception_retry_configuration=None,
            )
        )

        w3.eth.get_block("latest")
        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.http_rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_response_payload_bytes.return_value.observe.call_count > 0
        assert len(responses.calls) == 2
        assert responses.calls[1].request.url == "http://127.0.0.1:9000/"
