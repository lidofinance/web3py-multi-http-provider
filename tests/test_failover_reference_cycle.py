import gc
import weakref
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from web3 import AsyncWeb3, Web3

from tests.mocked_requests import _AVAILABLE_ADDRESS, _MOCK_REQUEST_GET_RESULT, mock_response
from web3_multi_provider import AsyncFallbackProvider, AsyncMultiProvider, FallbackProvider, MultiProvider, NoActiveProviderError

FAILOVER_THEN_OK = ["http://127.0.0.1:9001", "http://127.0.0.1:9000"]
ALL_DOWN = ["http://127.0.0.1:9001", "http://127.0.0.1:9002"]


class _Heavy:
    """A large caller-owned object; weakref-able so the test can see whether it was freed."""


@pytest.fixture
def no_automatic_gc():
    # With automatic collection off, only reference counting can free objects, which is what a
    # long-running process gets for anything stuck in the oldest generation.
    gc.disable()
    yield
    gc.enable()


def _sync_post(endpoint_uri, *args, **kwargs):
    # Patched below the `responses` mock on purpose: it records every raised exception in its call
    # list, which would itself keep the caller's frames alive and mask the behavior under test.
    return mock_response(endpoint_uri)


async def _async_post(endpoint_uri, *args, **kwargs):
    # web3 calls raise_for_status() without awaiting it; an AsyncMock there would leave a
    # never-awaited coroutine whose warning, if turned into an error, keeps the frames alive.
    if _AVAILABLE_ADDRESS not in endpoint_uri:
        raise ConnectionError("Mocked connection error.")
    response = MagicMock()
    response.read = AsyncMock(return_value=_MOCK_REQUEST_GET_RESULT)
    return response


@pytest.mark.parametrize("provider_cls", [FallbackProvider, MultiProvider])
@pytest.mark.parametrize("endpoints", [FAILOVER_THEN_OK, ALL_DOWN], ids=["failover_then_ok", "all_down"])
@patch("web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id", return_value=1)
@patch("web3._utils.http_session_manager.HTTPSessionManager.get_response_from_post_request", side_effect=_sync_post)
def test_failover_does_not_pin_caller_locals(
    make_post_request, mock_fetch_chain_id, provider_cls, endpoints, no_automatic_gc, mock_metrics
):
    w3 = Web3(provider_cls(endpoints, exception_retry_configuration=None))

    def caller() -> tuple[weakref.ref, bool]:
        heavy = _Heavy()
        try:
            w3.eth.get_block("latest")
        except NoActiveProviderError as error:
            # The group still carries every provider's exception after the list is cleared.
            assert len(error.exceptions) == len(endpoints)
            return weakref.ref(heavy), False
        return weakref.ref(heavy), True

    ref, succeeded = caller()
    assert succeeded is (endpoints is FAILOVER_THEN_OK)
    assert ref() is None


@pytest.mark.parametrize("provider_cls", [AsyncFallbackProvider, AsyncMultiProvider])
@pytest.mark.parametrize("endpoints", [FAILOVER_THEN_OK, ALL_DOWN], ids=["failover_then_ok", "all_down"])
@patch("web3_multi_provider.async_http_provider_proxy.AsyncHTTPProviderProxy._fetch_chain_id", return_value=1)
@patch(
    "web3._utils.http_session_manager.HTTPSessionManager.async_get_response_from_post_request",
    side_effect=_async_post,
)
@pytest.mark.asyncio
async def test_async_failover_does_not_pin_caller_locals(
    make_post_request, mock_fetch_chain_id, provider_cls, endpoints, no_automatic_gc, mock_metrics
):
    w3 = AsyncWeb3(provider_cls(endpoints, exception_retry_configuration=None))

    async def caller() -> tuple[weakref.ref, bool]:
        heavy = _Heavy()
        try:
            await w3.eth.get_block("latest")
        except NoActiveProviderError as error:
            # The group still carries every provider's exception after the list is cleared.
            assert len(error.exceptions) == len(endpoints)
            return weakref.ref(heavy), False
        return weakref.ref(heavy), True

    ref, succeeded = await caller()
    assert succeeded is (endpoints is FAILOVER_THEN_OK)
    assert ref() is None
