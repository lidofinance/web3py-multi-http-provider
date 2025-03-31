import logging
from unittest.mock import Mock, patch

import pytest
from web3 import AsyncWeb3

from tests.mocked_requests import mocked_async_request_get, mocked_async_request_poa
from web3_multi_provider import (
    AsyncFallbackProvider,
    AsyncMultiProvider,
    NoActiveProviderError,
    ProtocolNotSupported,
)


class TestHttpProvider:
    _caplog = None

    @pytest.fixture(autouse=True)
    def __inject_fixtures(self, caplog, mock_metrics):
        self._caplog = caplog
        self._metrics = mock_metrics

    @patch(
        "web3_multi_provider.async_http_provider_proxy.AsyncHTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.async_make_post_request",
        side_effect=mocked_async_request_get,
    )
    @pytest.mark.asyncio
    async def test_one_provider_works(self, make_post_request, mock_fetch_chain_id):
        await self.one_provider_works(AsyncMultiProvider)
        await self.one_provider_works(AsyncFallbackProvider)

    @patch(
        "web3_multi_provider.async_http_provider_proxy.AsyncHTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.async_make_post_request",
        side_effect=mocked_async_request_get,
    )
    @pytest.mark.asyncio
    async def test_nothing_works(self, make_post_request, mock_fetch_chain_id):
        self._caplog.set_level(logging.WARNING)

        provider = AsyncMultiProvider(
            [
                "http://127.0.0.1:9001",
                "http://127.0.0.1:9002",
            ]
        )

        w3 = AsyncWeb3(provider)

        with self._caplog.at_level(logging.DEBUG):
            with pytest.raises(NoActiveProviderError):
                await w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        # self.assertGreater(self._metrics['response'].return_value.observe.call_count, 0)
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count == 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0

        # Make sure there is no inf recursion
        assert len(self._caplog.records) == 6

    async def one_provider_works(self, provider_class):
        provider = provider_class(
            [
                "http://127.0.0.1:9001",
                "http://127.0.0.1:9000",
            ]
        )

        w3 = AsyncWeb3(provider)

        with self._caplog.at_level(logging.DEBUG):
            await w3.eth.get_block("latest")
            await w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count >0
        # self.assertGreater(self._metrics['response'].return_value.observe.call_count, 0)
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0

        assert self._caplog.records[2].msg == {
            "msg": "Provider not responding.",
            "error": "Mocked connection error.",
        }

        assert self._caplog.records[5].msg == {
            "msg": "Send request using AsyncMultiProvider.",
            "method": "eth_getBlockByNumber",
            "params": "('latest', False)",
        }

        # Make sure second request will be directory to second provider and will ignore second one
        assert self._caplog.records[9].msg == {
            "msg": "Send request using AsyncMultiProvider.",
            "method": "eth_getBlockByNumber",
            "params": "('latest', False)",
        }

    def test_protocols_support(self):
        AsyncMultiProvider(["http://127.0.0.1:9001"])
        AsyncMultiProvider(["https://127.0.0.1:9001"])

        with pytest.raises(ProtocolNotSupported):
            AsyncMultiProvider(["ipc://127.0.0.1:9001"])

        with pytest.raises(ProtocolNotSupported):
            AsyncMultiProvider(["ws://127.0.0.1:9001"])

        with pytest.raises(ProtocolNotSupported):
            AsyncMultiProvider(["wss://127.0.0.1:9001"])

    @patch(
        "web3_multi_provider.async_http_provider_proxy.AsyncHTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.async_make_post_request",
        side_effect=mocked_async_request_poa,
    )
    @pytest.mark.asyncio
    async def test_poa_blockchain(self, make_post_request, mock_fetch_chain_id):
        provider = AsyncMultiProvider(["http://127.0.0.1:9000"])

        w3 = AsyncWeb3(provider)

        with self._caplog.at_level(logging.DEBUG):
            block = await w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        # self.assertGreater(self._metrics['response'].return_value.observe.call_count, 0)
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0

        assert {"msg": "PoA blockchain cleanup response."} in [
            log.msg for log in self._caplog.records
        ]
        assert block.get("proofOfAuthorityData") is not None

    @patch(
        "web3_multi_provider.async_http_provider_proxy.AsyncHTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.async_make_post_request",
        side_effect=mocked_async_request_get,
    )
    @pytest.mark.asyncio
    async def test_pos_blockchain(self, make_post_request, mock_fetch_chain_id):
        provider = AsyncMultiProvider(["http://127.0.0.1:9000"])

        w3 = AsyncWeb3(provider)

        with self._caplog.at_level(logging.DEBUG):
            block = await w3.eth.get_block("latest")

        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        # self.assertGreater(self._metrics['response'].return_value.observe.call_count, 0)
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0

        assert {"msg": "PoA blockchain cleanup response."} not in [
            log.msg for log in self._caplog.records
        ]
        assert block.get("proofOfAuthorityData") is None


