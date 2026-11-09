import logging
import traceback

import pytest

from web3_multi_provider import (
    AsyncFallbackProvider,
    ChainIdMismatchError,
    FallbackProvider,
    NoActiveProviderError,
    ProviderRequestError,
)
from web3_multi_provider.util import REDACTED, redact_endpoint

KEY = "SENTINELAPIKEY123"
DEAD_ENDPOINTS = [f"http://127.0.0.1:1/v2/{KEY}", f"http://127.0.0.1:1/rpc?dkey={KEY}"]


@pytest.mark.parametrize(
    "uri,text,expected",
    [
        (f"https://x.io/v2/{KEY}", f"failed https://x.io/v2/{KEY}", f"failed {REDACTED}"),
        (f"https://x.io/v2/{KEY}", f"Max retries exceeded with url: /v2/{KEY}", f"Max retries exceeded with url: {REDACTED}"),
        (f"https://x.io/rpc?dkey={KEY}", f"url: /rpc?dkey={KEY}", f"url: {REDACTED}"),
        (f"https://user:{KEY}@x.io/", f"auth {KEY} failed", f"auth {REDACTED} failed"),
        ("https://x.io/", "path / stays", "path / stays"),
    ],
)
def test_redact_endpoint(uri, text, expected):
    assert redact_endpoint(text, uri) == expected


def _dead(provider) -> None:
    """Make every endpoint fail the way urllib3 does: quoting the URL path, with a cause that repeats it."""

    def fail(uri):
        path = uri.split("127.0.0.1:1", 1)[1]
        try:
            raise OSError(f"Failed to connect to {uri}")
        except OSError as cause:
            raise ConnectionError(f"Max retries exceeded with url: {path}") from cause

    for inner in provider._providers:
        if isinstance(provider, AsyncFallbackProvider):

            async def make_request(*_, _uri=str(inner.endpoint_uri)):
                fail(_uri)

        else:

            def make_request(*_, _uri=str(inner.endpoint_uri)):
                fail(_uri)

        inner.make_request = make_request


def _assert_redacted(error: NoActiveProviderError, caplog) -> None:
    assert KEY not in "".join(traceback.format_exception(error))
    library_logs = [r.getMessage() for r in caplog.records if r.name.startswith("web3_multi_provider")]
    assert any("Provider not responding." in line for line in library_logs)
    assert not any(KEY in line for line in library_logs)
    assert len(error.exceptions) == len(DEAD_ENDPOINTS)
    for sub in error.exceptions:
        assert isinstance(sub, ProviderRequestError)
        assert str(sub) == f"ConnectionError: Max retries exceeded with url: {REDACTED}"
        assert sub.__traceback__ is not None


def test_no_active_provider_error_does_not_leak_endpoint_keys(caplog):
    provider = FallbackProvider(DEAD_ENDPOINTS, exception_retry_configuration=None)
    _dead(provider)

    with caplog.at_level(logging.DEBUG), pytest.raises(NoActiveProviderError) as exc_info:
        provider.make_request("eth_blockNumber", [])

    _assert_redacted(exc_info.value, caplog)


@pytest.mark.asyncio
async def test_async_no_active_provider_error_does_not_leak_endpoint_keys(caplog):
    provider = AsyncFallbackProvider(DEAD_ENDPOINTS, exception_retry_configuration=None)
    _dead(provider)

    with caplog.at_level(logging.DEBUG), pytest.raises(NoActiveProviderError) as exc_info:
        await provider.make_request("eth_blockNumber", [])

    _assert_redacted(exc_info.value, caplog)


@pytest.mark.parametrize("provider_cls", [FallbackProvider, AsyncFallbackProvider])
def test_chain_id_mismatch_names_endpoints_by_index(provider_cls):
    provider = provider_cls(DEAD_ENDPOINTS, exception_retry_configuration=None)
    provider._providers[0]._chain_id = "1"
    provider._providers[1]._chain_id = "100"

    with pytest.raises(ChainIdMismatchError) as exc_info:
        provider._validate_chain_ids()

    message = str(exc_info.value)
    assert KEY not in message
    assert "Chain ID 1: endpoints #0" in message
    assert "Chain ID 100: endpoints #1" in message
