import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from web3_multi_provider.http_session_manager_proxy import HTTPSessionManagerProxy
from web3_multi_provider import metrics


@pytest.fixture
def proxy():
    return HTTPSessionManagerProxy(chain_id="1", uri="https://node.example", network="ethereum")


@pytest.fixture
def mock_metric():
    with patch.object(metrics._HTTP_RPC_SERVICE_REQUESTS, "labels", return_value=MagicMock()) as mock_labels:
        yield mock_labels


def test_get_response_from_get_request(proxy, mock_metric):
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "get_response_from_get_request",
        return_value=mock_response,
    ) as super_mock:
        response = HTTPSessionManagerProxy.get_response_from_get_request(proxy, "https://example.com")
        assert response == mock_response
        mock_metric.assert_called_with('ethereum', 'unknown', '1', 'https://node.example', 'False', '200')
        mock_metric.return_value.inc.assert_called_once()


def test_get_response_from_post_request(proxy, mock_metric):
    mock_response = MagicMock()
    mock_response.status_code = 201

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "get_response_from_post_request",
        return_value=mock_response,
    ) as super_mock:
        response = HTTPSessionManagerProxy.get_response_from_post_request(proxy, "https://example.com")
        assert response == mock_response
        mock_metric.assert_called_with('ethereum', 'unknown', '1', 'https://node.example', 'False', '201')
        mock_metric.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_async_get_response_from_get_request(proxy, mock_metric):
    mock_response = AsyncMock()
    mock_response.status = 200

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "async_get_response_from_get_request",
        return_value=mock_response,
    ) as super_mock:
        response = await HTTPSessionManagerProxy.async_get_response_from_get_request(proxy, "https://example.com")
        assert response == mock_response
        mock_metric.assert_called_with('ethereum', 'unknown', '1', 'https://node.example', 'False', '200')
        mock_metric.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_async_get_response_from_post_request(proxy, mock_metric):
    mock_response = AsyncMock()
    mock_response.status = 500

    with patch.object(
        HTTPSessionManagerProxy.__bases__[0],
        "async_get_response_from_post_request",
        return_value=mock_response,
    ) as super_mock:
        response = await HTTPSessionManagerProxy.async_get_response_from_post_request(proxy, "https://example.com")
        assert response == mock_response
        mock_metric.assert_called_with('ethereum', 'unknown', '1', 'https://node.example', 'False', '500')
        mock_metric.return_value.inc.assert_called_once()
