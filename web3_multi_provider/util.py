import logging
import re

from eth_typing import URI
from web3._utils.rpc_abi import RPC
from web3.exceptions import ExtraDataLengthError
from web3.middleware.proof_of_authority import extradata_to_poa_cleanup
from web3.middleware.validation import _check_extradata_length
from web3.types import RPCEndpoint, RPCResponse

logger = logging.getLogger(__name__)


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


def is_transient_error(error: Exception) -> bool:
    """
    Check if error is transient based on execution-apis specification.

    Transient conditions (worth retrying same provider):
    - JSON-RPC codes: -32000, -32001, -32603 (server/resource errors)
    - Known messages: syncing, block not found, header not found,
      state not available
    """
    code = getattr(error, 'code', None)

    # For Web3RPCError, the code is in rpc_response attribute
    if code is None and hasattr(error, 'rpc_response'):
        code = error.rpc_response

    if code is None and hasattr(error, 'args') and error.args:
        for arg in error.args:
            if isinstance(arg, dict) and 'code' in arg:
                code = arg['code']
                break

    msg = str(error).lower()

    # Check for transient JSON-RPC error codes
    transient_codes = [-32000, -32001, -32603]
    if code in transient_codes:
        # Additional check: ensure message indicates temporary condition
        transient_keywords = {
            "syncing",
            "block not found",
            "header not found",
            "state not available"
        }
        if any(keyword in msg for keyword in transient_keywords):
            return True

    return False


def format_provider_failures_message(exceptions: list[Exception], provider_name: str = "provider") -> str:
    """
    Format contextual error message for NoActiveProviderError based on exception types.

    Args:
        exceptions: List of exceptions from all provider attempts
        provider_name: Name of provider type for message (e.g. "provider", "fallbackprovider")

    Returns:
        Contextual error message describing the failure pattern
    """
    if not exceptions:
        return f"No {provider_name}s available"

    total = len(exceptions)
    transient_count = sum(1 for e in exceptions if is_transient_error(e))
    hard_count = total - transient_count

    if transient_count == total:
        return f"All {total} {provider_name}s in transient state (likely ePBS): syncing/block-unavailable"
    elif hard_count == total:
        return f"All {total} {provider_name}s failed: connection/timeout errors"
    else:
        return f"Mixed {provider_name} failures: {transient_count} transient, {hard_count} hard"
