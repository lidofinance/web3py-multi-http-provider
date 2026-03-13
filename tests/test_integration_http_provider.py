import os
from urllib.parse import urlparse

import pytest
from web3 import Web3

from web3_multi_provider import MultiProvider


INTEGRATION_RPC_URLS_ENV = "WEB3_MULTI_PROVIDER_INTEGRATION_RPC_URLS"


def _get_integration_rpc_urls() -> list[str]:
    raw_value = os.getenv(INTEGRATION_RPC_URLS_ENV, "")
    return [url.strip() for url in raw_value.split(",") if url.strip()]


@pytest.mark.integration
def test_multi_provider_from_env_happy_path():
    endpoint_urls = _get_integration_rpc_urls()

    if not endpoint_urls:
        pytest.skip(
            f"Set {INTEGRATION_RPC_URLS_ENV} to a comma-separated list of RPC URLs "
            "to run integration tests."
        )

    provider = MultiProvider(endpoint_urls, exception_retry_configuration=None)
    w3 = Web3(provider)

    block = w3.eth.get_block("latest")

    assert block is not None
    assert block["number"] >= 0
