import asyncio
import json
import logging
import time
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
import requests
import responses
from web3 import Web3
from web3.types import RPCEndpoint

from tests.mocked_requests import _AVAILABLE_ADDRESS, _NOT_AVAILABLE_ADDRESS_1
from web3_multi_provider import (
    AsyncFallbackProvider,
    AsyncMultiProvider,
    FallbackProvider,
    MultiProvider,
    NoActiveProviderError,
    is_endpoint_failure,
)
from web3_multi_provider.cooldown import ProviderCooldown
from web3_multi_provider.failover import InOrderSelector, RoundRobinSelector
from web3_multi_provider.metrics import _DummyMetric

COOLDOWN = 60.0
OK = {"jsonrpc": "2.0", "id": 1, "result": "0x1"}
DOWN = ConnectionError("429 Too Many Requests")


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} error", response=response)


def _client_response_error(status: int) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(request_info=Mock(), history=(), status=status)


def _provider(provider_cls, *responses, cooldown: float = COOLDOWN, clock=None, **kwargs):
    """One endpoint per entry: an exception makes every call to it fail, anything else is returned."""
    provider = provider_cls([f"http://rpc-{i}.example" for i in range(len(responses))], cooldown_seconds=cooldown, **kwargs)
    mock = AsyncMock if provider_cls in (AsyncFallbackProvider, AsyncMultiProvider) else Mock
    for endpoint, response in zip(provider._providers, responses, strict=True):
        _answer(endpoint, response, mock)
    if clock is not None:
        provider._failover.cooldown._clock = clock
    return provider


def _answer(endpoint, response, mock=Mock) -> None:
    endpoint.make_request = mock(side_effect=response) if isinstance(response, Exception) else mock(return_value=response)


def _fallback(*responses, **kwargs) -> FallbackProvider:
    return _provider(FallbackProvider, *responses, **kwargs)


def _async_fallback(*responses, **kwargs) -> AsyncFallbackProvider:
    return _provider(AsyncFallbackProvider, *responses, **kwargs)


def _request(provider, params=()):
    return provider.make_request(RPCEndpoint("eth_blockNumber"), list(params))


async def _async_request(provider):
    return await provider.make_request(RPCEndpoint("eth_blockNumber"), [])


def _calls(provider) -> list[int]:
    return [endpoint.make_request.call_count for endpoint in provider._providers]


def _warnings(caplog, logger_suffix: str) -> list:
    return [r.msg for r in caplog.records if r.name.endswith(logger_suffix)]


class TestProviderCooldown:
    def test_disabled_by_default(self):
        provider = _fallback(DOWN, OK, cooldown=0)

        for _ in range(3):
            assert _request(provider) == OK

        assert _calls(provider) == [3, 3]

    @pytest.mark.parametrize("seconds", [-1, float("nan"), float("inf")])
    def test_invalid_cooldown_is_rejected(self, seconds):
        with pytest.raises(ValueError):
            FallbackProvider(["http://rpc-0.example"], cooldown_seconds=seconds)

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
        clock = FakeClock()
        provider = _fallback(DOWN, OK, clock=clock)

        _request(provider)
        _answer(provider._providers[0], OK)
        clock.now += COOLDOWN
        _request(provider)

        assert _calls(provider) == [1, 1]

    def test_cooling_endpoints_are_still_tried_last(self):
        provider = _fallback(DOWN, OK, OK)
        _request(provider)
        _answer(provider._providers[0], OK)
        _answer(provider._providers[1], DOWN)
        _answer(provider._providers[2], DOWN)

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

        assert [msg["index"] for msg in _warnings(caplog, ".cooldown")] == [0, 1]

    def test_reorder_moves_cooling_endpoints_to_the_end(self):
        cooldown = ProviderCooldown(COOLDOWN)

        cooldown.mark_failed(0, DOWN)
        cooldown.mark_failed(2, DOWN)

        assert cooldown.reorder([0, 1, 2, 3]) == [1, 3, 0, 2]
        assert cooldown.reorder([2, 3, 0, 1]) == [3, 1, 2, 0]

    def test_reorder_lists_each_endpoint_once_when_a_failure_lands_mid_scan(self):
        class FailsDuringScan(dict):
            """Another thread marks endpoint 0 failed right after the scan has read it."""

            def get(self, key, default=None):
                value = super().get(key, default)
                if key == 0:
                    self[0] = time.monotonic() + COOLDOWN
                return value

        cooldown = ProviderCooldown(COOLDOWN)
        cooldown._until = FailsDuringScan()

        assert cooldown.reorder([0, 1]) == [0, 1]

    def test_failure_log_names_the_endpoint_not_its_position(self, caplog):
        provider = _fallback(DOWN, OK)
        _request(provider)
        _answer(provider._providers[1], DOWN)

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="web3_multi_provider.multi_http_provider"):
            with pytest.raises(NoActiveProviderError):
                _request(provider)  # tries endpoint 1 first, then the cooling endpoint 0

        assert [msg["index"] for msg in _warnings(caplog, ".multi_http_provider")] == [1, 0]

    def test_only_one_request_probes_when_cooldown_ends(self):
        clock = FakeClock()
        cooldown = ProviderCooldown(COOLDOWN, clock=clock)
        cooldown.mark_failed(0, DOWN)
        clock.now += COOLDOWN

        assert cooldown.reorder([0, 1]) == [0, 1]  # this request probes endpoint 0
        assert cooldown.reorder([0, 1]) == [1, 0]  # concurrent requests keep it last

    def test_failed_probe_keeps_endpoint_last(self, caplog):
        clock = FakeClock()
        provider = _fallback(DOWN, OK, clock=clock)
        _request(provider)
        clock.now += COOLDOWN

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="web3_multi_provider.cooldown"):
            _request(provider)  # probe fails
            _request(provider)

        assert _calls(provider) == [2, 3]
        assert [msg["msg"] for msg in _warnings(caplog, ".cooldown")] == ["Provider still failing after cooldown."]

    def test_unreported_probe_is_retried_next_window(self):
        clock = FakeClock()
        cooldown = ProviderCooldown(COOLDOWN, clock=clock)
        cooldown.mark_failed(0, DOWN)
        clock.now += COOLDOWN
        cooldown.reorder([0, 1])  # probe claimed, request cancelled before it reports

        clock.now += 1
        assert cooldown.reorder([0, 1]) == [1, 0]
        clock.now += COOLDOWN
        assert cooldown.reorder([0, 1]) == [0, 1]

    def test_cooling_endpoint_that_answers_is_preferred_again(self):
        provider = _fallback(DOWN, OK)
        _request(provider)
        _answer(provider._providers[0], OK)
        _answer(provider._providers[1], DOWN)
        _request(provider)  # endpoint 1 fails, cooling endpoint 0 answers
        _answer(provider._providers[1], OK)

        _request(provider)

        assert _calls(provider) == [2, 0]


