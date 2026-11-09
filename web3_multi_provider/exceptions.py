from typing import Sequence


class NoActiveProviderError(ExceptionGroup):
    """Raised when no provider is able to handle the request."""

    @classmethod
    def from_exceptions(
        cls, message: str, exceptions: Sequence[Exception]
    ) -> Exception:
        if exceptions:
            return cls(message, exceptions)
        else:
            return RuntimeError(
                "No providers were called"
            )  # or a fallback custom Exception


class ProtocolNotSupported(Exception):
    """Supported protocols: http, https"""


class ChainIdMismatchError(Exception):
    """Raised when providers in a multi-provider have different chain IDs."""


class ProviderRequestError(Exception):
    """A single endpoint's request failure, with the endpoint URL redacted.

    Stands in for the original exception inside NoActiveProviderError: HTTP client errors quote the
    endpoint URL (or its path, where providers put API keys), and callers log the whole group.
    The message keeps the original exception type. The traceback is preserved,
    the cause chain is not.
    """
