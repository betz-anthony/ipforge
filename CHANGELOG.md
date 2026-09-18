# Changelog

All notable changes to IPForge are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

**Reserved Ranges**
- Each DHCP scope's gateway and exclusion ranges are now auto-synced into
  Reserved Ranges (msdhcp: native exclusions + gateway; Kea: gateway +
  pool-gap-derived exclusions; Pi-hole: gateway only), so the subnet map and
  Allocation API stop treating them as free space. Auto-synced ranges are
  read-only in the UI except for delete.
- Per-scope opt-out for that auto-sync (DHCP page scope list, "Sync to
  Reserved Ranges" toggle) — for a scope kept in DHCP for testing/
  monitoring rather than real distribution, so its gateway/exclusions
  don't get unioned into a subnet's Reserved Ranges as if authoritative.
  Leases and pool data for the scope keep syncing either way.

**Search**
- Search results are now clickable, navigating to the matching record's
  edit view via an explicit Edit button (DNS records, DHCP reservations,
  addresses, subnets) instead of dead-ending on a read-only row.

**Subnet map**
- The heatmap's "Create address here" popup on a free cell is now a real
  form (status, hostname, MAC, description) instead of creating a bare
  address with no fields.
- The subnet detail drawer now shows the subnet's numeric ID.

**Ops**
- `docs/examples/ansible/get-next-free-ip.yml` and `create-test-vm.yml` —
  two new standalone Ansible playbook examples for the Allocation API.

### Fixed

**Sorting**
- IP address columns (Addresses list, DHCP lease list, a subnet's Reserved
  Ranges) sorted lexicographically as text (`10.10.1.1, 10.10.1.100,
  10.10.1.103, 10.10.1.11`) instead of in real numeric order.

**DNS sync**
- MS DNS: CNAME and NS records were silently dropped from `get_records()`
  instead of being synced.
- MS DNS: a record with a TTL above 32 bits (e.g. a huge NS TTL) could
  throw and abort the entire zone's sync; now handled without losing the
  rest of the zone.
- A zone whose fetch failed mid-sync could wipe that zone's previously
  cached DNS records instead of leaving them in place — sync now only
  deletes cache rows for zones that fetched successfully this pass.
- The DNS record-type filter only applied within the current page instead
  of across the whole zone.
- A DNS record with a very long value (e.g. a long TXT record) could push
  the zone header's Add Record button off-screen; values now wrap instead
  of overflowing.

**DHCP**
- MS DHCP: `Remove-DhcpServerv4Reservation` was called with an invalid
  `-Force` flag, failing every delete.
- MS DHCP: `Add-DhcpServerv4Reservation`'s `-ClientId` requires
  dash-delimited hex; IPForge's colon-delimited MAC form was rejected
  outright.
- MS DHCP: a DUID-based client identifier (common on newer Windows guest
  OSes) was being stored and displayed as if it were the lease's MAC
  address.
- MS DHCP: editing a reservation's MAC address deletes and re-adds it on
  the DHCP server; if the add failed, the reservation is now restored
  instead of left permanently deleted.

**Drift**
- `hostname_mismatch` compared MS-DNS's zone-relative name against IPAM/
  DHCP's FQDN, flagging nearly every MS-DNS-zone address as a false
  positive; now compares the host label on both sides.

### Security

- Cleared HIGH-severity CVEs (util-linux/libuuid) in the web container
  image.

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
