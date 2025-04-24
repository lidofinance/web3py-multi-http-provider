from unittest.mock import AsyncMock, patch

import pytest
from web3 import AsyncHTTPProvider
from web3.types import RPCEndpoint

from web3_multi_provider.async_http_provider_proxy import AsyncHTTPProviderProxy

pytestmark = pytest.mark.asyncio


@pytest.fixture
def proxy():
    return AsyncHTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")


async def test_make_request_success_initializes_chain_info(proxy, mock_metrics):
    with (
        patch.object(proxy, "_fetch_chain_id", return_value=1),
        patch.object(AsyncHTTPProvider, "make_request", new_callable=AsyncMock) as super_request,
    ):
        super_request.return_value = {"result": "0x123"}
        result = await proxy.make_request(RPCEndpoint("eth_blockNumber"), [])

        assert result["result"] == "0x123"
        assert proxy._chain_id == 1
        assert proxy._network == "ethereum"
        mock_metrics.rpc_service_requests.return_value.inc.assert_called_once()


async def test_make_request_handles_error_response(proxy, mock_metrics):
    with (
        patch.object(proxy, "_fetch_chain_id", return_value=1),
        patch.object(AsyncHTTPProvider, "make_request", new_callable=AsyncMock) as super_request,
    ):
        super_request.return_value = {"error": "something went wrong"}
        result = await proxy.make_request(RPCEndpoint("eth_call"), [])

        assert "error" in result
        mock_metrics.rpc_service_requests.return_value.inc.assert_called_once()


async def test_fetch_chain_id_success(proxy):
    with patch.object(AsyncHTTPProvider, "make_request", new_callable=AsyncMock) as mock_make_request:
        mock_make_request.return_value = {"result": "0x2a"}
        chain_id = await proxy._fetch_chain_id()
        assert chain_id == 42


async def test_fetch_chain_id_failure(proxy):
    with patch.object(AsyncHTTPProvider, "make_request", new_callable=AsyncMock) as mock_make_request:
        mock_make_request.side_effect = Exception("RPC error")
        with pytest.raises(RuntimeError, match="Failed to fetch chain ID"):
            await proxy._fetch_chain_id()


def test_encode_rpc_request_records_payload(proxy, mock_metrics):
    proxy._network = "ethereum"
    proxy._chain_id = 1
    proxy._uri = "infura.io"

    payload = proxy.encode_rpc_request(RPCEndpoint("eth_getBalance"), ["0xabc", "latest"])
    assert isinstance(payload, bytes)
    mock_metrics.rpc_service_request_payload_bytes.return_value.observe.assert_called_once()


def test_decode_rpc_response_records_size(proxy, mock_metrics):
    proxy._network = "ethereum"
    proxy._chain_id = 1
    proxy._uri = "infura.io"

    raw = b'{"jsonrpc":"2.0","id":1,"result":"0x1"}'
    result = proxy.decode_rpc_response(raw)

    assert result["result"] == "0x1"
    mock_metrics.rpc_service_response_payload_bytes.return_value.observe.assert_called_once_with(len(raw))
