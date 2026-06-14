#!/usr/bin/env bash
# One-shot launcher for the IPForge demo/screencast environment:
#   - full stack (db + api + web) AND the real demo backends (bind9, kea, pihole)
#   - then auto-configures the DNS/DHCP providers + a demo subnet, so you open
#     the UI already demo-ready and just allocate on camera.
#
# Usage:  scripts/demo-up.sh
# Teardown: scripts/demo-down.sh
#
# Requires: Docker running, plus `curl`, `jq`, and `dig` on the host.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE=(-f docker-compose.yml -f examples/demo-backends/docker-compose.demo-backends.yml)
API="http://localhost:8000/api/v1"
TSIG_SECRET="MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXY="

command -v jq  >/dev/null || { echo "need jq (brew install jq)"; exit 1; }
command -v dig >/dev/null || { echo "need dig"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker isn't running — start Docker Desktop first."; exit 1; }

echo "==> Building + launching stack + demo backends (first run builds images; be patient)..."
docker compose "${COMPOSE[@]}" up -d --build

wait_for() { # name, cmd...
  local name="$1"; shift; printf "==> waiting for %s" "$name"
  for _ in $(seq 1 60); do if "$@" >/dev/null 2>&1; then echo " ok"; return 0; fi; printf "."; sleep 3; done
  echo " TIMEOUT"; return 1
}

api_health()  { curl -sf http://localhost:8000/health; }
bind_ready()  { dig @127.0.0.1 -p 15353 demo.lab SOA +short | grep -q SOA || dig @127.0.0.1 -p 15353 demo.lab SOA +short | grep -q ns1; }
kea_ready()   { curl -s http://localhost:18000/ -H 'Content-Type: application/json' \
                  -d '{"command":"config-get","service":["dhcp4"]}' | jq -e '.[0].result==0' >/dev/null; }
pihole_ready(){ curl -sf -o /dev/null "http://localhost:8081/admin/"; }

wait_for "API"    api_health
wait_for "BIND"   bind_ready  || echo "  (bind not answering yet — continuing)"
wait_for "Kea"    kea_ready   || echo "  (kea not answering yet — continuing)"
wait_for "Pi-hole" pihole_ready || echo "  (pihole still starting — continuing)"

echo "==> Configuring IPForge via API (admin/admin)..."
TOKEN="$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin&password=admin' | jq -r '.access_token // empty')"
[ -n "$TOKEN" ] || { echo "ERROR: login failed (is the admin seed done?)"; exit 1; }
AUTH=(-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")

mkprov() { # json -> prints "name: HTTP_CODE"
  local code; code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/provider-configs" "${AUTH[@]}" -d "$2")"
  printf "   - %-18s %s\n" "$1" "$code"
}
mkprov "bind-demo (DNS)"  "{\"category\":\"dns\",\"provider_type\":\"bind\",\"name\":\"bind-demo\",\"config\":{\"host\":\"bind9\",\"port\":53,\"tsig_key_name\":\"ipforge-key\",\"tsig_key_secret\":\"$TSIG_SECRET\",\"tsig_algorithm\":\"hmac-sha256\",\"zones\":\"demo.lab\"},\"enabled\":true}"
mkprov "kea-demo (DHCP)"  '{"category":"dhcp","provider_type":"keadhcp","name":"kea-demo","config":{"url":"http://kea:8000","secret":""},"enabled":true}'
mkprov "pihole-demo (off)" '{"category":"dns","provider_type":"pihole","name":"pihole-demo","config":{"url":"http://pihole","password":"demodemo"},"enabled":false}'

echo "==> Creating demo subnet 10.99.0.0/24 (request-eligible, pinned to bind-demo + kea-demo)..."
SID="$(curl -s -X POST "$API/subnets" "${AUTH[@]}" \
  -d '{"name":"demo-lab","cidr":"10.99.0.0/24","dns_provider_name":"bind-demo","dhcp_provider_name":"kea-demo","request_eligible":true}' \
  | jq -r '.id // empty')"
[ -n "$SID" ] && echo "   - subnet id $SID" || echo "   - (subnet may already exist; check the UI)"

# Populate demo-lab so every tab tells the same story. Reserved ranges drive the
# map legend (gateway / infra / DHCP pool); the managed hosts are allocated through
# the REAL flow so each gets a live BIND A record and (most) a Kea reservation — so
# the subnet map, the DNS tab, and the DHCP tab all agree and dig / kea-query prove
# every host. A few discovered/deprecated hosts are added with no DNS (realistic, and
# it gives the Drift page something to show). .16+ fills up; .34+ stays free so the
# on-camera "web01" request lands cleanly in open space.
addr() { # ip hostname status [mac]
  local body="{\"address\":\"$1\",\"subnet_id\":$SID,\"hostname\":\"$2\",\"status\":\"$3\""
  [ -n "${4:-}" ] && body="$body,\"mac_address\":\"$4\""
  curl -s -o /dev/null -X POST "$API/addresses" "${AUTH[@]}" -d "$body}"
}
if [ -n "$SID" ]; then
  echo "==> Populating demo-lab: reserved ranges + managed hosts (real DNS + DHCP)..."
  for r in \
    '{"start_ip":"10.99.0.1","end_ip":"10.99.0.1","kind":"gateway","label":"Default gateway"}' \
    '{"start_ip":"10.99.0.2","end_ip":"10.99.0.15","kind":"reserved","label":"Infrastructure"}' \
    '{"start_ip":"10.99.0.100","end_ip":"10.99.0.150","kind":"dhcp_pool","label":"DHCP pool"}'; do
    curl -s -o /dev/null -X POST "$API/subnets/$SID/ranges" "${AUTH[@]}" -d "$r"
  done
  # Managed hosts via the allocation API: every one gets an A record in BIND; ~2/3 of
  # them also get a Kea reservation (the rest are DNS-only — a realistic mix that also
  # surfaces missing_dhcp on the Drift page). Then mark them assigned for the map.
  # NB: avoid the name "web01" — that's reserved for the pending on-camera request.
  hosts=(dc01 dc02 dns01 vcenter app01 app02 db01 db02 cache01 mon01 mail01 proxy01 ci01 nas01 log01 ns2 kdc01 fileserv)
  n=0
  for h in "${hosts[@]}"; do
    n=$((n + 1)); mac=$(printf 'aa:bb:cc:00:10:%02x' "$n")
    body="{\"hostname\":\"$h\",\"mac_address\":\"$mac\",\"register_dns\":true,\"dns_zone\":\"demo.lab\""
    [ $((n % 3)) -ne 0 ] && body="$body,\"register_dhcp\":true"   # ~2/3 also get DHCP
    id=$(curl -s -X POST "$API/subnets/$SID/allocate" "${AUTH[@]}" -d "$body}" | jq -r '.id // empty')
    [ -n "$id" ] && curl -s -o /dev/null -X PUT "$API/addresses/$id" "${AUTH[@]}" -d '{"status":"assigned"}'
  done
  # Discovered / deprecated hosts with NO DNS — realistic, adds map colour + Drift.
  addr "10.99.0.200" "discovered-200" discovered "aa:bb:cc:00:20:01"
  addr "10.99.0.201" "discovered-201" discovered "aa:bb:cc:00:20:02"
  addr "10.99.0.45"  "old-decom"      deprecated "aa:bb:cc:00:20:03"
  echo "   - ${#hosts[@]} managed hosts (live DNS + DHCP) + 3 discovered/deprecated; .34+ left free"
fi

echo "==> Creating dual-stack demo subnet 2001:db8:da::/64 (DNS-only, pinned to bind-demo)..."
SID6="$(curl -s -X POST "$API/subnets" "${AUTH[@]}" \
  -d '{"name":"demo-lab-v6","cidr":"2001:db8:da::/64","ip_version":6,"dns_provider_name":"bind-demo","request_eligible":true}' \
  | jq -r '.id // empty')"
[ -n "$SID6" ] && echo "   - subnet id $SID6" || echo "   - (v6 subnet may already exist; check the UI)"

# Seed a pending IP request so the UI money-shot is a clean "Approve + Allocate"
# (the Register DNS/DHCP toggles live in the Requests approval dialog).
if [ -n "$SID" ]; then
  echo "==> Seeding a pending IP request for web01 (for the UI Approve+Allocate flow)..."
  RC="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/requests" "${AUTH[@]}" \
    -d "{\"subnet_id\":$SID,\"hostname\":\"web01\",\"mac_address\":\"aa:bb:cc:dd:ee:01\",\"purpose\":\"Demo web server allocation\"}")"
  echo "   - request POST: $RC"
fi

# The background sync ran once at API boot — BEFORE the providers above existed —
# so the cache (DHCP scopes, DNS zones) is empty and the next auto-sync is ~5 min
# out. Trigger one now and wait for it, so the DHCP page shows the Kea scope and
# the DNS zone dropdown is populated the moment you log in.
echo "==> Triggering initial provider sync (DHCP scopes + DNS zones)..."
curl -s -o /dev/null -X POST "$API/sync/trigger" "${AUTH[@]}"
scopes_ready() { [ "$(curl -s "${AUTH[@]}" "$API/dhcp/scopes" | jq 'length')" -gt 0 ]; }
wait_for "DHCP scopes" scopes_ready || echo "  (sync still running — scopes will appear within ~5 min)"

cat <<EOF

════════════════════════════════════════════════════════════════════
  IPForge is up.  Open  http://localhost:3000   (admin / admin)
════════════════════════════════════════════════════════════════════

  What's already set up
    Subnets    demo-lab       10.99.0.0/24      ~18 managed hosts, live in
                                                 DNS + DHCP (subnet map,
                                                 DNS tab and DHCP tab all agree)
               demo-lab-v6    2001:db8:da::/64  dual-stack
    DNS        bind-demo      BIND, zone demo.lab (RFC2136 + AXFR)
    DHCP       kea-demo       ISC Kea, scope 10.99.0.0/24 (.100–.150)
    Requests   web01          one request pending approval

  The 90-second walkthrough
    1. Subnets → demo-lab — the heatmap shows the space at a glance.
    2. Requests → web01 → Approve + Allocate.
         Tick Register DNS (zone demo.lab) and Register DHCP, then approve.
       IPForge allocates the next free IP and pushes the records to the
       real DNS and DHCP servers.
    3. Confirm it landed on the actual servers:
         dig @127.0.0.1 -p 15353 web01.demo.lab A +short
         ./examples/demo-backends/kea-query.sh
    4. Dual-stack: allocate a host in demo-lab-v6 the same way, then
         dig @127.0.0.1 -p 15353 web6.demo.lab AAAA +short

  When you're done:  scripts/demo-down.sh   (stops everything, wipes state)
════════════════════════════════════════════════════════════════════
EOF
