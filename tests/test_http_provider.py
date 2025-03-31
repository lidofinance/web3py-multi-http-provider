import logging
from unittest.mock import patch

import pytest
from web3 import Web3

from tests.mocked_requests import mocked_request_poa, mock_response
from web3_multi_provider import MultiProvider
from web3_multi_provider.multi_http_provider import (
    FallbackProvider,
    NoActiveProviderError,
    ProtocolNotSupported,
)


def test_protocols_support():
    MultiProvider(["http://127.0.0.1:9001"])
    MultiProvider(["https://127.0.0.1:9001"])

    with pytest.raises(ProtocolNotSupported):
        MultiProvider(["ipc://127.0.0.1:9001"])

    with pytest.raises(ProtocolNotSupported):
        MultiProvider(["ws://127.0.0.1:9001"])

    with pytest.raises(ProtocolNotSupported):
        MultiProvider(["wss://127.0.0.1:9001"])


class TestHttpProvider:
    @pytest.fixture(autouse=True)
    def __inject_fixtures(self, caplog, mock_metrics):
        self._caplog = caplog
        self._metrics = mock_metrics

    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.get_response_from_post_request",
        side_effect=mock_response,
    )
    def test_one_provider_works(self, make_post_request, mock_fetch_chain_id):
        self.one_provider_works(MultiProvider)
        self.one_provider_works(FallbackProvider)

    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.get_response_from_post_request",
        side_effect=mock_response,
    )
    def test_nothing_works(self, make_post_request, mock_fetch_chain_id):
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
        assert self._metrics.rpc_service_response.return_value.observe.call_count == 0
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count == 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0

        # Make sure there is no inf recursion
        assert len(self._caplog.records) == 6

    def one_provider_works(self, provider_class):
        provider = provider_class(
            [
                "http://127.0.0.1:9001",
                "http://127.0.0.1:9000",
            ],
            exception_retry_configuration=None,
        )

        w3 = Web3(provider)

        with self._caplog.at_level(logging.DEBUG):
            w3.eth.get_block("latest")
            w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_response.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0

        assert {"msg": "Provider not responding.", "error": "Mocked connection error."} == self._caplog.records[2].msg
        assert {"msg": "Send request using MultiProvider.", "method": "eth_getBlockByNumber", "params": "('latest', False)"} == \
               self._caplog.records[5].msg
        # Make sure second request will be directory to second provider and will ignore second one
        assert {"msg": "Send request using MultiProvider.", "method": "eth_getBlockByNumber", "params": "('latest', False)", } == \
               self._caplog.records[9].msg

    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.make_post_request",
        side_effect=mocked_request_poa,
    )
    def test_poa_blockchain(self, make_post_request, mock_fetch_chain_id):
        provider = MultiProvider(["http://127.0.0.1:9000"])

        w3 = Web3(provider)

        with self._caplog.at_level(logging.DEBUG):
            block = w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0

        assert {"msg": "PoA blockchain cleanup response."} in [log.msg for log in self._caplog.records]
        assert block.get("proofOfAuthorityData", None) is not None

    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.get_response_from_post_request",
        side_effect=mock_response,
    )
    def test_pos_blockchain(self, make_post_request, mock_fetch_chain_id):
        provider = MultiProvider(["http://127.0.0.1:9000"])

        w3 = Web3(provider)

        with self._caplog.at_level(logging.DEBUG):
            block = w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_response.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0

        assert block.get("proofOfAuthorityData", None) is None

        assert {"msg": "PoA blockchain cleanup response."} not in [log.msg for log in self._caplog.records]


class TestFallbackProvider:

    @pytest.fixture(autouse=True)
    def __inject_fixtures(self, caplog, mock_metrics):
        self._caplog = caplog
        self._metrics = mock_metrics

    def test_no_endpoints(self):
        w3 = Web3(FallbackProvider([]))

        with pytest.raises(NoActiveProviderError):
            w3.eth.get_block("latest")

    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.get_response_from_post_request",
        side_effect=mock_response,
    )
    def test_one_endpoint(self, make_post_request, mock_fetch_chain_id):
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
        assert self._metrics.rpc_service_response.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0
        make_post_request.assert_called_once()

    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.get_response_from_post_request",
        side_effect=mock_response,
    )
    def test_first_working(self, make_post_request, mock_fetch_chain_id):
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
        assert self._metrics.rpc_service_response.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0
        make_post_request.assert_called_once()
        assert make_post_request.call_args.args[0] == "http://127.0.0.1:9000"

    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.get_response_from_post_request",
        side_effect=mock_response,
    )
    def test_all_endpoints_fail(self, make_post_request, mock_fetch_chain_id):
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
        assert self._metrics.rpc_service_response.return_value.observe.call_count == 0
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count == 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0
        assert make_post_request.call_count == 3
        assert make_post_request.call_args.args[0] == "http://127.0.0.1:9003"

    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.get_response_from_post_request",
        side_effect=mock_response,
    )
    def test_one_endpoint_works(self, make_post_request, mock_fetch_chain_id):
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
        assert self._metrics.rpc_service_response.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0
        assert make_post_request.call_count == 2
        assert make_post_request.call_args.args[0] == "http://127.0.0.1:9000"

    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.get_response_from_post_request",
        side_effect=mock_response,
    )
    def test_starts_from_the_first(self, make_post_request, mock_fetch_chain_id):
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
        w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_response.return_value.observe.call_count > 0
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0

        assert make_post_request.call_count == 4
        assert make_post_request.call_args_list[-2].args[0] == "http://127.0.0.1:9001"
