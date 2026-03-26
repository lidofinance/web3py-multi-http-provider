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
or with metrics:
```bash
$ poetry add web3-multi-provider[metrics]
```

## Usage

```py
from web3 import Web3
from web3_multi_provider import MultiProvider
from web3_multi_provider import FallbackProvider

w3 = Web3(MultiProvider([  # RPC endpoints list
    'http://127.0.0.1:8000/',
    'https://mainnet.infura.io/v3/...',
]))

# or

w3 = Web3(FallbackProvider([  # RPC endpoints list
    'http://127.0.0.1:8000/',
    'https://mainnet.infura.io/v3/...',
]))

last_block = w3.eth.get_block('latest')
```

### `MultiProvider`

This provider keeps track of the current endpoint and switches to the next one if an error occurs.
It fails if no endpoints are available.

### `FallbackProvider`

This provider sends requests to the all endpoints in the sequence until response received or endpoints list exhausted.

### `AsyncMultiProvider` and `AsyncFallbackProvider`

These providers are async versions of `MultiProvider` and `FallbackProvider` respectively. They may
be used with instances of `AsyncWeb3`.

```py
from web3 import AsyncWeb3
from web3_multi_provider import AsyncMultiProvider

w3 = AsyncWeb3(AsyncMultiProvider([  # RPC endpoints list
    'http://127.0.0.1:8000/',
    'https://mainnet.infura.io/v3/...',
]))
```

### Metrics

The library has built-in Prometheus metrics. They are disabled by default — install the extra and call `init_metrics()` before creating any provider.

```bash
pip install web3-multi-provider[metrics]
```

```py
from web3 import Web3
from web3_multi_provider import MultiProvider, init_metrics

init_metrics()  # must be called before creating a provider

w3 = Web3(MultiProvider([
    'http://127.0.0.1:8000/',
    'https://mainnet.infura.io/v3/...',
]))
```

`init_metrics()` registers the following metrics with the default Prometheus registry:

| Metric | Type | Description |
|---|---|---|
| `http_rpc_requests` | Counter | Total HTTP requests by network, provider, response code, result |
| `http_rpc_batch_size` | Histogram | Distribution of batch sizes |
| `http_rpc_response_seconds` | Histogram | RPC response time |
| `http_rpc_request_payload_bytes` | Histogram | Request payload size |
| `http_rpc_response_payload_bytes` | Histogram | Response payload size |
| `rpc_request` | Counter | RPC calls by method and result |

#### Custom configuration

Use `MetricsConfig` to set a namespace or override the chain ID → network name mapping:

```py
from web3_multi_provider.metrics import MetricsConfig

init_metrics(MetricsConfig(
    namespace="myapp",
    chain_id_to_name={
        1: "ethereum",
        137: "polygon",
        # add any custom chains here
    },
))
```

#### Custom registry

Pass a custom Prometheus registry if you don't want to use the global one:

```py
from prometheus_client import CollectorRegistry
from web3_multi_provider import init_metrics

registry = CollectorRegistry()
init_metrics(registry=registry)
```

## For developers

1. `poetry install` - to install deps
2. `pre-commit install` - to install pre-commit hooks

## Tests

```bash
poetry run pytest tests
```
