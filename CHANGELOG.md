# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-11-10

### Added

- Redis Streams transport: `mbtk.transport` contracts and
  `RedisStreamQueue` with deduplication, acknowledgements, and failure
  counters.
- Framework-agnostic webhook validation and a FastAPI adapter
  (`mbtk[fastapi]`).
- `mbtk.retry` error classification and `LoggingMiddleware`.
- `ErrorMiddleware`, `ErrorPolicy`, and `DefaultErrorPolicy`.
- Async cache primitives: `MemoryCache`, `NullCache`, and `RedisCache`.
- Generic worker: `Processor`, `process_once`, `termination_signals`, and
  `run_poll_loop`.

## [0.1.1] - 2026-11-10

### Added

- `mbtk.__version__` for runtime version introspection.

## [0.1.0] - 2026-11-10

### Added

- Core dispatcher, routers, observers, composable filters, middleware, and
  dependency injection by argument name.
- Typed MAX events: messages, callback presses, and bot-started events.
- FSM: states, state groups, dialogue context, in-memory storage, and the
  `FSMStorage` protocol.
- MAX update parsing, including double-encoded callback payloads.
- Optional `MaxApiClient` for the MAX Bot API (`mbtk[max]`).
- Optional `RedisFSMStorage` with atomic one-shot claims (`mbtk[redis]`).
- MAX keyboard and attachment builders.

[Unreleased]: https://github.com/VladimirKrokhin/mbtk/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/VladimirKrokhin/mbtk/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/VladimirKrokhin/mbtk/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/VladimirKrokhin/mbtk/releases/tag/v0.1.0
