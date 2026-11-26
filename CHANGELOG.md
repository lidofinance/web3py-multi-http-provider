# CHANGELOG

All notable changes to this project are documented in this file.

This changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

# [Unreleased]
### Added
- `MultiProvider` and `AsyncMultiProvider` accept `cooldown_seconds`, like the fallback providers.
- `cooldown_on`: a predicate that decides which errors start a cooldown. The default is the
  new public `is_endpoint_failure`.
- Metric `http_rpc_provider_cooldown_events`, labelled by `provider`, `index` (the endpoint's
  position in the configured list) and `event` (`entered`, `probe_failed`, `recovered`).

### Changed
- HTTP 400, 413, 414 and 422 no longer start a cooldown, and end one like a success: the
  endpoint answered. In 2.3.0 every error started a cooldown; pass
  `cooldown_on=lambda error: True` to keep that.
- `MultiProvider` rotates over the endpoints that are not on cooldown, and each request starts
  one endpoint further than the previous one. Before, the position moved once per endpoint
  tried, so with `[dead, ok]` every request tried the dead endpoint first. Without a cooldown,
  the endpoint after a dead one now also gets the dead one's share: with `[dead, b, c]`, `b`
  serves twice as many requests as `c`. Set `cooldown_seconds` to spread the load evenly.
- `get_providers()` advances the round-robin position and may start a cooldown probe when it is
  called. Calling it only to inspect the endpoints delays an endpoint's recovery by one window.
- With `MultiProvider`, an endpoint whose cooldown has ended is probed first, so a recovered
  endpoint is back in the rotation at once. `FallbackProvider` keeps the probe in its place.
- Endpoint URLs are no longer masked in the "Provider not responding." warning. URLs that
  contain API keys can appear in logs.

### Removed (protected API)
- Sync and async providers share a failover core in `failover.py`; subclasses choose the order
  with `_selector_class`. Removed: `_on_provider_failure` and `_on_provider_success` (added in
  2.3.0), `MultiProvider._current_provider_index`, `_provider_indexes`,
  `FallbackProvider._cooldown`. `_make_request_with_failover` takes only `method` and `params`.
  `ProviderCooldown.order` is now `reorder`, and `mark_failed` takes the error. The failover
  keeps the `_providers` list built in `__init__`: change its items, do not assign a new list.

Releases 2.0.0 to 2.3.0 are described in the GitHub releases, except 2.2.3, which has none.

# [1.0.0] - 2024-07-29
### Added
- Support for Python 3.11

### Fixed
- All logs are now debug level
- Endpoint addresses removed from logs

# [0.6.0] - 2023-03-29
### Added
- FallbackProvider.

# [0.5.0] - 2023-01-26
### Added
- Support to web3 v6.

### Fixed
- Check response is dict.


# [0.4.2] - 2022-07-28
### Fixed
- More threadsafe logging.
- Add check for extraData length (PoA chain check)

# [0.4.1] - 2022-07-21
### Changed
- Now `web3.provider.endpoint_uri` will contain current endpoint_uri used by provider.  
  (equivalent: `web3.provider._http_providers[web3.provider._current_provider_index].endpoint_uri`)

# [0.4.0] - 2022-07-02
### Added
- Support web sockets connection

### Deprecated
- MultiHTTPProvider deprecated use MultiProvider instead

## [0.3.0] - 2022-04-27
### Added
- Support PoA chain

## [0.2.0] - 2022-04-07
### Changed
- Library dependencies reduced. (downgrade web3 and python versions)
- Renamed NoActiveProvider to NoActiveProviderError
- Add NoActiveProviderError moved to base directory
- Reduce amount of logs

## [0.1.0] - 2022-04-01
### Added
- MultiHTTPProvider class.
