# Contributing

Issues and pull requests are welcome.

## Local setup

```sh
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The `httpx` dependency is enough to run the client tests; the Redis tests use
an in-memory fake and do not need a running Redis server.

## Guidelines

- Keep the core free of runtime dependencies. Anything that needs a library
  belongs in an extra.
- Add a test for every behavior change.
- Keep public names and docstrings in English.
- Use Conventional Commits, for example `feat: add TextRegexp filter`.
- Update `CHANGELOG.md` under `[Unreleased]` for user-visible changes.

## Pull requests

1. Fork the repository and create a branch.
2. Make the change and run the checks above.
3. Open a pull request with a short description and the motivation.
4. Wait for CI to pass.

## Release

Releases are cut from `main`:

1. Bump `version` in `pyproject.toml`.
2. Move the `[Unreleased]` section in `CHANGELOG.md` to the new version.
3. Commit, tag `vX.Y.Z`, and push the tag.
4. The `Release` workflow builds the package and publishes it to PyPI via
   Trusted Publishing.
