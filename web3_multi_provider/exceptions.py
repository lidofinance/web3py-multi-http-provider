class NoActiveProviderError(Exception):
    """Base exception if all providers are offline"""


class ProtocolNotSupported(Exception):
    """Supported protocols: http, https"""


