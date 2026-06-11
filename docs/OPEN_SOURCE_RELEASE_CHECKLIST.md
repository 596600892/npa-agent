# Open Source Release Checklist

Use this checklist before publishing or tagging an open-source release.

## Required Checks

- Run `make test`.
- Start the app with `make dev PORT=8767`.
- Run `make smoke PORT=8767`.
- Open the workbench and confirm the top bar shows the current NPA Agent service address.
- Run `git status --short --ignored`.
- Confirm runtime data remains ignored:
  - `.venv/`
  - `data/app.sqlite`
  - `data/uploads/`
  - `data/reports/`
  - `data/legal_docs/`
  - `data/knowledge/`
  - `data/private_skills/`
  - `data/secrets/`

## File Review

- `LICENSE` exists and matches the intended license.
- `README.md` explains local and Docker startup.
- `.env.example` contains placeholders only.
- `SECURITY.md` explains sensitive data and local-first defaults.
- `CONTRIBUTING.md` explains tests and data safety.
- `docs/RELEASE_GAP_ANALYSIS.md` clearly marks Done, Partial, Placeholder, and Not Started items.
- `docs/ROADMAP.md` lists Alpha limits and later platform work.
- README does not describe reserved or partial capabilities as complete production features.

## Demo Review

- Use only files in `samples/` and `templates/`.
- Do not include real names, phone numbers, ID cards, addresses, contracts, or API keys in screenshots.
- Confirm `/api/health` returns `app_name=NPA Agent`.

## End-to-End Smoke

- Start with `make dev PORT=8767`.
- Open `http://127.0.0.1:8767`.
- Create a project.
- Upload `samples/level1_basic.xlsx`.
- Confirm field mapping.
- Generate the screening report.
- Generate the execution plan.
- Confirm the report and execution plan use masked sensitive fields.

## Release Notes

Mention that this is a local Alpha MVP for individual loan and consumer loan asset packages. Legal analysis is an auxiliary prompt, not legal advice. Pricing output is an analytical estimate, not investment advice.
