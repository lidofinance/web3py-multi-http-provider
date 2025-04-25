import sys
from unittest.mock import patch

import pytest
from web3.beacon import Beacon

from web3_multi_provider.cl_client_proxy import BeaconProxy


@pytest.fixture
def beacon_proxy():
    return BeaconProxy(base_url='http://127.0.0.1:9001')

@patch.object(Beacon, '_make_get_request', autospec=True)
def test_make_get_request_success(mock_super_get, mock_metrics, beacon_proxy):
    mock_super_get.return_value = {'data': 'value'}

    result = beacon_proxy._make_get_request('some_endpoint')

    assert result == {'data': 'value'}
    mock_super_get.assert_called_once()
    mock_metrics.rpc_service_requests.return_value.inc.assert_called_once()
    mock_metrics.rpc_service_response_payload_bytes.return_value.observe.assert_called_once()

@patch.object(Beacon, '_make_get_request', autospec=True)
def test_make_get_request_with_error(mock_super_get, mock_metrics, beacon_proxy):
    mock_super_get.return_value = {'error': {'code': 1234}}

    result = beacon_proxy._make_get_request('error_endpoint')

    assert 'error' in result
    mock_super_get.assert_called_once()
    mock_metrics.rpc_service_requests.return_value.inc.assert_called_once()
    mock_metrics.rpc_service_response_payload_bytes.return_value.observe.assert_called_once()

@patch.object(Beacon, '_make_post_request', autospec=True)
def test_make_post_request_success(mock_super_post, mock_metrics, beacon_proxy):
    mock_super_post.return_value = {'data': 'post_result'}
    body = {'some': 'body'}

    result = beacon_proxy._make_post_request('post_endpoint', body)

    assert result == {'data': 'post_result'}
    mock_super_post.assert_called_once()
    mock_metrics.rpc_service_requests.return_value.inc.assert_called_once()
    mock_metrics.rpc_service_request_payload_bytes.return_value.observe.assert_called_once_with(sys.getsizeof(body))
    mock_metrics.rpc_service_response_payload_bytes.return_value.observe.assert_called()

@patch.object(Beacon, '_make_post_request', autospec=True)
def test_make_post_request_with_error(mock_super_post, mock_metrics, beacon_proxy):
    mock_super_post.return_value = {'error': {'code': 5678}}
    body = {'invalid': 'request'}

    result = beacon_proxy._make_post_request('post_error_endpoint', body)

    assert 'error' in result
    mock_super_post.assert_called_once()
    mock_metrics.rpc_service_requests.return_value.inc.assert_called_once()
    mock_metrics.rpc_service_request_payload_bytes.return_value.observe.assert_called_once_with(sys.getsizeof(body))
    mock_metrics.rpc_service_response_payload_bytes.return_value.observe.assert_called()
