# AutoTax

Nepal payroll & salary-TDS engine for companies paying in NPR or foreign currency (e.g. USD).
Plan: see `~/.claude/plans/i-want-to-work-lovely-bachman.md`.

## Status
- [x] Phase 1 — tax engine + versioned rule files + golden/property tests
- [x] Phase 2 (partial) — NRB forex client, FX conversion with fallback & manual override
- [x] Rule watcher — official-source monitoring, archived hashes, draft proposals, payroll gate
- [x] Phase 3 — Postgres models, FastAPI, payroll-run lifecycle, audit log
- [x] Phase 4 — Next.js frontend
- [ ] Phase 5 — IRD e-TDS / SSF / CIT exports, payslips

## Running locally
```
docker compose up -d db                                   # Postgres 17 on localhost:5434
cd backend && uv run alembic upgrade head
uv run uvicorn app.main:app --port 8010 --reload          # API at http://localhost:8010/docs
cd ../frontend && npm install
BACKEND_URL=http://localhost:8010 npm run dev             # app at http://localhost:3000
```
Tests: `cd backend && uv run pytest` (needs the `autotax_test` database:
`docker compose exec db psql -U autotax -c "create database autotax_test"`).
Set `JWT_SECRET` to a long random value for any shared deployment.

## How it works
- `rules/np/<FY>.yaml` is the **only** place rates, caps and slabs live. Every parameter cites a
  source document + section and has a `status` (`verified` / `corroborated` / `needs_review`).
  The loader rejects uncited or incomplete files.
- `backend/app/engine/` is pure: `compute_annual_tax(...)` and `compute_month(...)` return numbers
  plus a step-by-step trace citing the rule for each figure.
- Monthly TDS projects the year (actual months + recurring × remaining), computes annual tax and
  spreads the unpaid balance; the final month trues up, so the year's TDS equals the liability
  even when FX rates, salary or bonuses change.

```
cd backend && uv run pytest
```

## Keeping rules current: the rule watcher
```
cd backend
uv run python -m app.watcher init           # once: record what is already published as the baseline
uv run python -m app.watcher run            # daily: new docs → archive + hash → (Claude) proposals → report
uv run python -m app.watcher status         # coverage / review status / budget-season check
uv run python -m app.watcher extract X.pdf  # propose changes from a PDF you already have
uv run python -m app.watcher fetch-sources  # re-download archived source PDFs and verify hashes
```
- **Sources** (`rules/watch_sources.yaml`): IRD Finance Act / Income Tax Act / notices / home,
  MoF, Law Commission (ordinances), SSF. Relevance by title keywords (Nepali + English).
- **Documents** are archived as `rules/sources/<sha256[:16]>.pdf` (git-ignored; hashes live in
  the rule files). Most are scans with no usable text layer.
- **Proposals** (optional, needs an AI key): the model reads the PDF pages and maps provisions
  onto existing rule parameters, each with page number + verbatim quote. Output is validated (known
  param, page in range, value passes the rule-file schema) and written as a DRAFT to
  `rules/np/proposed/` — never loaded. The report shows the tax impact on the golden sample employees.
- **Activation is manual**: a reviewer checks each value against the cited page, marks it `verified`,
  and moves the file into `rules/np/`. Mid-year changes are a new version (`2083-84.v2.yaml`) with its own
  `effective_from`; the highest version covering a date wins.
- **Payroll gate** (`app/engine/gate.py`): blocks finalizing payroll when no rule file covers the date,
  when an archived source no longer matches its hash, or (unless explicitly acknowledged and logged)
  when rules are unverified. Budget-season alert from Jestha 15 until next FY's rules exist.
- **Automation** (`.github/workflows/rule-watch.yml`): daily at 07:00 NPT; opens/updates one rolling
  PR labelled `rule-watch`, and an issue labelled `rule-alert` for coverage/budget-season alerts.
  Add repository secret `GEMINI_API_KEY` (free tier) or `ANTHROPIC_API_KEY` to enable proposals.
- **AI providers** (`app/watcher/providers.py`): Gemini (free tier; newest stable Flash model is
  auto-selected, override with `GEMINI_MODEL`) or Claude. Pick with `--provider` / `AUTOTAX_EXTRACTOR`;
  default is the first with a key, Gemini first. Free-tier rate limits are retried with back-off.

## ⚠️ Before using for real tax payments
Rule file review status is `draft`. The official Finance Act 2083 (Gazette 2083-03-30, 415-page scan)
is archived and hash-pinned as source `fa2083`; a CA must confirm each value against its Schedule 1
and set `status: verified` (or run `python -m app.watcher extract` on it to get page-cited proposals):
- FY 2083/84 slabs (1% to 10L, 10% / 20% / 27% / 29%; single & couple merged) — corroborated by
  multiple secondary sources, not yet checked against the archived Act.
- Carried-over values marked `needs_review`: insurance caps (40k/20k/5k), remote-area caps,
  female 10% rebate (and whether it applies on total tax incl. SST), disability first-slab +50%,
  non-resident 25%, donation caps.
- FX policy: NRB **buying** rate on the **payment date** (fallback: nearest prior published rate
  within 7 days). Confirm with your auditor; switch via `fx.rate_type` / `fx.date_basis`.
- TDS rounding precision (`rounding.tds_places`, currently 2).
