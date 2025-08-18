from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web3_multi_provider.http_session_manager_proxy import HTTPSessionManagerProxy


@pytest.fixture
def proxy_el():
    return HTTPSessionManagerProxy(
        chain_id="1",
        uri="https://node.example",
        network="ethereum",
        layer="el",
    )


@pytest.fixture
def proxy_cl():
    return HTTPSessionManagerProxy(
        chain_id="beacon",
        uri="https://beacon.example",
        network="ethereum",
        layer="cl",
    )


def test_get_response_from_get_request_records_http_counter(proxy_el, mock_metrics):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Length": "123"}

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "get_response_from_get_request",
        return_value=mock_response,
    ):
        response = HTTPSessionManagerProxy.get_response_from_get_request(proxy_el, "https://example.com")
        assert response == mock_response
        mock_metrics.http_rpc_service_requests.assert_called_with(
            'ethereum', 'el', '1', 'https://node.example', 'False', '200', 'success'
        )
        mock_metrics.http_rpc_service_requests.return_value.inc.assert_called_once()
        # Response payload metric observed with exact size from Content-Length
        mock_metrics.rpc_service_response_payload_bytes.return_value.observe.assert_called_with(123)


def test_post_request_records_payload_and_rpc_request_for_el(proxy_el, mock_metrics):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_response.json = MagicMock(return_value={})

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "get_response_from_post_request",
        return_value=mock_response,
    ):
        response = HTTPSessionManagerProxy.get_response_from_post_request(
            proxy_el,
            "https://example.com",
            json={"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1},
        )
        assert response == mock_response
        # HTTP counter
        mock_metrics.http_rpc_service_requests.assert_called_with(
            'ethereum', 'el', '1', 'https://node.example', 'False', '200', 'success'
        )
        # Request payload metric observed
        mock_metrics.rpc_service_request_payload_bytes.assert_called()
        # _RPC_REQUEST emitted with method label
        mock_metrics.rpc_service_requests.assert_called_with(
            'ethereum', 'el', '1', 'https://node.example', 'eth_chainId', 'success', ''
        )
        mock_metrics.rpc_service_requests.return_value.inc.assert_called()


@pytest.mark.asyncio
async def test_async_post_records_payload_and_rpc_request_for_el(proxy_el, mock_metrics):
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.content_length = 321

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "async_get_response_from_post_request",
        return_value=mock_response,
    ):
        response = await HTTPSessionManagerProxy.async_get_response_from_post_request(
            proxy_el,
            "https://example.com",
            json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
        )
        assert response == mock_response
        mock_metrics.rpc_service_request_payload_bytes.assert_called()
        mock_metrics.rpc_service_response_payload_bytes.return_value.observe.assert_called_with(321)
        mock_metrics.rpc_service_requests.assert_called_with(
            'ethereum', 'el', '1', 'https://node.example', 'eth_blockNumber', 'success', ''
        )


def test_post_request_bytes_size_assert(proxy_el, mock_metrics):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {}
    body = b'{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}'

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "get_response_from_post_request",
        return_value=mock_response,
    ):
        HTTPSessionManagerProxy.get_response_from_post_request(
            proxy_el,
            "https://example.com",
            data=body,
        )
    mock_metrics.rpc_service_request_payload_bytes.return_value.observe.assert_called_with(len(body))


def test_observes_duration(proxy_el, mock_metrics, monkeypatch):
    # Make perf_counter deterministic: start at 0.0, end at 0.5
    seq = iter([0.0, 0.5])
    monkeypatch.setattr(
        "web3_multi_provider.http_session_manager_proxy.time.perf_counter",
        lambda: next(seq),
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {}

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "get_response_from_get_request",
        return_value=mock_response,
    ):
        HTTPSessionManagerProxy.get_response_from_get_request(proxy_el, "https://example.com")

    mock_metrics.rpc_service_response_seconds.return_value.observe.assert_called_with(0.5)


