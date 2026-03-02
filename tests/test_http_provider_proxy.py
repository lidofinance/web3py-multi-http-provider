from unittest.mock import patch

import pytest
from web3.types import RPCEndpoint

from web3_multi_provider.http_provider_proxy import HTTPProviderProxy


@patch("web3_multi_provider.http_provider_proxy.HTTPProvider.make_request")
def test_initialization_fetches_chain_id_success(mock_make_request, mock_metrics):
    mock_make_request.side_effect = [
        {"result": "0x1"},
        {"result": "0x123"},
        RuntimeError("unexpected call"),
    ]
    provider = HTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")

    assert provider._chain_id == ""
    assert provider._network == ""
    assert provider._request_session_manager is None

    provider.make_request(RPCEndpoint("eth_blockNumber"), [])

    assert provider._chain_id == "1"
    assert provider._network == "ethereum"
    assert provider._request_session_manager is not None
    assert mock_make_request.call_count == 2


@patch("web3_multi_provider.http_provider_proxy.HTTPProvider.make_request")
def test_initialization_fails_on_chain_id_fetch(mock_make_request):
    mock_make_request.side_effect = Exception("nope")
    provider = HTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")

    assert provider._chain_id == ""

    with pytest.raises(Exception, match="nope"):
        provider.make_request(RPCEndpoint("eth_blockNumber"), [])