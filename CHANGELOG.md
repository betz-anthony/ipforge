# Changelog

All notable changes to IPForge are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.0] - 2026-09-05

### Added

**DNS/DHCP record editing**
- DNS records and DHCP reservations can now be edited in place instead of
  delete-and-recreate. Zone/scope/IP identity stays locked; PTR records and
  linked DNS records can follow through on request; MS DNS, BIND, and GCP
  DNS updates are atomic where the provider API supports it.
- DHCP reservations can also register a matching DNS record inline
  (previously only available through the allocation flow).

**Outbound webhooks**
- Every audited write fires a signed HTTP webhook
  (`X-IPForge-Signature-256`), delivered via a transactional outbox with
  retry/backoff and dead-lettering. Settings → Webhooks UI for endpoint
  CRUD, test ping, and a paginated delivery log with redeliver.

**Python client library**
- `ipforge-client` on PyPI — a typed sync wrapper over the full `/api/v1`
  surface (subnets, addresses, VLANs, DNS, DHCP, drift, discovery, audit),
  with pagination iterators and a typed exception hierarchy.

**Drift detection**
- Cross-DNS-provider conflict detection (`dns_source_conflict`): flags an IP
  carrying an A/AAAA record in more than one configured DNS provider.

**Accessibility**
- WCAG 2.1 AA: keyboard-navigable tables, dialog focus traps, ARIA labeling
  across all data tables and forms, contrast fixes in both themes.

**Operations**
- `scripts/backup.sh` / `scripts/restore.sh` — Postgres dump/restore for
  both Docker Compose and Kubernetes, with migration-ordering guardrails.
- One-command demo environment (`scripts/demo-up.sh`) against real BIND,
  Kea, and Pi-hole backends.
- Published, reproducible scale benchmark: 100k addresses / 500 subnets on
  Postgres 16 (see `docs/scaling.md`).

## [1.1.0] - 2026-06-10

### Added
- Server-side table pagination for addresses, DNS, DHCP, and audit (WCAG AA:
  bounded, navigable tables).
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), and a pull
  request template.

### Changed
- **Breaking:** API paths are now served under `/api/v1/*` (was `/api/*`).
  Update any external API or token clients. The bundled frontend and MCP client
  are already updated.

## [1.0.0] - 2026-06-01

First public release.

### Added

**IPAM core**
- Subnet management with hierarchy (parent/child), reserved ranges, and an
  address-space heatmap (subnet map).
- IP address tracking with statuses, MAC addresses, hostnames, custom fields,
  and tags.
- VLAN management.
- Idempotent allocation API (keyed by hostname) with optional DNS/DHCP
  registration and rollback on failure.

**DDI providers** (configured at runtime in Settings → Providers; credentials
Fernet-encrypted at rest)
- DNS: `msdns` (WinRM), `bind` (AXFR + RFC2136), `pihole`, `cloudflare`,
  `route53`, `azure_dns`, `gcp_dns`.
- DHCP: `msdhcp` (WinRM), `keadhcp` (DHCPv4 + DHCPv6 with DUID), `pihole`.

**Reconciliation & monitoring**
- Drift detection — multi-way diff across IPAM ↔ DNS ↔ DHCP ↔ live scan
  (orphan/missing/mismatch/conflict categories incl. `missing_dhcp`,
  `ptr_mismatch`, `unreachable_assigned`).
- Drift auto-remediation — per-category policies (global or per-subnet),
  dry-run by default, safe IPAM-only and provider actions, gitops-aware.
- Continuous scanning — per-subnet ping sweep + scheduler, reachability
  history, alert events.
- Background sync of DNS/DHCP records into cache tables with auto-populate.

**Discovery & security**
- SNMP discovery — ARP + dot1q FDB + ifName join to IP ↔ MAC ↔ switchport ↔
  VLAN (enrich-only).
- Security events — rogue device / MAC move / IP conflict / new MAC, with
  reversible quarantine.

**Automation & integration**
- GitOps — declarative YAML apply for VLANs/subnets/reserved ranges/allocations
  with managed-marker prune.
- Automation rules — on rogue/drift events, tag or set address status.
- MCP server — agent-native access over the HTTP API (separate process/deps).

**Planning & history**
- Capacity forecasting — daily utilization snapshots + least-squares exhaustion
  projection + Dashboard widget.
- Lifecycle timeline — per-IP merged history with point-in-time reconstruction.

**Ops & access**
- Alerting — trigger queue → rules → channels (email/webhook/Slack/Teams/
  PagerDuty).
- Auth/RBAC — local + LDAP/AD, JWT + scoped API tokens, roles
  (admin / operator / scoped / requester / read-only) with per-subnet grants.
- IP-request/approval workflow, stale-IP reclamation, CSV import/export,
  audit log, Prometheus `/metrics`.

**Packaging**
- Docker Compose (prod images from `backend/Dockerfile.prod` +
  `frontend/Dockerfile`), Kubernetes/Kustomize manifests, public images on GHCR.

[Unreleased]: https://github.com/betz-anthony/ipforge/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/betz-anthony/ipforge/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/betz-anthony/ipforge/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/betz-anthony/ipforge/releases/tag/v1.0.0
