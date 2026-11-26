# <img src="https://raw.githubusercontent.com/lidofinance/web3py-multi-http-provider/main/docs/logo.svg" height="70px" align="center" alt="Lido Logo"/> Web3 Multi Provider

[![PyPI](https://img.shields.io/pypi/v/web3-multi-provider.svg)](https://pypi.org/project/web3-multi-provider/)
[![Python](https://img.shields.io/pypi/pyversions/web3-multi-provider.svg)](https://pypi.org/project/web3-multi-provider/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[web3.py](https://github.com/ethereum/web3.py) HTTP providers that accept a list of RPC endpoints and fail over
to the next one when an endpoint errors, so the application stays online while a node is down.

Requires Python 3.12+ and web3.py 7.

## Install

The package is on PyPI as [`web3-multi-provider`](https://pypi.org/project/web3-multi-provider/):

```bash
pip install web3-multi-provider
# or
poetry add web3-multi-provider
```

With Prometheus metrics:

```bash
pip install "web3-multi-provider[metrics]"
# or
poetry add "web3-multi-provider[metrics]"
```

Releases after 2.3.0 are published from GitHub Actions with [PEP 740](https://peps.python.org/pep-0740/)
attestations, see [Verify a release](#verify-a-release).

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

This provider spreads requests across the endpoints (round-robin): each request starts one endpoint
further than the previous one and fails over to the next endpoints in turn. It fails if no endpoints
are available.

### `FallbackProvider`

This provider sends requests to the endpoints in the configured order until one answers or the list
is exhausted.

### Endpoint cooldown

A failing endpoint is slow to fail over from: web3 retries it before the next endpoint is tried. All
providers accept `cooldown_seconds`: an endpoint that failed is then tried after the other endpoints
until its cooldown ends. It is still tried if the other endpoints fail. When the cooldown ends, one
request tries the endpoint in its usual place again; concurrent requests keep it last until that
request finishes. If it fails, a new cooldown starts. An endpoint that answers, including one tried
last, is back in its usual place at once. The default `0` disables the cooldown.

```py
w3 = Web3(FallbackProvider([
    'http://127.0.0.1:8000/',
    'https://mainnet.infura.io/v3/...',
], cooldown_seconds=60))
```

Errors that blame the request itself do not start a cooldown, so one bad request does not move a
healthy endpoint back for everyone. By default (`is_endpoint_failure`) these are HTTP 400, 413, 414
and 422, and `TypeError` or `ValueError` raised while the request is built (for example params that
cannot be encoded as JSON). Every other error starts a cooldown, including HTTP 401 and 403 from an
expired API key and responses that are not JSON. Pass `cooldown_on` to decide yourself, for example
to start a cooldown on any error:

```py
w3 = Web3(FallbackProvider(endpoints, cooldown_seconds=60, cooldown_on=lambda error: True))
```

A JSON-RPC error in an HTTP 200 response (for example, a rate limit reported as error `-32005`) is a
valid answer, so it never reaches `cooldown_on` and does not start a cooldown.

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

### Errors

- `NoActiveProviderError` (an `ExceptionGroup`) is raised when every endpoint failed; it holds the error of
  each endpoint.
- `ChainIdMismatchError` is raised when the endpoints report different chain IDs. Each endpoint fetches its
  chain ID with `eth_chainId` on its first request, not when the provider is created.
- `ProtocolNotSupported` is raised on creation for a non-HTTP endpoint.

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

| Metric                              | Type      | Description                                                                       |
|-------------------------------------|-----------|-----------------------------------------------------------------------------------|
| `http_rpc_requests`                 | Counter   | Total HTTP requests by network, provider, response code, result                   |
| `http_rpc_batch_size`               | Histogram | Distribution of batch sizes                                                       |
| `http_rpc_response_seconds`         | Histogram | RPC response time                                                                 |
| `http_rpc_request_payload_bytes`    | Histogram | Request payload size                                                              |
| `http_rpc_response_payload_bytes`   | Histogram | Response payload size                                                             |
| `rpc_request`                       | Counter   | RPC calls by method and result                                                    |
| `http_rpc_provider_cooldown_events` | Counter   | Endpoint cooldown transitions by provider: `entered`, `probe_failed`, `recovered` |

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

## Verify a release

The wheel and the sdist on PyPI carry attestations signed by Sigstore with the identity of the
`publish.yml` workflow of this repository. PyPI shows them on the
[files page](https://pypi.org/project/web3-multi-provider/#files) of a version. To verify a file:

```bash
pip install pypi-attestations
python -m pypi_attestations verify pypi \
  --repository https://github.com/lidofinance/web3py-multi-http-provider \
  pypi:web3_multi_provider-<version>-py3-none-any.whl
```

A local file (from `pip download --no-deps web3-multi-provider==<version>`) can be passed by its path instead.

## For developers

This project requires a specific Poetry version, pinned in `.poetry-version`. To install it:

```bash
pipx install "poetry==$(cat .poetry-version)"
```

### Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [Dev Container CLI](https://github.com/devcontainers/cli): `npm install -g @devcontainers/cli`
- VS Code: [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension
- JetBrains: [Dev Containers](https://plugins.jetbrains.com/plugin/21724-dev-containers) plugin

### Setup

```bash
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . bash
```

This installs all dependencies and pre-commit hooks automatically via `postCreateCommand`.

Alternatively, without Docker:

1. `poetry install` - to install deps
2. `pre-commit install` - to install pre-commit hooks

## Tests

```bash
poetry run pytest -m "not integration" tests
```

The integration tests call real RPC endpoints, set as a comma-separated list in
`WEB3_MULTI_PROVIDER_INTEGRATION_RPC_URLS`:

```bash
WEB3_MULTI_PROVIDER_INTEGRATION_RPC_URLS=https://...,https://... \
  poetry run pytest -m integration tests/test_integration_http_provider.py
```

## Release

1. Merge the changes to `main`. Every push to `main` publishes a `.dev` build to
   [TestPyPI](https://test.pypi.org/project/web3-multi-provider/).
2. Publish a GitHub release tagged `v<version>`, as `v2.3.1`. The `Publish` workflow sets the package
   version from the tag, builds, signs the distributions and uploads them with their attestations to PyPI
   through trusted publishing (environment `release`).
