# Contributing to IPForge

Thanks for your interest in improving IPForge. This guide covers local setup,
the test gates every change must pass, and how to open a pull request.

## Local development

Full stack (Docker Compose):

```bash
cp .env.example .env   # set DB_PASSWORD; JWT/SECRET keys auto-generate if blank
docker compose up --build
```

Backend only:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://localhost:8000, docs at /docs
```

Frontend only (proxies /api to localhost:8000):

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

## Test gates (run before every PR)

- Backend: `cd backend && python -m pytest -q` — all tests must pass.
- Frontend: `cd frontend && npm run build` and `npm run lint` — clean.

A PR that does not pass these will not be merged.

## Commit + PR conventions

- Use [Conventional Commits](https://www.conventionalcommits.org/) for messages
  (`feat:`, `fix:`, `docs:`, `ci:`, `refactor:`, `test:`). Use a `!` suffix
  (e.g. `feat(api)!:`) for breaking changes.
- Do **not** add `Co-Authored-By` trailers.
- Keep PRs focused on a single change.
- Update `CHANGELOG.md` under `[Unreleased]` in the same PR.
- Update user-facing docs when behavior changes.

## Documentation layout

- Public docs live under `docs/` (`user-guide.html`, `examples/`).
- Internal/private docs under `docs/private/` are excluded from the public
  mirror — contributors edit public docs only.

## Reporting bugs / requesting features

Use the GitHub issue templates. For security issues, see `SECURITY.md` — do not
open a public issue.
