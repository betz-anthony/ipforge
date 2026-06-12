# Demo backends — real, disposable DNS/DHCP for the screencast

These are **real** DNS/DHCP servers in throwaway containers that IPForge actually
pushes config to. Use them to record the money shot: allocate an IP in IPForge →
the DNS A record and DHCP reservation appear **on the server**, proven with
`dig` / `curl` (not just IPForge's own UI).

Run them alongside the main stack (they join the same Docker network, so the
`api` container reaches them by service name):

```bash
docker compose \
  -f docker-compose.yml \
  -f examples/demo-backends/docker-compose.demo-backends.yml \
  up -d
```

Three backends, ranked by setup friction:

| Backend | Role | Friction | Use for |
|---|---|---|---|
| **Pi-hole** | DNS **and** DHCP, one container | none | fastest end-to-end demo |
| **BIND9** | authoritative DNS (RFC2136) | low | credible "real DNS" proof |
| **Kea** | ISC DHCP (control-agent API) | medium (one-time `build`) | authoritative-DHCP push (Kea 3.0) |

Recommended recording path: **BIND9 for DNS + Kea or Pi-hole for DHCP** — all
three are free and verified. Pi-hole is the one-container quick path; Kea 3.0 is
the credible "real DHCP server" story.

> **Verified live (2026-06-12):** BIND accepts IPForge's exact TSIG/RFC2136
> update and serves it over AXFR; Pi-hole's API auth works; **Kea 3.0
> `reservation-add` → `reservation-get-all` round-trips** (host_cmds is open
> source in Kea 3.0 — no subscription).

> Throwaway only. The TSIG key and passwords here are committed demo values —
> never reuse them anywhere real. `docker compose ... down -v` wipes everything.

---

## A. Pi-hole (DNS + DHCP, one container) — easiest

Admin UI: <http://localhost:8081/admin> (password `demodemo`).

**Add as a provider in IPForge** (Settings → Providers → Add):
- **DNS** — type `pihole`, name `pihole-demo`, `url` = `http://pihole`,
  `password` = `demodemo`.
- **DHCP** — type `pihole`, name `pihole-demo`, `url` = `http://pihole`,
  `password` = `demodemo`. Enable Pi-hole's DHCP server in its admin UI first
  (Settings → DHCP) with a small range, e.g. `10.99.0.100–10.99.0.150`.

**Prove on camera (after an allocation with register_dns/register_dhcp):**
```bash
# DNS — Pi-hole answers for the name IPForge just created:
dig @127.0.0.1 -p 15354 web01.demo.lab +short
# DHCP — the reservation shows in the admin UI (Settings → DHCP → static leases),
# or via the API:
curl -s "http://localhost:8081/api/dhcp/leases" -H "X-FTL-SID: <sid>"
```

## B. BIND9 (authoritative DNS, RFC2136) — credible DNS proof

Serves the `demo.lab` zone; accepts TSIG-signed dynamic updates (what IPForge's
`bind` provider sends) and zone transfers (AXFR, how it reads records).

**Add as a provider** (Settings → Providers → Add → DNS):
- type `bind`, name `bind-demo`
- `host` = `bind9`
- `port` = `53`
- `tsig_key_name` = `ipforge-key`
- `tsig_key_secret` = `MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXY=`
- `tsig_algorithm` = `hmac-sha256`
- `zones` = `demo.lab`

**Prove on camera:**
```bash
# Before: name doesn't resolve
dig @127.0.0.1 -p 15353 web01.demo.lab A +short        # (empty)
# Allocate web01 in IPForge with register_dns + dns_zone=demo.lab
# After: the A record IPForge just wrote, live on BIND:
dig @127.0.0.1 -p 15353 web01.demo.lab A +short        # 10.99.0.x
# Full record + the zone:
dig @127.0.0.1 -p 15353 demo.lab AXFR \
  -y "hmac-sha256:ipforge-key:MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXY="
```

## C. ISC Kea 3.0 (DHCP control agent) — free reservation push

Built from `./kea/Dockerfile` (Kea **3.0** from ISC's `kea-3-0` apt repo, where
ISC open-sourced all hooks). Runs `kea-dhcp4` + `kea-ctrl-agent` with the
`host_cmds` + `pgsql` hooks and a Postgres host backend, so IPForge can add and
remove reservations at runtime. First run builds it (`build kea`, ~2 min); the
build fails if `libdhcp_host_cmds.so` is missing.

> Two Kea-3.0 specifics already handled here, in case you adapt this: control
> sockets must live under `/var/run/kea` (not `/tmp`), and hook libraries must be
> referenced by their real arch path (`/usr/lib/x86_64-linux-gnu/kea/hooks/…`),
> which is why the `kea` service pins `platform: linux/amd64`. The Postgres host
> backend is itself a hook in 3.0 (`libdhcp_pgsql.so`) and is loaded alongside
> `host_cmds`.

**Add as a provider** (Settings → Providers → Add → DHCP):
- type `keadhcp`, name `kea-demo`, `url` = `http://kea:8000`, `secret` = (blank)

**Prove on camera (after an IPForge allocation with register_dhcp)** — the
DHCP analog of `dig`: query Kea's control agent for its live reservation state.

```bash
# Convenience wrapper (host-side, needs curl + jq):
./examples/demo-backends/kea-query.sh              # reservations in subnet 1
./examples/demo-backends/kea-query.sh leases       # dynamic leases

# Or the raw control-agent call it wraps:
curl -s http://localhost:18000/ -H 'Content-Type: application/json' \
  -d '{"command":"reservation-get-all","service":["dhcp4"],"arguments":{"subnet-id":1}}' \
  | jq '.[0].arguments.hosts'
```

---

## Screencast wiring (maps to the script in `marketing.md`)

Beat 3 (the money shot): split-screen IPForge UI + a terminal.
1. Terminal: `dig @127.0.0.1 -p 15353 web01.demo.lab A +short` → empty.
2. UI: allocate next-free IP in a subnet → hostname `web01`, MAC set,
   `register_dns` (zone `demo.lab`) + `register_dhcp` on → submit.
3. Terminal: re-run the `dig` → the A record appears. Run the Kea/Pi-hole proof →
   the reservation appears. **That's the differentiator** — config landed on the
   real server, not just IPForge.

Beat 5 (IaC): same thing via Terraform —
```hcl
resource "ipforge_allocation" "web01" {
  subnet_id    = data.ipforge_subnet.app.id
  hostname     = "web01"
  register_dns = true
  dns_zone     = "demo.lab"
}
```
`terraform apply`, then the same `dig` proof.

## Teardown

```bash
docker compose -f docker-compose.yml \
  -f examples/demo-backends/docker-compose.demo-backends.yml down -v
```
