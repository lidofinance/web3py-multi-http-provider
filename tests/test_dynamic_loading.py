import sys
from unittest.mock import patch

import pytest
from prometheus_client import CollectorRegistry, Counter
from web3.types import RPCEndpoint


@pytest.mark.parametrize("prometheus_installed", [True, False])
def test_http_provider_proxy_with_metrics_backends(prometheus_installed, monkeypatch):
    if not prometheus_installed:
        monkeypatch.setitem(sys.modules, "prometheus_client", None)

    import web3_multi_provider.metrics as metrics

    if prometheus_installed:
        test_registry = CollectorRegistry()
        metrics.init_all_metrics(registry=test_registry)
    else:
        metrics.init_all_metrics()  # will fall back to DummyMetric if prometheus_client missing

    # Now test normally
    with patch("web3_multi_provider.http_provider_proxy.HTTPProvider.make_request") as mock_make_request:
        mock_make_request.side_effect = [
            {"result": "0x1"}, {"result": "0xabc"}
        ]

        from web3_multi_provider.http_provider_proxy import HTTPProviderProxy

        provider = HTTPProviderProxy(endpoint_uri="https://mainnet.infura.io/v3/test")
        result = provider.make_request(RPCEndpoint("eth_blockNumber"), [])

        assert result["result"] == "0xabc"

        metric_obj = metrics.RPC_SERVICE_REQUESTS.labels("ethereum", "1", provider._uri, "success")
        if prometheus_installed:
            assert isinstance(metrics.RPC_SERVICE_REQUESTS, Counter)
        else:
            assert metric_obj.__class__.__name__ == "DummyMetric"
