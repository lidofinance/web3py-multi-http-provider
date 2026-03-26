import warnings
from unittest.mock import patch

import pytest

from web3_multi_provider import AsyncMultiProvider, MultiProvider
from web3_multi_provider.metrics import MetricsConfig, init_metrics


@pytest.fixture(autouse=True)
def reset_metrics_initialized():
    """Reset _metrics_initialized to False before each test in this module."""
    with patch("web3_multi_provider.metrics._metrics_initialized", False):
        yield


def test_warns_when_prometheus_installed_and_metrics_not_initialized():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        MultiProvider(["http://localhost:8545"])

    assert len(caught) == 1
    assert issubclass(caught[0].category, UserWarning)
    assert "init_metrics()" in str(caught[0].message)


def test_no_warning_when_metrics_initialized():
    init_metrics(MetricsConfig(namespace="test_warn"))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        MultiProvider(["http://localhost:8545"])

    assert len(caught) == 0


def test_no_warning_when_prometheus_not_installed():
    with patch.dict("sys.modules", {"prometheus_client": None}):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            MultiProvider(["http://localhost:8545"])

    assert len(caught) == 0


def test_async_provider_warns_when_metrics_not_initialized():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        AsyncMultiProvider(["http://localhost:8545"])

    assert len(caught) == 1
    assert issubclass(caught[0].category, UserWarning)
    assert "init_metrics()" in str(caught[0].message)
