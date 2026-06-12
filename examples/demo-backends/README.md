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
| **Kea** | ISC DHCP (control-agent API) | medium (one-time `build`; hook guaranteed) | authoritative-DHCP story |

Recommended recording path: **BIND9 for DNS + Pi-hole for DHCP** (both reliable),
or **Pi-hole for everything** (simplest). Kea is included for completeness — see
its caveat below before relying on it on recording day.

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
dig @127.0.0.1 -p 5354 web01.demo.lab +short
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
dig @127.0.0.1 -p 5353 web01.demo.lab A +short        # (empty)
# Allocate web01 in IPForge with register_dns + dns_zone=demo.lab
# After: the A record IPForge just wrote, live on BIND:
dig @127.0.0.1 -p 5353 web01.demo.lab A +short        # 10.99.0.x
# Full record + the zone:
dig @127.0.0.1 -p 5353 demo.lab AXFR \
  -y "hmac-sha256:ipforge-key:MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXY="
```

## C. ISC Kea (DHCP control agent) — advanced

IPForge's `keadhcp` provider uses `reservation-add` / `reservation-del`, which
require Kea's **`host_cmds` hook library** plus a **writable host backend**
(Postgres here). Both are wired up, and the hook is **guaranteed**:

> The `kea` service is **built from `./kea/Dockerfile`**, which installs Kea 2.7+
> (where ISC open-sourced the hooks — `host_cmds` is premium-only in 2.6 and
> earlier) and **fails the build if `libdhcp_host_cmds.so` is absent**. So you
> can't end up recording against a Kea that silently rejects `reservation-add`.
> First run builds it: `docker compose ... build kea` (a minute or two). If
> ISC's apt package names drift, the build errors at `apt-get install` with a
> clear message — adjust `KEA_REPO` / the package list in the Dockerfile.

**Add as a provider** (Settings → Providers → Add → DHCP):
- type `keadhcp`, name `kea-demo`
- `url` = `http://kea:8000`
- `secret` = (leave blank)

**Prove on camera:**
```bash
# The reservation IPForge just made, straight from Kea's control agent:
curl -s http://localhost:8000/ \
  -H 'Content-Type: application/json' \
  -d '{"command":"reservation-get-all","service":["dhcp4"],"arguments":{"subnet-id":1}}' | jq
```

---

## Screencast wiring (maps to the script in `marketing.md`)

Beat 3 (the money shot): split-screen IPForge UI + a terminal.
1. Terminal: `dig @127.0.0.1 -p 5353 web01.demo.lab A +short` → empty.
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
