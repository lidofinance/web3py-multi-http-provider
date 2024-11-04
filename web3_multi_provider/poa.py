import logging

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
