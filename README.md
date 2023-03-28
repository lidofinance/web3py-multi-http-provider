# <img src="https://docs.lido.fi/img/logo.svg" alt="Lido" width="46"/> Web3 Multi Provider

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Provider that accepts multiple endpoints.

## Install

```bash
$ pip install web3-multi-provider
```
or
```bash
$ poetry add web3-multi-provider
```

## Usage

```py
from web3 import Web3
from web3_multi_provider import MultiProvider
from web3_multi_provider import FallbackProvider

w3 = Web3(MultiProvider([  # RPC endpoints list
    'http://127.0.0.1:8000/',
    'https://mainnet.infura.io/v3/...',
    'wss://mainnet.infura.io/ws/v3/...',
]))

# or

w3 = Web3(FallbackProvider([  # RPC endpoints list
    'http://127.0.0.1:8000/',
    'https://mainnet.infura.io/v3/...',
    'wss://mainnet.infura.io/ws/v3/...',
]))

last_block = w3.eth.get_block('latest')
```

### `MultiProvider`

This provider tracks currently used endpoint internally and switch to the next one on error or fails if no more
endpoints to switch to.

### `FallbackProvider`

This provider sends requests to the all endpoints in the sequence until response received or endpoints list exhausted.

## For developers

1. `poetry install` - to install deps
2. `pre-commit install` - to install pre-commit hooks

## Tests

```bash
poetry run pytest tests
```