class TestAsyncFallbackProvider:

    @pytest.fixture(autouse=True)
    def __inject_fixtures(self, caplog, mock_metrics):
        self._caplog = caplog
        self._metrics = mock_metrics

    @pytest.mark.asyncio
    async def test_no_endpoints(self):
        w3 = AsyncWeb3(AsyncFallbackProvider([]))

        with pytest.raises(NoActiveProviderError):
            await w3.eth.get_block("latest")

    @patch(
        "web3_multi_provider.async_http_provider_proxy.AsyncHTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.async_make_post_request",
        side_effect=mocked_async_request_get,
    )
    @pytest.mark.asyncio
    async def test_one_endpoint(self, make_post_request: Mock, mock_fetch_chain_id):
        w3 = AsyncWeb3(
            AsyncFallbackProvider(
                [
                    "http://127.0.0.1:9000",
                ],
                exception_retry_configuration=None,
            )
        )
        await w3.eth.get_block("latest")
        assert self._metrics.rpc_service_requests.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_payload_bytes.return_value.observe.call_count > 0
        # self.assertGreater(self._metrics['response'].return_value.observe.call_count, 0)
        assert self._metrics.rpc_service_responses_total_bytes.return_value.inc.call_count > 0
        assert self._metrics.rpc_service_request_methods.return_value.inc.call_count > 0
        make_post_request.assert_called_once()

    @patch(
        "web3_multi_provider.async_http_provider_proxy.AsyncHTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.async_make_post_request",
        side_effect=mocked_async_request_get,
    )
    @pytest.mark.asyncio
    async def test_first_working(self, make_post_request: Mock, mock_fetch_chain_id):
        w3 = AsyncWeb3(
            AsyncFallbackProvider(
                [
                    "http://127.0.0.1:9000",
                    "http://127.0.0.1:9001",
                ],
                exception_retry_configuration=None,
            )
        )
        await w3.eth.get_block("latest")
        make_post_request.assert_called_once()
        assert make_post_request.call_args.args[0] == "http://127.0.0.1:9000"

    @patch(
        "web3_multi_provider.async_http_provider_proxy.AsyncHTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.async_make_post_request",
        side_effect=mocked_async_request_get,
    )
    @pytest.mark.asyncio
    async def test_all_endpoints_fail(self, make_post_request: Mock, mock_fetch_chain_id):
        w3 = AsyncWeb3(
            AsyncFallbackProvider(
                [
                    "http://127.0.0.1:9001",
                    "http://127.0.0.1:9002",
                    "http://127.0.0.1:9003",
                ],
                exception_retry_configuration=None,
            )
        )

        with pytest.raises(NoActiveProviderError):
            await w3.eth.get_block("latest")

        assert make_post_request.call_count == 3
        assert make_post_request.call_args.args[0] == "http://127.0.0.1:9003"

    @patch(
        "web3_multi_provider.async_http_provider_proxy.AsyncHTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.async_make_post_request",
        side_effect=mocked_async_request_get,
    )
    @pytest.mark.asyncio
    async def test_one_endpoint_works(self, make_post_request: Mock, mock_fetch_chain_id):
        w3 = AsyncWeb3(
            AsyncFallbackProvider(
                [
                    "http://127.0.0.1:9001",
                    "http://127.0.0.1:9000",
                ],
                exception_retry_configuration=None,
            )
        )

        await w3.eth.get_block("latest")
        assert make_post_request.call_count == 2
        assert make_post_request.call_args.args[0] == "http://127.0.0.1:9000"

    @patch(
        "web3_multi_provider.async_http_provider_proxy.AsyncHTTPProviderProxy._fetch_chain_id",
        return_value=1
    )
    @patch(
        "web3._utils.http_session_manager.HTTPSessionManager.async_make_post_request",
        side_effect=mocked_async_request_get,
    )
    @pytest.mark.asyncio
    async def test_starts_from_the_first(self, make_post_request: Mock, mock_fetch_chain_id):
        w3 = AsyncWeb3(
            AsyncFallbackProvider(
                [
                    "http://127.0.0.1:9001",
                    "http://127.0.0.1:9000",
                ],
                exception_retry_configuration=None,
            )
        )

        await w3.eth.get_block("latest")
        await w3.eth.get_block("latest")

        assert make_post_request.call_count == 4
        assert make_post_request.call_args_list[-2].args[0] == "http://127.0.0.1:9001"
