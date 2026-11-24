from typing import Sequence


class NoActiveProviderError(ExceptionGroup):
    """Raised when no provider is able to handle the request."""

    @classmethod
    def from_exceptions(
        cls, message: str, exceptions: Sequence[Exception]
    ) -> Exception:
        """Build the error to raise when every provider failed.

        Returns a RuntimeError instead when no provider was called at all,
        because an ExceptionGroup cannot be empty.
        """
        if exceptions:
            return cls(message, exceptions)
        return RuntimeError("No providers were called")


class ProtocolNotSupported(Exception):
    """Supported protocols: http, https"""


class ChainIdMismatchError(Exception):
    """Raised when providers in a multi-provider have different chain IDs."""
