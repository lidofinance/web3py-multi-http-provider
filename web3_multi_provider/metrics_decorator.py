import functools
import inspect
from typing import List, Tuple, Any

import web3_multi_provider.metrics as metrics

from web3.types import RPCEndpoint


def record_rpc_call(metric_name: str = '_RPC_SERVICE_REQUESTS'):
    """
    Wrap RPC call methods (sync or async) to record status and error_code metrics dynamically.
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
    Wrap batch request methods (sync or async) to observe size of batch dynamically.
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
