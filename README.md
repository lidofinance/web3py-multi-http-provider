# <img src="https://docs.lido.fi/img/logo.svg" alt="Lido" width="46"/> Web3 Multi Provider

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Provider that switch to other working web3 rpc endpoint if smth is bad with active one.

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
from web3_multi_provider import MultiHTTPProvider

w3 = Web3(MultiHTTPProvider([  # RPC endpoints list
    'https://mainnet.infura.io/v3/...',  # RPC endpoint 2
    'http://127.0.0.1:8000/',  # RPC endpoint 1
]))

last_block = w3.eth.get_block('latest')
```

## For developers

1. `poetry install` - to install deps
2. `pre-commit install` - to install pre-commit hooks

## Tests

```bash
poetry run pytest tests
```
