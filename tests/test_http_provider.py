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
from web3_multi_provider.exceptions import ChainIdMismatchError

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

    assert {"msg": "Provider not responding.", "index": 0, "error": "Mocked connection error."} == caplog.records[3].msg
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

    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    def test_chain_id_validation_same_chain_ids(self, mock_fetch_chain_id, mock_metrics):
        """Test that validation passes when all providers have the same chain ID."""
        provider = FallbackProvider(
            [
                "http://127.0.0.1:9001",
                "http://127.0.0.1:9002",
            ],
            exception_retry_configuration=None,
        )

        provider._providers[0]._chain_id = "1"
        provider._providers[1]._chain_id = "1"

        provider._validate_chain_ids()

        assert provider._providers[0]._chain_id == "1"
        assert provider._providers[1]._chain_id == "1"

    @responses.activate
    def test_chain_id_validation_different_chain_ids(self):
        """Test that validation raises ChainIdMismatchError when providers have different chain IDs."""
        provider = FallbackProvider(
            [
                "http://127.0.0.1:9001",
                "http://127.0.0.1:9002"
            ],
            exception_retry_configuration=None,
        )

        provider._providers[0]._chain_id = "1"
        provider._providers[1]._chain_id = "137"

        with pytest.raises(ChainIdMismatchError) as exc_info:
            provider._validate_chain_ids()

        error_msg = str(exc_info.value).lower()
        assert "different chain ids" in error_msg
        assert "1" in str(exc_info.value)
        assert "137" in str(exc_info.value)


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


_GOOD_RPC_BODY = b'{"jsonrpc":"2.0","id":0,"result":"0x1"}'
_JSON_RPC_ERROR_BODY = (
    b'{"jsonrpc":"2.0","id":0,'
    b'"error":{"code":-32601,"message":"Method not found"}}'
)


class TestHttpErrorFailover:
    BAD = "http://127.0.0.1:9100"
    GOOD = "http://127.0.0.1:9101"

    @pytest.fixture(autouse=True)
    def __inject_fixtures(self, caplog, mock_metrics):
        self._caplog = caplog
        self._metrics = mock_metrics

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1,
    )
    def test_make_request__first_provider_returns_404_with_html_body__fails_over_to_next(
        self, mock_fetch_chain_id
    ):
        responses.add(
            responses.POST,
            self.BAD,
            body=b"<html><body>Not Found</body></html>",
            status=404,
            content_type="text/html",
        )
        responses.add(
            responses.POST,
            self.GOOD,
            body=_GOOD_RPC_BODY,
            status=200,
            content_type="application/json",
        )

        provider = FallbackProvider(
            [self.BAD, self.GOOD], exception_retry_configuration=None
        )
        result = provider.make_request("eth_chainId", [])

        assert result == {"jsonrpc": "2.0", "id": 0, "result": "0x1"}
        assert len(responses.calls) == 2
        assert responses.calls[0].request.url == self.BAD + "/"
        assert responses.calls[1].request.url == self.GOOD + "/"

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1,
    )
    def test_make_request__first_provider_returns_404_with_json_rpc_error_body__fails_over_to_next(
        self, mock_fetch_chain_id
    ):
        responses.add(
            responses.POST,
            self.BAD,
            body=_JSON_RPC_ERROR_BODY,
            status=404,
            content_type="application/json",
        )
        responses.add(
            responses.POST,
            self.GOOD,
            body=_GOOD_RPC_BODY,
            status=200,
            content_type="application/json",
        )

        provider = FallbackProvider(
            [self.BAD, self.GOOD], exception_retry_configuration=None
        )
        result = provider.make_request("eth_chainId", [])

        assert result == {"jsonrpc": "2.0", "id": 0, "result": "0x1"}
        assert len(responses.calls) == 2

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1,
    )
    def test_make_request__first_provider_returns_5xx__fails_over_to_next(
        self, mock_fetch_chain_id, status
    ):
        responses.add(
            responses.POST,
            self.BAD,
            body=b"upstream error",
            status=status,
            content_type="text/plain",
        )
        responses.add(
            responses.POST,
            self.GOOD,
            body=_GOOD_RPC_BODY,
            status=200,
            content_type="application/json",
        )

        provider = FallbackProvider(
            [self.BAD, self.GOOD], exception_retry_configuration=None
        )
        result = provider.make_request("eth_chainId", [])

        assert result == {"jsonrpc": "2.0", "id": 0, "result": "0x1"}
        assert len(responses.calls) == 2

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1,
    )
    def test_make_request__first_provider_returns_200_with_non_json_body__fails_over_to_next(
        self, mock_fetch_chain_id
    ):
        responses.add(
            responses.POST,
            self.BAD,
            body=b"<html>welcome</html>",
            status=200,
            content_type="text/html",
        )
        responses.add(
            responses.POST,
            self.GOOD,
            body=_GOOD_RPC_BODY,
            status=200,
            content_type="application/json",
        )

        provider = FallbackProvider(
            [self.BAD, self.GOOD], exception_retry_configuration=None
        )
        result = provider.make_request("eth_chainId", [])

        assert result == {"jsonrpc": "2.0", "id": 0, "result": "0x1"}
        assert len(responses.calls) == 2

    @responses.activate
    @patch(
        "web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id",
        return_value=1,
    )
    def test_make_request__all_providers_return_404__raises_no_active_provider_error(
        self, mock_fetch_chain_id
    ):
        urls = [
            "http://127.0.0.1:9100",
            "http://127.0.0.1:9101",
            "http://127.0.0.1:9102",
        ]
        for url in urls:
            responses.add(
                responses.POST,
                url,
                body=b"not found",
                status=404,
                content_type="text/plain",
            )

        provider = FallbackProvider(urls, exception_retry_configuration=None)

        with pytest.raises(NoActiveProviderError) as exc_info:
            provider.make_request("eth_chainId", [])

        assert len(responses.calls) == 3
        assert len(exc_info.value.exceptions) == 3

