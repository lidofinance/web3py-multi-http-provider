import logging
from unittest import TestCase
from unittest.mock import Mock, patch

import pytest
from web3 import Web3

from web3_multi_provider import MultiProvider
from web3_multi_provider.multi_http_provider import (
    FallbackProvider,
    NoActiveProviderError,
    ProtocolNotSupported,
)


def mocked_requests_get(
    endpoint_uri,
    data,
    *args,
    **kwargs,
):
    if "http://127.0.0.1:9000" in endpoint_uri:
        return b'{"jsonrpc": "2.0", "id": 0, "result": {"baseFeePerGas": "0x1816eeb4af", "difficulty": "0x27aca623255aa9", "extraData": "0x486976656f6e2065752d68656176792d32", "gasLimit": "0x1c9c364", "gasUsed": "0x8454f8", "hash": "0x2420cd3a3f572ba42a881457c88c5c3f58cf44a46e7f25aea53d3a7313922694", "logsBloom": "0x5260400700da108048d93200854128614100802800081404698960db80801ec8464604e3940845a34200c3c2800a4971922881803c01a13902474008842a2518012005042016030f1a80920a703402e209a160240845ce0128a451c282e040c0be0401180a3a0608a355581942010aa06441180242406622780550b4460a02004c11890083047425054a21690dcc044450012c7389089a0a0c20674c419008840b790700804034120a000fc08c2394019087886200038c440c8124b090850d11404120a2818840537b410143518037f000006a0b063a2438148c25020023e606b81825ad000202011506060096a080810459c904a1000062108b191212013223", "miner": "0x1ad91ee08f21be3de0ba2ba6918e714da6b45836", "mixHash": "0x4889052c97da7a2386244f85d8061a0765e1c0f98a212c2eda929dc406713dbe", "nonce": "0xf078269bfcafc704", "number": "0xd1271e", "parentHash": "0x857a1b6ee3a8f2b837f9ae69f5a0b1b181903f5e23df0ed9d166776333e14ec8", "receiptsRoot": "0x1760ed19deceff14ce9cdfebd18ff257c3afc22359edb144d663cd6eb6523aba", "sha3Uncles": "0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347", "size": "0xa1cc", "stateRoot": "0xa9d6469a301598d5de4f43f121c020da2814875c9154fffb72fb7a6edb8a88cd", "timestamp": "0x61a4733a", "totalDifficulty": "0x78150c58dfe2dc7fcb1", "transactions": [], "transactionsRoot": "0x46fdbd1a3ea670807040dd45f91ebe007c9521395d219150c2d8ac8b77055722", "uncles": []}}'

    raise ConnectionError("Mocked connection error.")


def mocked_request_poa(
    endpoint_uri,
    data,
    *args,
    **kwargs,
):
    return b'{"jsonrpc": "2.0", "id": 0, "result": {"baseFeePerGas": "0x1816eeb4af", "difficulty": "0x27aca623255aa9", "extraData": "0x00000000000000000000000051396620476f65726c6920417574686f72697479a8766f851c7ae7b3be68b8766225f28c8a0daf86bcdcdc7cb6a2cadec54bd393506e7d2088192110067a6d6280b13a2430d6b44dd2dbbe93d190ddce4309b83500", "gasLimit": "0x1c9c364", "gasUsed": "0x8454f8", "hash": "0x2420cd3a3f572ba42a881457c88c5c3f58cf44a46e7f25aea53d3a7313922694", "logsBloom": "0x5260400700da108048d93200854128614100802800081404698960db80801ec8464604e3940845a34200c3c2800a4971922881803c01a13902474008842a2518012005042016030f1a80920a703402e209a160240845ce0128a451c282e040c0be0401180a3a0608a355581942010aa06441180242406622780550b4460a02004c11890083047425054a21690dcc044450012c7389089a0a0c20674c419008840b790700804034120a000fc08c2394019087886200038c440c8124b090850d11404120a2818840537b410143518037f000006a0b063a2438148c25020023e606b81825ad000202011506060096a080810459c904a1000062108b191212013223", "miner": "0x1ad91ee08f21be3de0ba2ba6918e714da6b45836", "mixHash": "0x4889052c97da7a2386244f85d8061a0765e1c0f98a212c2eda929dc406713dbe", "nonce": "0xf078269bfcafc704", "number": "0xd1271e", "parentHash": "0x857a1b6ee3a8f2b837f9ae69f5a0b1b181903f5e23df0ed9d166776333e14ec8", "receiptsRoot": "0x1760ed19deceff14ce9cdfebd18ff257c3afc22359edb144d663cd6eb6523aba", "sha3Uncles": "0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347", "size": "0xa1cc", "stateRoot": "0xa9d6469a301598d5de4f43f121c020da2814875c9154fffb72fb7a6edb8a88cd", "timestamp": "0x61a4733a", "totalDifficulty": "0x78150c58dfe2dc7fcb1", "transactions": [], "transactionsRoot": "0x46fdbd1a3ea670807040dd45f91ebe007c9521395d219150c2d8ac8b77055722", "uncles": []}}'


