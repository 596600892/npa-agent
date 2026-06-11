# Contributing

Thanks for helping improve NPA Agent.

## Development Setup

```bash
make setup
make dev
```

If port `8765` is occupied:

```bash
make dev PORT=8767
make smoke PORT=8767
```

## Test Before Submitting

```bash
make test
```

The test suite uses the Python standard library `unittest` runner. Do not add new hard dependencies unless they are needed for the MVP and listed in `requirements.txt`.

## Data Safety

Do not commit runtime business data:

- `data/app.sqlite`
- uploaded asset packages
- generated reports
- legal document originals
- knowledge vault notes
- private skill draft contents
- API keys or `.env` files

Use sample files under `samples/` and templates under `templates/` for tests and demos.

## Code Style

- Keep changes local to the feature being implemented.
- Prefer existing modules and simple rules before adding frameworks.
- Preserve local-first behavior and sensitive-data redaction.
- Add or update tests for behavior changes.

## Pull Request Checklist

- `make test` passes.
- `/api/health` returns `app_name=NPA Agent`.
- README or docs are updated for user-visible changes.
- No real debtor, asset package, contract, API key, or company private data is staged.
