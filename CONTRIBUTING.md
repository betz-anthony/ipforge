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

## Versioning

IPForge follows [Semantic Versioning](https://semver.org/). The version bump for
a release is derived from the Conventional Commit types since the last tag — it
is not chosen by hand:

| Highest-severity change since last tag | Bump |
|---|---|
| Any `!` suffix or `BREAKING CHANGE:` footer | **MAJOR** (`x.0.0`) |
| Any `feat:` (no breaking change) | **MINOR** (`x.y.0`) |
| Only `fix:` / `perf:` / `refactor:` / `docs:` / `chore:` | **PATCH** (`x.y.z`) |

Run `scripts/suggest-bump.sh` to print the recommended bump and next version
from the commits since the last `v*` tag. The `[Unreleased]` section of
`CHANGELOG.md` is the human-readable mirror of the same signal.

**The REST API is versioned separately by its URL path (`/api/vN`).** That path
is the API compatibility boundary, not the application version. A
backward-incompatible API change ships as a **new `/api/vN`** (a `feat:`, which
bumps the app MINOR) — it does **not** force an app MAJOR bump, and it is **not**
marked `!`. Reserve `!` / `BREAKING CHANGE:` for application-level
incompatibilities: removing a feature or endpoint version, an irreversible DB
migration, or a breaking change to config/env/CLI. This keeps app releases
readable while the `/api/vN` path carries API compatibility.

## Documentation layout

- Public docs live under `docs/` (`user-guide.html`, `examples/`).
- Internal/private docs under `docs/private/` are excluded from the public
  mirror — contributors edit public docs only.

## Licensing of contributions

IPForge uses a **dual-license model**: the [GNU AGPL v3.0](LICENSE) for the
community, and a separate **commercial license** for users who cannot or do not
wish to comply with the AGPL. That is only possible while the maintainer can
relicense the whole work, so contributions are accepted on these terms:

By submitting a contribution (pull request, patch, or any code/docs/material) you
agree that:

1. **You have the right to submit it** — it is your original work, or you are
   authorized to submit it under these terms (this is the intent of the DCO
   sign-off below).
2. **You grant the maintainer (Anthony Betz) a perpetual, worldwide,
   non-exclusive, royalty-free, irrevocable license to use, reproduce, modify,
   sublicense, and distribute your contribution, including the right to license it
   under terms of the maintainer's choosing** — i.e. under the AGPLv3 *and* under
   separate commercial/proprietary terms.
3. You retain copyright in your contribution; this grant does not transfer
   ownership — it only keeps the project offerable under both AGPLv3 and a
   commercial license.

The community edition stays fully copyleft (AGPLv3) for everyone; the grant just
lets the maintainer fund development via commercial licensing. If you cannot agree
to this, open an issue to discuss before contributing.

> The **Python client** (`clients/python`, Apache-2.0) and the **Terraform
> provider** (MPL-2.0) are separately licensed; contributions to those are accepted
> under their respective licenses.

### Developer Certificate of Origin (DCO)

Sign off every commit (`git commit -s`) per the [DCO](https://developercertificate.org/),
certifying you wrote the patch or may otherwise submit it under the terms above:

```
Signed-off-by: Your Name <you@example.com>
```

> This CLA-style grant is a practical measure, not formal legal advice. For a
> high-stakes commercial program, have a lawyer review the contribution terms.

## Reporting bugs / requesting features

Use the GitHub issue templates. For security issues, see `SECURITY.md` — do not
open a public issue.
