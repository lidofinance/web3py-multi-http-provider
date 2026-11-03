import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
import responses
from web3 import Web3
from web3.types import RPCEndpoint

from tests.mocked_requests import _AVAILABLE_ADDRESS, _NOT_AVAILABLE_ADDRESS_1
from web3_multi_provider import AsyncFallbackProvider, FallbackProvider, NoActiveProviderError
from web3_multi_provider.cooldown import ProviderCooldown

COOLDOWN = 60.0
OK = {"jsonrpc": "2.0", "id": 1, "result": "0x1"}
DOWN = ConnectionError("429 Too Many Requests")


def _fallback(*responses, cooldown: float = COOLDOWN) -> FallbackProvider:
    """One endpoint per entry: an exception makes every call to it fail, anything else is returned."""
    provider = FallbackProvider([f"http://rpc-{i}.example" for i in range(len(responses))], cooldown_seconds=cooldown)
    for endpoint, response in zip(provider._providers, responses, strict=True):
        endpoint.make_request = Mock(side_effect=response) if isinstance(response, Exception) else Mock(return_value=response)
    return provider


def _async_fallback(*responses, cooldown: float = COOLDOWN) -> AsyncFallbackProvider:
    provider = AsyncFallbackProvider([f"http://rpc-{i}.example" for i in range(len(responses))], cooldown_seconds=cooldown)
    for endpoint, response in zip(provider._providers, responses, strict=True):
        endpoint.make_request = AsyncMock(side_effect=response) if isinstance(response, Exception) else AsyncMock(return_value=response)
    return provider


def _request(provider: FallbackProvider):
    return provider.make_request(RPCEndpoint("eth_blockNumber"), [])


async def _async_request(provider: AsyncFallbackProvider):
    return await provider.make_request(RPCEndpoint("eth_blockNumber"), [])


def _calls(provider) -> list[int]:
    return [endpoint.make_request.call_count for endpoint in provider._providers]


class TestProviderCooldown:
    def test_disabled_by_default(self):
        provider = _fallback(DOWN, OK, cooldown=0)

        for _ in range(3):
            assert _request(provider) == OK

        assert _calls(provider) == [3, 3]

    def test_negative_cooldown_is_rejected(self):
        with pytest.raises(ValueError):
            FallbackProvider(["http://rpc-0.example"], cooldown_seconds=-1)

    def test_healthy_primary_serves_every_request(self):
        provider = _fallback(OK, OK)

        _request(provider)
        _request(provider)

        assert _calls(provider) == [2, 0]

    def test_failed_primary_is_skipped_while_cooling(self):
        provider = _fallback(DOWN, OK)

        for _ in range(3):
            assert _request(provider) == OK

        assert _calls(provider) == [1, 3]

    def test_primary_is_preferred_again_after_cooldown(self):
        provider = _fallback(DOWN, OK)

        with patch("web3_multi_provider.cooldown.time.monotonic", return_value=1000.0):
            _request(provider)
        provider._providers[0].make_request = Mock(return_value=OK)
        with patch("web3_multi_provider.cooldown.time.monotonic", return_value=1000.0 + COOLDOWN):
            _request(provider)

        assert _calls(provider) == [1, 1]

    def test_cooling_endpoints_are_still_tried_last(self):
        provider = _fallback(DOWN, OK, OK)
        _request(provider)
        provider._providers[0].make_request = Mock(return_value=OK)
        provider._providers[1].make_request = Mock(side_effect=DOWN)
        provider._providers[2].make_request = Mock(side_effect=DOWN)

        assert _request(provider) == OK
        assert _calls(provider) == [1, 1, 1]

    def test_all_endpoints_failing_still_raises(self):
        provider = _fallback(DOWN, DOWN)

        for _ in range(2):
            with pytest.raises(NoActiveProviderError):
                _request(provider)

        assert _calls(provider) == [2, 2]

    def test_cooldown_is_logged_once_per_window(self, caplog):
        provider = _fallback(DOWN, DOWN)

        with caplog.at_level(logging.WARNING, logger="web3_multi_provider.cooldown"):
            for _ in range(2):
                with pytest.raises(NoActiveProviderError):
                    _request(provider)

        assert [r.msg["index"] for r in caplog.records if r.name == "web3_multi_provider.cooldown"] == [0, 1]

    def test_order_moves_cooling_endpoints_to_the_end(self):
        cooldown = ProviderCooldown(COOLDOWN)

        cooldown.mark_failed(0)
        cooldown.mark_failed(2)

        assert cooldown.order(4) == [1, 3, 0, 2]


class TestAsyncProviderCooldown:
    @pytest.mark.asyncio
    async def test_failed_primary_is_skipped_while_cooling(self):
        provider = _async_fallback(DOWN, OK)

        for _ in range(3):
            assert await _async_request(provider) == OK

        assert _calls(provider) == [1, 3]

    @pytest.mark.asyncio
    async def test_disabled_by_default(self):
        provider = _async_fallback(DOWN, OK, cooldown=0)

        for _ in range(3):
            assert await _async_request(provider) == OK

        assert _calls(provider) == [3, 3]

    @pytest.mark.asyncio
    async def test_all_endpoints_failing_still_raises(self):
        provider = _async_fallback(DOWN, DOWN)

        for _ in range(2):
            with pytest.raises(NoActiveProviderError):
                await _async_request(provider)

        assert _calls(provider) == [2, 2]


@patch("web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id", return_value=1)
@responses.activate
def test_web3_skips_failed_endpoint_over_http(mock_fetch_chain_id, mock_metrics):
    w3 = Web3(
        FallbackProvider(
            [_NOT_AVAILABLE_ADDRESS_1, _AVAILABLE_ADDRESS],
            exception_retry_configuration=None,
            cooldown_seconds=COOLDOWN,
        )
    )

    w3.eth.get_block("latest")
    w3.eth.get_block("latest")

    requested = [call.request.url.rstrip("/") for call in responses.calls]
    assert requested.count(_NOT_AVAILABLE_ADDRESS_1) == 1
    assert requested.count(_AVAILABLE_ADDRESS) == 2
