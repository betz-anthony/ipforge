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
| **Kea** | ISC DHCP (control-agent API) | read-only (free) | scopes/leases read; **push needs ISC premium hook** |

Recommended recording path: **BIND9 for DNS + Pi-hole for DHCP** (both verified,
both free), or **Pi-hole for everything** (simplest). Kea's reservation *push*
(`reservation-add`) requires ISC's premium `host_cmds` hook (see C) — use Pi-hole
for the free DHCP money shot.

> **Verified (2026-06-11):** BIND accepts IPForge's exact TSIG/RFC2136 update and
> serves it over AXFR; Pi-hole's API auth works. Use these two.

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

## C. ISC Kea (DHCP control agent) — read-only on the free tier

Built from `./kea/Dockerfile` (Kea 2.7 from ISC's public apt repo). Runs
`kea-dhcp4` + `kea-ctrl-agent`, so IPForge can **read** scopes and leases.

> **Reservation push is not free.** IPForge's `add_reservation` uses
> `reservation-add`, a command from the **`host_cmds` hook** — which is **ISC
> premium (subscriber-only)** and is **not** in the public repo (verified
> 2026-06-11: the open repo ships `lease_cmds`, `ha`, `stat_cmds`, … but not
> `host_cmds`). So free Kea answers "command not supported" on `reservation-add`.
> **For the DHCP money shot, use Pi-hole (A).** If you have an ISC subscription,
> drop `libdhcp_host_cmds.so` into the image and uncomment the `hooks-libraries`
> + `hosts-database` block in `kea/kea-dhcp4.conf` (the `kea-db` Postgres service
> is already provided for the host backend).

**Add as a provider** (Settings → Providers → Add → DHCP):
- type `keadhcp`, name `kea-demo`, `url` = `http://kea:8000`, `secret` = (blank)

**Read proof (works on the free tier):**
```bash
# Kea's configured scopes, straight from the control agent:
curl -s http://localhost:18000/ -H 'Content-Type: application/json' \
  -d '{"command":"config-get","service":["dhcp4"]}' | jq '.[0].arguments.Dhcp4.subnet4'
# Dynamic leases (lease_cmds, open source):
curl -s http://localhost:18000/ -H 'Content-Type: application/json' \
  -d '{"command":"lease4-get-all","service":["dhcp4"],"arguments":{"subnets":[1]}}' | jq
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
