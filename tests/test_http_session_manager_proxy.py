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
    mock_response.json = MagicMock(return_value={"error": {"code": "123"}})

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
            'ethereum', 'el', '1', 'https://node.example', 'eth_chainId', 'success', '123'
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
            'ethereum', 'cl', 'beacon', 'https://beacon.example', '/eth/v1/beacon/blocks/{hash}/root', 'success', ''
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
            'ethereum', 'cl', 'beacon', 'https://beacon.example', '/eth/v1/validator/duties/{num}', 'success', ''
        )
