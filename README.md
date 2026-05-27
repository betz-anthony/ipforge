# IPForge

Self-hosted IP Address Management with integrated DNS and DHCP control.

Tracks subnets, IP allocations, DNS zones/records, and DHCP scopes/reservations across pluggable providers — Microsoft DNS/DHCP (WinRM), BIND (dnspython/TSIG), Pi-hole v6, ISC Kea. Includes request/approval workflow, live availability scanning, collision detection, alerting (email/webhook/Slack/Teams/PagerDuty), audit log, LDAP/AD auth, and a Prometheus metrics endpoint.

## Stack

- **Backend:** FastAPI, SQLAlchemy 2.0, PostgreSQL, Alembic
- **Frontend:** React + Vite + TypeScript, TanStack Query
- **Packaging:** Docker Compose for local dev/prod, Kustomize for Kubernetes

## Quick start (Docker Compose)

```bash
cp .env.example .env        # fill in MS_WINRM_* and provider hostnames
docker compose up --build
```

Web UI: <http://localhost> · API docs: <http://localhost:8000/docs>

## Local development

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://localhost:8000
```

Frontend (Vite proxies `/api` to `localhost:8000`):

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

Tests:

```bash
cd backend && python -m pytest -q
cd frontend && npm run lint && npm run build
```

## Configuration

All configuration is via environment variables (see `.env.example`). Highlights:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | JWT signing key (auto-generated on first run if empty) |
| `SECRET_KEY` | Fernet key encrypting provider/LDAP secrets at rest |
| `DNS_PROVIDER` / `DHCP_PROVIDER` | Comma-separated active providers |
| `MS_WINRM_HOST` / `MS_WINRM_USER` / `MS_WINRM_PASSWORD` | WinRM credentials for MS providers |
| `MS_DNS_SERVER` / `MS_DHCP_SERVER` | Target Windows DNS/DHCP servers |

Provider-specific settings (Pi-hole URL, BIND TSIG key, Kea Control Agent URL) can be entered through **Settings → Providers** in the UI and are persisted encrypted in the database.

## Architecture

```
backend/app/
  main.py              FastAPI app, CORS, lifespan
  config.py            pydantic-settings — env-driven config
  database.py          SQLAlchemy engine, Base, get_db()
  models/              SQLAlchemy 2.0 ORM models
  schemas/             Pydantic request/response schemas
  api/                 FastAPI routers (subnets, addresses, dns, dhcp, ...)
  providers/
    dns/   base + msdns, bind, pihole implementations
    dhcp/  base + msdhcp, keadhcp, pihole implementations
    registry.py        factory selecting provider per category

frontend/src/
  api/client.ts        axios + typed API wrappers
  pages/               route-level pages
  components/          reusable UI primitives
```

### Adding a provider

Implement `DNSProvider` (or `DHCPProvider`) in `backend/app/providers/<category>/<name>.py`, register it in `registry.py`. No API or model changes needed.

## Deployment

- **Docker Compose** — `docker compose up --build` (production-tuned variants in `docker-compose.prod.yml`).
- **Kubernetes** — manifests in `k8s/` are applied with `kubectl apply -k k8s/`. The Ingress expects an nginx-ingress controller and a TLS Secret named `wildcard-tls` (or override).
- **Database migrations** — Alembic. `alembic upgrade head` runs automatically on container start; CI/CD can run it explicitly.

## Security

- Authentication: local users + optional LDAP/AD bind with group→role mapping
- Roles: `admin` / `operator` / `readonly` / `requester` / `scoped` (per-subnet RBAC)
- All provider credentials encrypted at rest with Fernet (`SECRET_KEY`)
- Audit log captures create/update/delete with before/after state and acting user
- API tokens for machine clients (Prometheus, scripts) with scoped permissions

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).

Modifications you distribute (including container images you publish) must be released under GPL v3 with source available.
