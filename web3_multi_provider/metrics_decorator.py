import functools
import inspect
from typing import Any, List, Tuple

from web3.types import RPCEndpoint

import web3_multi_provider.metrics as metrics


def record_rpc_call(metric_name: str = '_RPC_REQUEST'):
    """
    Decorator that wraps an RPC method (sync or async) to record Prometheus metrics for request outcomes.

    It tracks:
    - Request status (success/fail)
    - RPC error codes (if any)
    - Increments the given Prometheus counter metric with appropriate labels

    Args:
        metric_name (str): The name of the Prometheus metric attribute to call `labels(...).inc()` on.

    Returns:
        Callable: Wrapped method that records metrics and returns the RPC result.
    """


    def decorator(fn):
        # Async wrapper
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(self, method, params=None):
                status = 'fail'
                error_code = ''
                try:
                    result = await fn(self, method, params)
                    if isinstance(result, dict) and 'error' in result:
                        err = result['error']
                        if isinstance(err, dict):
                            error_code = err.get('code', '')
                    if 'error' not in result:
                        status = 'success'
                    return result
                finally:
                    metric = getattr(metrics, metric_name)
                    metric.labels(
                        self._network,
                        self._layer,
                        self._chain_id,
                        self._uri,
                        method,
                        status,
                        error_code
                    ).inc()

            return async_wrapper

        # Sync wrapper
        @functools.wraps(fn)
        def wrapper(self, method, params=None):
            status = 'fail'
            error_code = ''
            try:
                result = fn(self, method, params)
                if isinstance(result, dict) and 'error' in result:
                    err = result['error']
                    if isinstance(err, dict):
                        error_code = err.get('code', '')
                if 'error' not in result:
                    status = 'success'
                return result
            finally:
                metric = getattr(metrics, metric_name)
                metric.labels(
                    self._network,
                    self._layer,
                    self._chain_id,
                    self._uri,
                    method,
                    status,
                    error_code
                ).inc()

        return wrapper

    return decorator


def observe_output_payload(metric_name: str):
    """
    Decorator that observes the size (in bytes) of a request payload produced by the wrapped method.

    Typically used for methods that return an encoded byte string (e.g., JSON RPC requests).

    Args:
        metric_name (str): The Prometheus histogram or summary metric name to record the payload size with.

    Returns:
        Callable: Wrapped function that records the payload size in bytes.
    """

    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(self, *args, **kwargs):
                payload = await fn(self, *args, **kwargs)
                getattr(metrics, metric_name).labels(
                    self._network, self._layer, self._chain_id, self._uri
                ).observe(len(payload))
                return payload

            return async_wrapper

        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            payload = fn(self, *args, **kwargs)
            getattr(metrics, metric_name).labels(
                self._network, self._layer, self._chain_id, self._uri
            ).observe(len(payload))
            return payload

        return wrapper

    return decorator


def observe_input_payload(metric_name: str):
    """
    Decorator that records the size of an incoming byte response before decoding.

    Useful for measuring raw RPC response sizes.

    Args:
        metric_name (str): The Prometheus histogram or summary metric name to record the response size with.

    Returns:
        Callable: Wrapped function that records the size of the raw input payload.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(self, raw_response: bytes, *args, **kwargs):
            getattr(metrics, metric_name).labels(
                self._network, self._layer, self._chain_id, self._uri
            ).observe(len(raw_response))
            return fn(self, raw_response, *args, **kwargs)

        return wrapper

    return decorator


def observe_batch_size(metric_name: str = '_HTTP_RPC_BATCH_SIZE'):
    """
    Decorator that observes the number of requests in a batch RPC call (sync or async).

    Args:
        metric_name (str): The Prometheus metric name to use for recording the batch size.

    Returns:
        Callable: Wrapped batch function that records the number of items in the batch.
    """

    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(self, batch_requests: List[Tuple[RPCEndpoint, Any]]):
                try:
                    return await fn(self, batch_requests)
                finally:
                    metric = getattr(metrics, metric_name)
                    metric.labels(
                        self._network,
                        self._layer,
                        self._chain_id,
                        self._uri
                    ).observe(len(batch_requests))

            return async_wrapper

        @functools.wraps(fn)
        def wrapper(self, batch_requests: List[Tuple[RPCEndpoint, Any]]):
            try:
                return fn(self, batch_requests)
            finally:
                metric = getattr(metrics, metric_name)
                metric.labels(
                    self._network,
                    self._layer,
                    self._chain_id,
                    self._uri
                ).observe(len(batch_requests))

        return wrapper

    return decorator
