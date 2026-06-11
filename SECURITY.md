# Security Policy

NPA Agent is local-first software for non-performing asset analysis. The default design assumes asset packages, contracts, phone numbers, ID cards, addresses, and company recovery experience are sensitive.

## Sensitive Data

Sensitive fields include:

- Debtor names
- ID card numbers
- Phone numbers
- Detailed addresses
- Full asset package rows
- Contract originals and extracted text
- Company pricing rules, court experience, and recovery results
- API keys for model or voice providers

## Local-First Defaults

- Uploaded files are stored under `data/`.
- SQLite data is stored at `data/app.sqlite`.
- Generated reports, legal documents, knowledge notes, and private skill drafts are local runtime data.
- These runtime files are ignored by git by default.

Before sharing logs, screenshots, reports, or database files, confirm that they do not include sensitive data.

## Cloud Model Calls

The product defaults to redacted cloud mode when model providers are configured. Original sensitive content should not be sent to a cloud model unless the user explicitly chooses that mode and accepts the risk.

Audit records should describe provider, model, purpose, safety mode, and rough call metadata. They should not store full sensitive prompts.

## API Keys

API keys should be entered through the local UI or a local environment file. Do not commit real secrets. `.env.example` is only a template.

## Reporting Issues

If you find a security issue, open a private report with:

- A short description
- Reproduction steps
- Whether sensitive data could be exposed
- Suggested mitigation, if known

Do not attach real asset packages, contracts, debtor identifiers, or API keys.