def test_cl_get_records_normalized_path_as_method(proxy_cl, mock_metrics):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {}
    dynamic_hex = "0x" + "a" * 64

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "get_response_from_get_request",
        return_value=mock_response,
    ):
        response = HTTPSessionManagerProxy.get_response_from_get_request(
            proxy_cl,
            f"https://beacon.example/eth/v1/beacon/blocks/{dynamic_hex}/root",
        )
        assert response == mock_response
        # method label should be normalized path
        mock_metrics.rpc_service_requests.assert_called_with(
            'ethereum', 'cl', 'beacon', 'https://beacon.example', '/eth/v1/beacon/blocks/{block_id}/root', 'success', ''
        )


@pytest.mark.asyncio
async def test_async_cl_get_records_normalized_path_as_method(proxy_cl, mock_metrics):
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.content_length = None
    dynamic_num = "123456"

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "async_get_response_from_get_request",
        return_value=mock_response,
    ):
        response = await HTTPSessionManagerProxy.async_get_response_from_get_request(
            proxy_cl,
            f"https://beacon.example/eth/v1/validator/duties/{dynamic_num}",
        )
        assert response == mock_response
        mock_metrics.rpc_service_requests.assert_called_with(
            'ethereum', 'cl', 'beacon', 'https://beacon.example', '/eth/v1/validator/duties/{epoch}', 'success', ''
        )


@pytest.mark.asyncio
async def test_async_make_post_request_records_metrics(proxy_el, mock_metrics):
    content = b'{"jsonrpc":"2.0","result":"0x1","id":1}'
    
    # Mock aiohttp ClientResponse
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {}
    mock_response.content_length = len(content)
    mock_response.read = AsyncMock(return_value=content)
    
    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "async_get_response_from_post_request",
        return_value=mock_response,
    ):
        result = await proxy_el.async_make_post_request(
            "https://example.com",
            data=b'{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}',
        )
        assert result == content
        # Should record request payload, response payload, RPC request, and duration
        mock_metrics.rpc_service_request_payload_bytes.assert_called()
        mock_metrics.rpc_service_response_payload_bytes.return_value.observe.assert_called_with(len(content))
        mock_metrics.rpc_service_requests.assert_called_with(
            'ethereum', 'el', '1', 'https://node.example', 'eth_chainId', 'success', ''
        )
        mock_metrics.rpc_service_response_seconds.assert_called()