class TestErrorClassification:
    @pytest.mark.parametrize(
        "error",
        [
            ConnectionError("refused"),
            TimeoutError(),
            requests.ConnectionError("refused"),
            requests.ReadTimeout("slow"),
            requests.ConnectTimeout("slow"),
            _http_error(429),
            _http_error(500),
            _http_error(503),
            aiohttp.ServerDisconnectedError(),
            aiohttp.ServerTimeoutError(),
            _client_response_error(429),
            _client_response_error(502),
            json.JSONDecodeError("Expecting value", "<html>", 0),
            requests.JSONDecodeError("Expecting value", "<html>", 0),
        ],
        ids=repr,
    )
    def test_endpoint_failures(self, error):
        assert is_endpoint_failure(error)

    @pytest.mark.parametrize(
        "error",
        [
            _http_error(400),
            _http_error(404),
            _http_error(413),
            _client_response_error(400),
            _client_response_error(413),
            requests.HTTPError("no response attached"),
            KeyError("result"),
            ValueError("bad hex"),
            RuntimeError("bug"),
        ],
        ids=repr,
    )
    def test_request_failures(self, error):
        assert not is_endpoint_failure(error)

    def test_request_error_does_not_demote_healthy_primary(self):
        provider = _fallback(OK, OK)

        def primary(method, params):
            if params == ["huge-range"]:
                raise _http_error(413)
            return OK

        provider._providers[0].make_request = Mock(side_effect=primary)

        _request(provider, ["huge-range"])
        for _ in range(3):
            _request(provider)

        assert _calls(provider) == [4, 1]

    def test_custom_predicate_decides_what_starts_a_cooldown(self):
        provider = _fallback(_http_error(413), OK, cooldown_on=lambda error: True)

        for _ in range(3):
            _request(provider)

        assert _calls(provider) == [1, 3]

    def test_cooldown_can_ignore_errors_that_count_by_default(self):
        provider = _fallback(DOWN, OK, cooldown_on=lambda error: False)

        for _ in range(3):
            _request(provider)

        assert _calls(provider) == [3, 3]


class TestEndpointSelectors:
    def test_in_order_always_starts_from_the_first(self):
        selector = InOrderSelector(3)

        assert [selector.order() for _ in range(2)] == [[0, 1, 2], [0, 1, 2]]

    def test_round_robin_starts_each_request_one_further(self):
        selector = RoundRobinSelector(3)

        assert [selector.order() for _ in range(4)] == [[0, 1, 2], [1, 2, 0], [2, 0, 1], [0, 1, 2]]

    @pytest.mark.parametrize("selector_cls", [InOrderSelector, RoundRobinSelector])
    def test_no_endpoints(self, selector_cls):
        assert selector_cls(0).order() == []

    def test_multi_provider_spreads_requests(self):
        provider = _provider(MultiProvider, OK, OK, OK, cooldown=0)

        for _ in range(6):
            _request(provider)

        assert _calls(provider) == [2, 2, 2]

    def test_multi_provider_without_cooldown_reaches_dead_endpoint_every_other_request(self):
        provider = _provider(MultiProvider, DOWN, OK, cooldown=0)

        for _ in range(4):
            assert _request(provider) == OK

        assert _calls(provider) == [2, 4]

    def test_multi_provider_skips_cooling_endpoint(self):
        provider = _provider(MultiProvider, DOWN, OK, OK)

        for _ in range(6):
            assert _request(provider) == OK

        assert _calls(provider)[0] == 1
        assert sum(_calls(provider)[1:]) == 6