class HttpProviderTestCase(TestCase):
    @pytest.fixture(autouse=True)
    def __inject_fixtures(self, caplog):
        self._caplog = caplog

    @patch("web3.providers.rpc.make_post_request", side_effect=mocked_requests_get)
    def test_one_provider_works(self, make_post_request):
        self.one_provider_works(MultiProvider)

    @patch("web3.providers.rpc.make_post_request", side_effect=mocked_requests_get)
    def test_nothing_works(self, make_post_request):
        self._caplog.set_level(logging.WARNING)

        provider = MultiProvider(
            [
                "http://127.0.0.1:9001",
                "http://127.0.0.1:9002",
            ]
        )

        w3 = Web3(provider)

        with self._caplog.at_level(logging.DEBUG):
            with self.assertRaises(NoActiveProviderError):
                w3.eth.get_block("latest")

        # Make sure there is no inf recursion
        self.assertEqual(len(self._caplog.records), 6)

    def one_provider_works(self, provider_class):
        provider = provider_class(
            [
                "http://127.0.0.1:9001",
                "http://127.0.0.1:9000",
            ]
        )

        w3 = Web3(provider)

        with self._caplog.at_level(logging.DEBUG):
            w3.eth.get_block("latest")
            w3.eth.get_block("latest")

        self.assertDictEqual(
            {
                "msg": "Provider not responding.",
                "error": "Mocked connection error.",
            },
            self._caplog.records[2].msg,
        )
        self.assertDictEqual(
            {
                "msg": "Send request using MultiProvider.",
                "method": "eth_getBlockByNumber",
                "params": "('latest', False)",
            },
            self._caplog.records[5].msg,
        )
        # Make sure second request will be directory to second provider and will ignore second one
        self.assertDictEqual(
            {
                "msg": "Send request using MultiProvider.",
                "method": "eth_getBlockByNumber",
                "params": "('latest', False)",
            },
            self._caplog.records[9].msg,
        )

    def test_protocols_support(self):
        MultiProvider(["http://127.0.0.1:9001"])
        MultiProvider(["https://127.0.0.1:9001"])
        MultiProvider(["ws://127.0.0.1:9001"])
        MultiProvider(["wss://127.0.0.1:9001"])

        with self.assertRaises(ProtocolNotSupported):
            MultiProvider(["ipc://127.0.0.1:9001"])

    @patch("web3.providers.rpc.make_post_request", side_effect=mocked_request_poa)
    def test_poa_blockchain(self, make_post_request):
        provider = MultiProvider(["http://127.0.0.1:9000"])

        w3 = Web3(provider)

        with self._caplog.at_level(logging.DEBUG):
            block = w3.eth.get_block("latest")

        self.assertIn(
            {"msg": "PoA blockchain cleanup response."},
            [log.msg for log in self._caplog.records],
        )

        self.assertIsNotNone(block.get("proofOfAuthorityData", None))

    @patch("web3.providers.rpc.make_post_request", side_effect=mocked_requests_get)
    def test_pos_blockchain(self, make_post_request):
        provider = MultiProvider(["http://127.0.0.1:9000"])

        w3 = Web3(provider)

        with self._caplog.at_level(logging.DEBUG):
            block = w3.eth.get_block("latest")

        self.assertIsNone(block.get("proofOfAuthorityData", None))

        self.assertNotIn(
            {"msg": "PoA blockchain cleanup response."},
            [log.msg for log in self._caplog.records],
        )


class TestFallbackProvider:
    def test_no_endpoints(self):
        w3 = Web3(FallbackProvider([]))

        with pytest.raises(NoActiveProviderError):
            w3.eth.get_block("latest")

    @patch("web3.providers.rpc.make_post_request", side_effect=mocked_requests_get)
    def test_one_endpoint(self, make_post_request: Mock):
        w3 = Web3(
            FallbackProvider(
                [
                    "http://127.0.0.1:9000",
                ]
            )
        )
        w3.eth.get_block("latest")
        make_post_request.assert_called_once()

    @patch("web3.providers.rpc.make_post_request", side_effect=mocked_requests_get)
    def test_first_working(self, make_post_request: Mock):
        w3 = Web3(
            FallbackProvider(
                [
                    "http://127.0.0.1:9000",
                    "http://127.0.0.1:9001",
                ]
            )
        )
        w3.eth.get_block("latest")
        make_post_request.assert_called_once()
        assert make_post_request.call_args.args[0] == "http://127.0.0.1:9000"

    @patch("web3.providers.rpc.make_post_request", side_effect=mocked_requests_get)
    def test_all_endpoints_fail(self, make_post_request: Mock):
        w3 = Web3(
            FallbackProvider(
                [
                    "http://127.0.0.1:9001",
                    "http://127.0.0.1:9002",
                    "http://127.0.0.1:9003",
                ]
            )
        )

        with pytest.raises(NoActiveProviderError):
            w3.eth.get_block("latest")

        assert make_post_request.call_count == 3
        assert make_post_request.call_args.args[0] == "http://127.0.0.1:9003"

    @patch("web3.providers.rpc.make_post_request", side_effect=mocked_requests_get)
    def test_one_endpoint_works(self, make_post_request: Mock):
        w3 = Web3(
            FallbackProvider(
                [
                    "http://127.0.0.1:9001",
                    "http://127.0.0.1:9000",
                ]
            )
        )

        w3.eth.get_block("latest")
        assert make_post_request.call_count == 2
        assert make_post_request.call_args.args[0] == "http://127.0.0.1:9000"

    @patch("web3.providers.rpc.make_post_request", side_effect=mocked_requests_get)
    def test_starts_from_the_first(self, make_post_request: Mock):
        w3 = Web3(
            FallbackProvider(
                [
                    "http://127.0.0.1:9001",
                    "http://127.0.0.1:9000",
                ]
            )
        )

        w3.eth.get_block("latest")
        w3.eth.get_block("latest")

        assert make_post_request.call_count == 4
        assert make_post_request.call_args_list[-2].args[0] == "http://127.0.0.1:9001"
