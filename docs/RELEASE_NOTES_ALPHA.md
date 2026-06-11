# NPA Agent v0.1.0-alpha.1 Release Notes

> Release type: local Alpha baseline
> Date: 2026-06-11
> Commit message: `chore: establish npa agent alpha baseline`

## Positioning

NPA Agent v0.1.0-alpha.1 is a local-first Alpha MVP for individual loan and consumer loan non-performing asset package analysis. It is designed for AMC teams, NPA investors, law firms, and phone mediation or collection support teams that need a local workbench for early screening, report generation, execution planning, and experience capture.

The core Alpha flow is:

```text
Upload asset package Excel -> confirm fields -> generate screening report -> generate execution plan -> optionally sync knowledge and draft private skills
```

## Supported In This Alpha

- Individual loan and consumer loan asset package `.xlsx` upload.
- Automatic field mapping and manual field confirmation.
- Required principal validation; debtor name can be replaced by an internal id.
- ID card parsing for age, gender, and basic region signals.
- Data completeness, amount distribution, contactability, debtor profile, and disposal mode analysis.
- Three-scenario pricing estimate with conservative, baseline, and optimistic ranges.
- Markdown screening report with source attribution and risk disclaimers.
- Local project records, uploaded file records, field mappings, reports, skill calls, and basic audit logs.
- Contract or clause document upload for PDF, DOCX, and TXT files, with basic text-based risk analysis.
- Company historical disposal data import, court profile aggregation, and pricing calibration.
- Yindeng public URL or notice text parsing, without login or crawler bypass.
- DeepSeek, Qwen/Bailian, and custom OpenAI-compatible model gateway entry points.
- Browser speech fallback and OpenAI-compatible enhanced TTS entry point.
- Lightweight execution workbench for batches, task priorities, compliant scripts, follow-up events, and redacted Excel export.
- Local Markdown knowledge base and searchable note index.
- Private skill draft generation and manual review, without automatic activation.
- MIT license, Docker support, Makefile commands, security notes, contribution guide, demo walkthrough, release checklist, gap analysis, and roadmap.

## Explicit Limits

This Alpha is not a production SaaS platform and does not claim complete legal, investment, data-source, or CRM coverage.

- No scanned PDF OCR. PDF support is limited to extractable text.
- No dedicated judgment, enforcement document, mediation record, or court filing parser.
- No AgentMemory MCP integration.
- No full BaiLongma-style real-time ASR, streaming speech conversation, or playback interruption.
- No Yindeng full-site monitoring, login handling, CAPTCHA bypass, or automated scraping.
- No external court, judicial, property, business registry, or commercial data provider integration.
- No GitHub or community skill installation and execution.
- No approved private skill execution in the analysis chain; private skills are draft and review only.
- No multi-role permissions, team workspace, production authentication, or SaaS tenant isolation.
- No full collection CRM, real outbound calling, SMS, WeCom, auto-contact, or payment tracking system.
- `.xls` and `.csv` uploads are not part of the Alpha baseline; use `.xlsx`.

## Data Safety

- Runtime data stays local under `data/` by default.
- Sensitive fields such as names, ID cards, phones, and addresses are masked in reports and exports where applicable.
- Cloud model calls default to redacted content. Sending original sensitive content requires explicit confirmation in the model gateway flow.
- API keys and local secrets must not be committed. Use local settings or environment files based on `.env.example`.
- Ignored runtime paths include the SQLite database, uploads, reports, legal document originals, knowledge notes, private skill draft bodies, and secrets.

## Legal And Investment Disclaimer

Legal risk analysis is an auxiliary prompt and screening aid. It does not replace advice from licensed lawyers.

Pricing output is an analytical estimate based on current data and assumptions. It does not constitute investment advice, valuation advice, or a purchase recommendation.

Users should verify asset authenticity, evidence chain completeness, limitation period, jurisdiction, collection compliance, and disposal assumptions before making investment or legal decisions.

## Verification Checklist

Before publishing this Alpha baseline, verify:

- `make test`
- `make dev PORT=8767`
- `make smoke PORT=8767`
- Browser smoke: create project, upload `samples/level1_basic.xlsx`, confirm fields, generate report, generate execution plan.
- `git diff --cached --check`
- `git status --short --ignored`
- Staged files contain no real asset package, contract original, database, report, API key, ID card, phone number, or private operating note.

## Next Milestones

- Add OCR and richer legal document parsing.
- Improve model and voice provider diagnostics.
- Add external court and judicial data integrations.
- Add Yindeng monitoring and industry intelligence feeds.
- Add stronger audit UI, export controls, and role-based permissions.
- Design safe community skill installation and sandbox execution.