class TestBeaconAPIPathNormalization:
    """Test Beacon API path normalization patterns"""
    
    @pytest.fixture
    def proxy_cl(self):
        return HTTPSessionManagerProxy(
            chain_id="beacon",
            uri="https://beacon.example",
            network="ethereum",
            layer="cl",
        )
    
    def test_normalize_cl_path_block_identifiers(self, proxy_cl):
        """Test block ID normalization in various contexts"""
        test_cases = [
            # Basic blocks
            ("https://beacon.example/eth/v1/beacon/blocks/12345", "/eth/v1/beacon/blocks/{block_id}"),
            ("https://beacon.example/eth/v1/beacon/blocks/head", "/eth/v1/beacon/blocks/{block_id}"),
            ("https://beacon.example/eth/v1/beacon/blocks/0xabc123", "/eth/v1/beacon/blocks/{block_id}"),
            # Blinded blocks
            ("https://beacon.example/eth/v1/beacon/blinded_blocks/12345", "/eth/v1/beacon/blinded_blocks/{block_id}"),
            # Blob sidecars
            ("https://beacon.example/eth/v1/beacon/blob_sidecars/12345", "/eth/v1/beacon/blob_sidecars/{block_id}"),
            # Block rewards
            ("https://beacon.example/eth/v1/beacon/rewards/blocks/12345", "/eth/v1/beacon/rewards/blocks/{block_id}"),
            # Sync committee rewards
            ("https://beacon.example/eth/v1/beacon/rewards/sync_committee/12345", "/eth/v1/beacon/rewards/sync_committee/{block_id}"),
        ]
        
        for url, expected in test_cases:
            normalized = proxy_cl._normalize_cl_path(url)
            assert normalized == expected, f"Failed for {url}: got {normalized}, expected {expected}"
    
    def test_normalize_cl_path_state_identifiers(self, proxy_cl):
        """Test state ID normalization"""
        test_cases = [
            ("https://beacon.example/eth/v1/beacon/states/12345", "/eth/v1/beacon/states/{state_id}"),
            ("https://beacon.example/eth/v1/beacon/states/head", "/eth/v1/beacon/states/{state_id}"),
            ("https://beacon.example/eth/v1/beacon/states/finalized/validators", "/eth/v1/beacon/states/{state_id}/validators"),
        ]
        
        for url, expected in test_cases:
            normalized = proxy_cl._normalize_cl_path(url)
            assert normalized == expected, f"Failed for {url}: got {normalized}, expected {expected}"
    
    def test_normalize_cl_path_validator_identifiers(self, proxy_cl):
        """Test validator ID normalization"""
        test_cases = [
            ("https://beacon.example/eth/v1/beacon/states/head/validators/12345", "/eth/v1/beacon/states/{state_id}/validators/{validator_id}"),
            ("https://beacon.example/eth/v1/beacon/states/head/validators/all", "/eth/v1/beacon/states/{state_id}/validators/{validator_id}"),
        ]
        
        for url, expected in test_cases:
            normalized = proxy_cl._normalize_cl_path(url)
            assert normalized == expected, f"Failed for {url}: got {normalized}, expected {expected}"
    
    def test_normalize_cl_path_epoch_identifiers(self, proxy_cl):
        """Test epoch normalization in duties and rewards"""
        test_cases = [
            ("https://beacon.example/eth/v1/validator/duties/attester/12345", "/eth/v1/validator/duties/attester/{epoch}"),
            ("https://beacon.example/eth/v1/validator/duties/proposer/12345", "/eth/v1/validator/duties/proposer/{epoch}"),
            ("https://beacon.example/eth/v1/validator/duties/sync/12345", "/eth/v1/validator/duties/sync/{epoch}"),
            ("https://beacon.example/eth/v1/beacon/rewards/attestations/12345", "/eth/v1/beacon/rewards/attestations/{epoch}"),
            ("https://beacon.example/eth/v1/validator/liveness/12345", "/eth/v1/validator/liveness/{epoch}"),
        ]
        
        for url, expected in test_cases:
            normalized = proxy_cl._normalize_cl_path(url)
            assert normalized == expected, f"Failed for {url}: got {normalized}, expected {expected}"
    
    def test_normalize_cl_path_validator_blocks_slot(self, proxy_cl):
        """Test validator blocks use {slot} not {block_id}"""
        test_cases = [
            ("https://beacon.example/eth/v3/validator/blocks/12345", "/eth/v3/validator/blocks/{slot}"),
            ("https://beacon.example/eth/v2/validator/blocks/12345", "/eth/v2/validator/blocks/{slot}"),
        ]
        
        for url, expected in test_cases:
            normalized = proxy_cl._normalize_cl_path(url)
            assert normalized == expected, f"Failed for {url}: got {normalized}, expected {expected}"
    
    def test_normalize_cl_path_light_client_bootstrap(self, proxy_cl):
        """Test light client bootstrap uses {block_root}"""
        url = "https://beacon.example/eth/v1/beacon/light_client/bootstrap/0x" + "a" * 64
        expected = "/eth/v1/beacon/light_client/bootstrap/{block_root}"
        normalized = proxy_cl._normalize_cl_path(url)
        assert normalized == expected
    
    def test_normalize_cl_path_peer_identifiers(self, proxy_cl):
        """Test peer ID normalization"""
        test_cases = [
            ("https://beacon.example/eth/v1/node/peers/16Uiu2HAm", "/eth/v1/node/peers/{peer_id}"),
            ("https://beacon.example/eth/v1/node/peers/enr:-IS4Q", "/eth/v1/node/peers/{peer_id}"),
        ]
        
        for url, expected in test_cases:
            normalized = proxy_cl._normalize_cl_path(url)
            assert normalized == expected, f"Failed for {url}: got {normalized}, expected {expected}"
    
    def test_normalize_cl_path_committee_indices(self, proxy_cl):
        """Test committee index normalization"""
        url = "https://beacon.example/eth/v1/beacon/states/head/committees/123"
        expected = "/eth/v1/beacon/states/{state_id}/committees/{committee_index}"
        normalized = proxy_cl._normalize_cl_path(url)
        assert normalized == expected
    
    def test_normalize_cl_path_generic_roots(self, proxy_cl):
        """Test generic hex root normalization"""
        url = "https://beacon.example/eth/v1/beacon/blocks/0x" + "a" * 64 + "/root"
        expected = "/eth/v1/beacon/blocks/{block_id}/root"
        normalized = proxy_cl._normalize_cl_path(url)
        assert normalized == expected
    
    def test_normalize_cl_path_preserves_literals(self, proxy_cl):
        """Test that literal path segments are preserved"""
        url = "https://beacon.example/eth/v1/node/health"
        expected = "/eth/v1/node/health"
        normalized = proxy_cl._normalize_cl_path(url)
        assert normalized == expected


