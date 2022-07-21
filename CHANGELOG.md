# CHANGELOG

All notable changes to this project are documented in this file.

This changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
