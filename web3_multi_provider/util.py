import logging
import re
from urllib.parse import urlsplit

from eth_typing import URI
from web3._utils.rpc_abi import RPC
from web3.exceptions import ExtraDataLengthError
from web3.middleware.proof_of_authority import extradata_to_poa_cleanup
from web3.middleware.validation import _check_extradata_length
from web3.types import RPCEndpoint, RPCResponse

from web3_multi_provider.exceptions import ProviderRequestError

logger = logging.getLogger(__name__)

REDACTED = "****"


def sanitize_poa_response(method: RPCEndpoint, response: RPCResponse) -> None:
    """Modify the response to remove PoA specific data."""
    if method in (RPC.eth_getBlockByHash, RPC.eth_getBlockByNumber):
        if (
            "result" in response
            and isinstance(response["result"], dict)
            and "extraData" in response["result"]
            and "proofOfAuthorityData" not in response["result"]
        ):
            try:
                _check_extradata_length(response["result"]["extraData"])
            except ExtraDataLengthError:
                logger.debug({"msg": "PoA blockchain cleanup response."})
                response["result"] = extradata_to_poa_cleanup(response["result"])


def normalize_provider(uri: URI | str) -> str:
    """
    If uri is an IP address returns as is.
    If uri is a dns address returns two highest domains.
    """
    stripped = re.sub(r"^https?://", "", uri.strip().lower())
    host = stripped.split("/")[0]

    if re.match(r"^((\d{1,3}\.){3}\d{1,3}|localhost)(:\d+)?$", host):
        return host

    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])

    raise ValueError(
        (
            f"Unhandled hostname format: {uri!r}. "
            "Hostname must be either an IP address or a valid provider address."
        )
    )


def redact_endpoint(text: str, endpoint_uri: URI | str | None) -> str:
    """Replace every part of the endpoint URL that can carry a credential.

    Providers put API keys in the URL path or query, and urllib3 errors quote only that part
    ("Max retries exceeded with url: /v2/<key>"), so replacing the full URL alone is not enough.
    """
    if not endpoint_uri:
        return text
    uri = str(endpoint_uri)
    parts = urlsplit(uri)
    fragments = {uri, parts.path + (f"?{parts.query}" if parts.query else "")}
    if parts.password:
        fragments.add(parts.password)
    # A bare "/" path is no secret and would mangle the rest of the message.
    for fragment in sorted(fragments - {"", "/"}, key=len, reverse=True):
        text = text.replace(fragment, REDACTED)
    return text


def redacted_error(
    error: Exception, endpoint_uri: URI | str | None
) -> ProviderRequestError:
    """Copy a provider failure without the endpoint URL, for NoActiveProviderError."""
    redacted = ProviderRequestError(
        f"{type(error).__name__}: {redact_endpoint(str(error), endpoint_uri)}"
    )
    # The cause chain repeats the URL (requests -> urllib3 errors), so it is dropped, not copied.
    redacted.__suppress_context__ = True
    return redacted.with_traceback(error.__traceback__)