def test_extract_methods_el_single_request(proxy_el):
    """Test EL method extraction from single JSON-RPC request"""
    kwargs = {"json": {"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}}
    methods = proxy_el._extract_methods("https://example.com", kwargs)
    assert methods == ["eth_chainId"]


def test_extract_methods_el_batch_request(proxy_el):
    """Test EL method extraction from batch JSON-RPC request"""
    kwargs = {
        "json": [
            {"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1},
            {"jsonrpc": "2.0", "method": "eth_getBalance", "params": ["0x..", "latest"], "id": 2},
        ]
    }
    methods = proxy_el._extract_methods("https://example.com", kwargs)
    assert methods == ["eth_chainId", "eth_getBalance"]


def test_extract_methods_el_from_bytes_data(proxy_el):
    """Test EL method extraction from bytes data"""
    data = b'{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'
    kwargs = {"data": data}
    methods = proxy_el._extract_methods("https://example.com", kwargs)
    assert methods == ["eth_blockNumber"]


def test_extract_methods_cl_normalized_path(proxy_cl):
    """Test CL method extraction returns normalized path"""
    methods = proxy_cl._extract_methods("https://beacon.example/eth/v1/beacon/blocks/12345", {})
    assert methods == ["/eth/v1/beacon/blocks/{block_id}"]


def test_extract_methods_invalid_json(proxy_el):
    """Test method extraction handles invalid JSON gracefully"""
    kwargs = {"data": b"invalid json"}
    methods = proxy_el._extract_methods("https://example.com", kwargs)
    assert methods is None


def test_extract_methods_no_method_field(proxy_el):
    """Test method extraction handles missing method field"""
    kwargs = {"json": {"jsonrpc": "2.0", "params": [], "id": 1}}  # No method field
    methods = proxy_el._extract_methods("https://example.com", kwargs)
    assert methods is None


@pytest.mark.asyncio
async def test_async_make_post_request_failure_records_fail(proxy_el, mock_metrics):
    """Test that failed async requests record 'fail' status"""
    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "async_get_response_from_post_request",
        side_effect=Exception("Network error"),
    ):
        with pytest.raises(Exception):
            await proxy_el.async_make_post_request(
                "https://example.com",
                data=b'{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}',
            )
        
        # Should still record metrics with 'fail' status
        mock_metrics.rpc_service_request_payload_bytes.assert_called()
        mock_metrics.rpc_service_requests.assert_called_with(
            'ethereum', 'el', '1', 'https://node.example', 'eth_chainId', 'fail', ''
        )
        mock_metrics.rpc_service_response_seconds.assert_called()
