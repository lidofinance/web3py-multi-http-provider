import pytest
from web3.exceptions import ContractLogicError, Web3RPCError

from web3_multi_provider.multi_http_provider import TransientErrorConfig
from web3_multi_provider.util import (
    format_provider_failures_message,
    is_transient_error,
)


class TestIsTransientError:

    def test_transient_error_codes_with_keywords(self):
        """Test that transient RPC codes with relevant keywords are detected."""
        transient_cases = [
            Web3RPCError("Node is syncing", -32000),
            Web3RPCError("Block not found", -32001),
            Web3RPCError("Header not found", -32603),
            Web3RPCError("State not available", -32000),
        ]

        for error in transient_cases:
            assert is_transient_error(error), f"Should detect {error} as transient"

    def test_transient_codes_without_keywords_not_detected(self):
        """Test that transient codes without relevant keywords are not detected."""
        non_transient_cases = [
            Web3RPCError("Invalid signature", -32000),
            Web3RPCError("Unauthorized request", -32001),
            Web3RPCError("Internal server error", -32603),
        ]

        for error in non_transient_cases:
            assert not is_transient_error(error), f"Should not detect {error} as transient"

    def test_hard_errors_not_detected(self):
        """Test that hard errors are not detected as transient."""
        hard_errors = [
            ConnectionError("Connection timeout"),
            ConnectionError("Connection refused"),
            Web3RPCError("Invalid method", -32601),
            Web3RPCError("Parse error", -32700),
            ContractLogicError("execution reverted"),
        ]

        for error in hard_errors:
            assert not is_transient_error(error), f"Should not detect {error} as transient"

    def test_no_code_no_keywords(self):
        """Test that errors without codes or keywords are not transient."""
        error = ValueError("Some random error")
        assert not is_transient_error(error)


class TestFormatProviderFailuresMessage:
    """Test error message formatting."""

    def test_no_exceptions(self):
        """Test message when no exceptions provided."""
        msg = format_provider_failures_message([], "provider")
        assert msg == "No providers available"

    def test_all_transient_errors(self):
        """Test message when all errors are transient."""
        exceptions = [
            Web3RPCError("Node is syncing", -32000),
            Web3RPCError("Block not found", -32001),
            Web3RPCError("State not available", -32000),
        ]

        msg = format_provider_failures_message(exceptions, "provider")
        assert msg == "All 3 providers in transient state (likely ePBS): syncing/block-unavailable"

    def test_all_hard_errors(self):
        """Test message when all errors are hard failures."""
        exceptions = [
            ConnectionError("Connection timeout"),
            ConnectionError("Connection refused"),
            Web3RPCError("Invalid method", -32601),
        ]

        msg = format_provider_failures_message(exceptions, "provider")
        assert msg == "All 3 providers failed: connection/timeout errors"

    def test_mixed_errors(self):
        """Test message when errors are mixed."""
        exceptions = [
            Web3RPCError("Node is syncing", -32000),  # transient
            ConnectionError("Connection timeout"),     # hard
            Web3RPCError("Block not found", -32001),  # transient
            ConnectionError("Connection refused"),     # hard
        ]

        msg = format_provider_failures_message(exceptions, "provider")
        assert msg == "Mixed provider failures: 2 transient, 2 hard"

    def test_custom_provider_name(self):
        """Test message with custom provider name."""
        exceptions = [Web3RPCError("Node is syncing", -32000)]

        msg = format_provider_failures_message(exceptions, "fallbackprovider")
        assert msg == "All 1 fallbackproviders in transient state (likely ePBS): syncing/block-unavailable"