class TestCooldownMetrics:
    def test_transitions_are_counted(self, mock_metrics):
        clock = FakeClock()
        provider = _fallback(DOWN, OK, clock=clock)
        _request(provider)
        clock.now += COOLDOWN
        _request(provider)  # probe fails
        _answer(provider._providers[0], OK)
        clock.now += COOLDOWN
        _request(provider)  # probe answers

        assert mock_metrics.provider_cooldown_events.call_args_list == [
            (("rpc-0.example", "entered"),),
            (("rpc-0.example", "probe_failed"),),
            (("rpc-0.example", "recovered"),),
        ]
        assert mock_metrics.provider_cooldown_events.return_value.inc.call_count == 3

    def test_works_without_metrics(self):
        with patch("web3_multi_provider.metrics._PROVIDER_COOLDOWN_EVENTS", _DummyMetric()):
            provider = _fallback(DOWN, OK)
            for _ in range(2):
                assert _request(provider) == OK

        assert _calls(provider) == [1, 2]

    def test_broken_metric_does_not_fail_the_request(self, caplog):
        with patch("web3_multi_provider.metrics._PROVIDER_COOLDOWN_EVENTS.labels", side_effect=RuntimeError("boom")):
            provider = _fallback(DOWN, OK)
            assert _request(provider) == OK

        assert {"msg": "Failed to record cooldown metric.", "error": "boom"} in _warnings(caplog, ".cooldown")


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

    @pytest.mark.asyncio
    async def test_failure_log_names_the_endpoint_not_its_position(self, caplog):
        provider = _async_fallback(DOWN, OK)
        await _async_request(provider)
        _answer(provider._providers[1], DOWN, AsyncMock)

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="web3_multi_provider.async_multi_http_provider"):
            with pytest.raises(NoActiveProviderError):
                await _async_request(provider)

        assert [msg["index"] for msg in _warnings(caplog, ".async_multi_http_provider")] == [1, 0]

    @pytest.mark.asyncio
    async def test_concurrent_requests_send_one_probe_when_cooldown_ends(self):
        cooldown = 0.05

        async def slow_failure(*_):
            await asyncio.sleep(0.1)
            raise DOWN

        provider = _async_fallback(DOWN, OK, cooldown=cooldown)
        provider._providers[0].make_request = AsyncMock(side_effect=slow_failure)
        await _async_request(provider)
        await asyncio.sleep(cooldown * 1.5)

        results = await asyncio.gather(*(_async_request(provider) for _ in range(20)))

        assert results == [OK] * 20
        assert _calls(provider) == [2, 21]

    @pytest.mark.asyncio
    async def test_request_error_does_not_demote_healthy_primary(self):
        provider = _async_fallback(_client_response_error(413), OK)

        for _ in range(3):
            await _async_request(provider)

        assert _calls(provider) == [3, 3]

    @pytest.mark.asyncio
    async def test_multi_provider_skips_cooling_endpoint(self):
        provider = _provider(AsyncMultiProvider, DOWN, OK, OK)

        for _ in range(6):
            assert await _async_request(provider) == OK

        assert _calls(provider)[0] == 1
        assert sum(_calls(provider)[1:]) == 6


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


_FAILING_ADDRESS = "http://rpc-failing.example"


@pytest.mark.parametrize(
    "status, content_type, body, primary_calls",
    [
        (503, "text/plain", "Service Unavailable", 1),
        (429, "application/json", '{"error": {"code": 429, "message": "rate limited"}}', 1),
        (413, "application/json", '{"error": {"code": -32600, "message": "too large"}}', 2),
    ],
)
@patch("web3_multi_provider.multi_http_provider.HTTPProviderProxy._fetch_chain_id", return_value=1)
@responses.activate
def test_http_errors_are_classified_over_http(mock_fetch_chain_id, status, content_type, body, primary_calls, mock_metrics):
    responses.add(responses.POST, _FAILING_ADDRESS, body=body, status=status, content_type=content_type)
    provider = FallbackProvider(
        [_FAILING_ADDRESS, _AVAILABLE_ADDRESS],
        exception_retry_configuration=None,
        cooldown_seconds=COOLDOWN,
    )

    for _ in range(2):
        provider.make_request(RPCEndpoint("eth_blockNumber"), [])

    requested = [call.request.url.rstrip("/") for call in responses.calls]
    assert requested.count(_FAILING_ADDRESS) == primary_calls
