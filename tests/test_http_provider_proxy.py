from unittest.mock import patch

import pytest
import requests
import responses
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint

from web3_multi_provider.http_provider_proxy import HTTPProviderProxy
from web3_multi_provider.http_session_manager_proxy import _rpc_error_code


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
    assert provider._request_session_manager is not None

    provider.make_request(RPCEndpoint("eth_blockNumber"), [])

    assert provider._chain_id == "1"
    assert provider._network == "ethereum"
    assert mock_make_request.call_count == 2


@patch("web3_multi_provider.http_provider_proxy.HTTPProvider.make_request")
def test_initialization_fails_on_chain_id_fetch(mock_make_request):
    mock_make_request.side_effect = Exception("nope")
    provider = HTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")

    assert provider._chain_id == ""

    with pytest.raises(Exception, match="nope"):
        provider.make_request(RPCEndpoint("eth_blockNumber"), [])

_URL = "http://rpc.example"
_RPC_ERROR = '{"jsonrpc": "2.0", "id": 0, "error": {"code": -32000, "message": "header not found"}}'


def _proxy(**kwargs) -> HTTPProviderProxy:
    kwargs.setdefault("exception_retry_configuration", None)
    return HTTPProviderProxy(endpoint_uri=_URL, **kwargs)


@pytest.mark.parametrize(
    "status, content_type, body",
    [
        (503, "text/plain", "Service Unavailable"),
        (429, "text/plain", "Too Many Requests"),
        (413, "text/html", "<html>Request Entity Too Large</html>"),
        (404, "text/html", "<html>Not Found</html>"),
        (503, "application/json", _RPC_ERROR),
    ],
)
@patch("web3_multi_provider.http_provider_proxy.HTTPProviderProxy._fetch_chain_id", return_value=1)
@responses.activate
def test_http_error_keeps_its_status_whatever_the_body(mock_fetch_chain_id, status, content_type, body, mock_metrics):
    responses.add(responses.POST, _URL, body=body, status=status, content_type=content_type)

    with pytest.raises(requests.HTTPError) as error:
        _proxy().make_request(RPCEndpoint("eth_blockNumber"), [])

    assert error.value.response.status_code == status


@pytest.mark.parametrize("content_type, body", [("text/plain", "Service Unavailable"), ("application/json", _RPC_ERROR)])
@patch("web3_multi_provider.http_provider_proxy.HTTPProviderProxy._fetch_chain_id", return_value=1)
@responses.activate
def test_http_error_is_retried_whatever_the_body(mock_fetch_chain_id, content_type, body, mock_metrics):
    responses.add(responses.POST, _URL, body=body, status=503, content_type=content_type)
    retries = ExceptionRetryConfiguration(errors=(requests.HTTPError,), retries=3, backoff_factor=0)

    with pytest.raises(requests.HTTPError):
        _proxy(exception_retry_configuration=retries).make_request(RPCEndpoint("eth_blockNumber"), [])

    assert len(responses.calls) == 3


@patch("web3_multi_provider.http_provider_proxy.HTTPProviderProxy._fetch_chain_id", return_value=1)
@responses.activate
def test_batch_request(mock_fetch_chain_id, mock_metrics):
    body = '[{"jsonrpc": "2.0", "id": 0, "result": "0x10"}, {"jsonrpc": "2.0", "id": 1, "result": "0x1"}]'
    responses.add(responses.POST, _URL, body=body, status=200, content_type="application/json")

    result = _proxy().make_batch_request([(RPCEndpoint("eth_blockNumber"), []), (RPCEndpoint("eth_chainId"), [])])

    assert [r["result"] for r in result] == ["0x10", "0x1"]


@patch("web3_multi_provider.http_provider_proxy.HTTPProviderProxy._fetch_chain_id", return_value=1)
@responses.activate
def test_error_that_is_not_an_object_is_returned_to_web3(mock_fetch_chain_id, mock_metrics):
    body = '{"jsonrpc": "2.0", "id": 0, "error": "rate limited"}'
    responses.add(responses.POST, _URL, body=body, status=200, content_type="application/json")

    assert _proxy().make_request(RPCEndpoint("eth_blockNumber"), [])["error"] == "rate limited"


@pytest.mark.parametrize(
    "status, body, result, rpc_error_code",
    [
        (200, '{"jsonrpc": "2.0", "id": 0, "result": "0x10"}', "success", ""),
        (200, _RPC_ERROR, "success", "-32000"),
        (503, _RPC_ERROR, "fail", "-32000"),
        (503, "Service Unavailable", "fail", ""),
    ],
)
@patch("web3_multi_provider.http_provider_proxy.HTTPProviderProxy._fetch_chain_id", return_value=1)
@responses.activate
def test_metrics_record_http_result_and_rpc_error_code(mock_fetch_chain_id, status, body, result, rpc_error_code, mock_metrics):
    responses.add(responses.POST, _URL, body=body, status=status)

    try:
        _proxy().make_request(RPCEndpoint("eth_blockNumber"), [])
    except requests.HTTPError:
        pass

    *_, code, http_result = mock_metrics.http_rpc_service_requests.call_args.args
    *_, method, rpc_result, error_code = mock_metrics.rpc_service_requests.call_args.args
    assert (code, http_result) == (str(status), result)
    assert (method, rpc_result, error_code) == ("eth_blockNumber", result, rpc_error_code)


@pytest.mark.parametrize(
    "body, expected",
    [
        (b'{"error": {"code": -32000}}', "-32000"),
        (b'{"error": {"message": "no code"}}', ""),
        (b'{"error": "rate limited"}', ""),
        (b'{"result": "0x1"}', ""),
        (b'[{"error": {"code": -32000}}]', ""),
        (b"<html>Bad Gateway</html>", ""),
        (b"", ""),
        (b"\xff\xfe", ""),
    ],
)
def test_rpc_error_code_never_raises(body, expected):
    response = requests.Response()
    response._content = body

    assert _rpc_error_code(response) == expected
