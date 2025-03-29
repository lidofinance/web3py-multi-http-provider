import pytest

from util import normalize_provider


@pytest.mark.parametrize("input_uri,expected", [
    ("http://127.0.0.1", "127.0.0.1"),
    ("127.0.0.1", "127.0.0.1"),
    ("http://127.0.0.1:8545", "127.0.0.1:8545"),
    ("127.0.0.1:8545", "127.0.0.1:8545"),
    ("https://eth-mainnet.alchemy.com/v2/key", "alchemy.com"),
    ("http://rpc.ankr.com/eth", "ankr.com"),
    ("https://my.provider.example.io/path", "example.io"),
    ("my.provider.infura.io", "infura.io"),
])
def test_normalize_provider_valid(input_uri, expected):
    assert normalize_provider(input_uri) == expected


def test_normalize_provider_invalid_hostname():
    with pytest.raises(ValueError, match="Unhandled hostname format"):
        normalize_provider("localhost")
