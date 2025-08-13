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