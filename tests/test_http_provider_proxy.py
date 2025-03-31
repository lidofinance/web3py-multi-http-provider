from unittest.mock import patch

import pytest
from web3.types import RPCEndpoint

from web3_multi_provider.exceptions import ProviderInitialization
from web3_multi_provider.http_provider_proxy import HTTPProviderProxy


@patch("web3_multi_provider.http_provider_proxy.HTTPProvider.make_request")
def test_initialization_fetches_chain_id_success(mock_make_request, mock_metrics):
    mock_make_request.return_value = {"result": "0x1"}
    provider = HTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")

    assert provider._chain_id == "1"
    assert provider._network == "ethereum"
    assert hasattr(provider, "_request_session_manager")


@patch("web3_multi_provider.http_provider_proxy.HTTPProvider.make_request")
def test_initialization_fails_on_chain_id_fetch(mock_make_request):
    mock_make_request.side_effect = Exception("nope")
    with pytest.raises(ProviderInitialization, match="Failed to fetch chain ID"):
        HTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")


@patch("web3_multi_provider.http_provider_proxy.HTTPProvider.make_request")
def test_make_request_success_sets_status_success(mock_make_request, mock_metrics):
    mock_make_request.side_effect = [
        {"result": "0x1"},
        {"result": "0x123"},
    ]
    provider = HTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")
    result = provider.make_request(RPCEndpoint("eth_blockNumber"), [])

    assert result["result"] == "0x123"
    mock_metrics.rpc_service_requests.return_value.inc.assert_called_once()
    mock_metrics.rpc_service_request_methods.return_value.inc.assert_called_once()


@patch("web3_multi_provider.http_provider_proxy.HTTPProvider.make_request")
def test_make_request_failure_sets_status_fail(mock_make_request, mock_metrics):
    mock_make_request.side_effect = [
        {"result": "0x1"},
        {"error": "some failure"},
    ]
    provider = HTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")
    result = provider.make_request(RPCEndpoint("eth_call"), [])

    assert "error" in result
    mock_metrics.rpc_service_requests.return_value.inc.assert_called_once()
    mock_metrics.rpc_service_request_methods.return_value.inc.assert_called_once()


@patch("web3_multi_provider.http_provider_proxy.HTTPProvider.make_request")
@patch("web3_multi_provider.http_provider_proxy.HTTPProvider.encode_rpc_request")
def test_encode_rpc_request_records_payload(mock_encode, mock_make_request, mock_metrics):
    mock_make_request.return_value = {"result": "0x1"}
    mock_encode.return_value = b'{"jsonrpc":"2.0"}'

    provider = HTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")
    result = provider.encode_rpc_request(RPCEndpoint("eth_call"), [])

    assert isinstance(result, bytes)
    mock_metrics.rpc_service_request_payload_bytes.return_value.observe.assert_called_once_with(len(result))


@patch("web3_multi_provider.http_provider_proxy.HTTPProvider.make_request")
@patch("web3_multi_provider.http_provider_proxy.JSONBaseProvider.decode_rpc_response")
def test_decode_rpc_response_records_bytes(mock_decode, mock_make_request, mock_metrics):
    mock_make_request.return_value = {"result": "0x1"}
    mock_decode.return_value = {"result": "0xabc"}
    provider = HTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")

    raw = b'{"jsonrpc":"2.0","result":"0xabc"}'
    result = provider.decode_rpc_response(raw)
    assert result["result"] == "0xabc"
    mock_metrics.rpc_service_responses_total_bytes.return_value.inc.assert_called_once_with(len(raw))
