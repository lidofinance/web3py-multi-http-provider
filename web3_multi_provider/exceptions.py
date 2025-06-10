from mypy.checkexpr import Sequence


class NoActiveProviderError(ExceptionGroup):
    """Raised when no provider is able to handle the request."""

    @classmethod
    def from_exceptions(cls, message: str, exceptions: Sequence[BaseException]):
        if exceptions:
            return cls(message, exceptions)
        else:
            return RuntimeError(
                "No providers were called"
            )  # or a fallback custom Exception


class ProtocolNotSupported(Exception):
    """Supported protocols: http, https"""


class ProviderInitialization(Exception):
    """Error during provider init"""
