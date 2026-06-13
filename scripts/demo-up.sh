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

# Populate demo-lab so the subnet map / heatmap looks real: reserved ranges drive
# the legend (gateway / infra / DHCP pool), and a mix of address statuses gives
# the map colour. .1-.15 reserved, .16-.49 used, .100-.150 DHCP pool — leaving
# .50+ free so the on-camera "web01" allocation lands cleanly in open space.
addr() { # ip hostname status [mac]
  local body="{\"address\":\"$1\",\"subnet_id\":$SID,\"hostname\":\"$2\",\"status\":\"$3\""
  [ -n "${4:-}" ] && body="$body,\"mac_address\":\"$4\""
  curl -s -o /dev/null -X POST "$API/addresses" "${AUTH[@]}" -d "$body}"
}
if [ -n "$SID" ]; then
  echo "==> Populating demo-lab with reserved ranges + a realistic address mix (subnet map)..."
  for r in \
    '{"start_ip":"10.99.0.1","end_ip":"10.99.0.1","kind":"gateway","label":"Default gateway"}' \
    '{"start_ip":"10.99.0.2","end_ip":"10.99.0.15","kind":"reserved","label":"Infrastructure"}' \
    '{"start_ip":"10.99.0.100","end_ip":"10.99.0.150","kind":"dhcp_pool","label":"DHCP pool"}'; do
    curl -s -o /dev/null -X POST "$API/subnets/$SID/ranges" "${AUTH[@]}" -d "$r"
  done
  names=(app db web api cache queue mail proxy log mon)
  for i in $(seq 16 40); do
    addr "10.99.0.$i" "${names[$((i % 10))]}$(printf '%02d' "$i")" assigned "$(printf 'aa:bb:cc:00:00:%02x' "$i")"
  done
  for i in 41 42 43; do addr "10.99.0.$i" "rsv-$i" reserved; done
  for i in 44 45;    do addr "10.99.0.$i" "old-$i" deprecated "$(printf 'aa:bb:cc:00:01:%02x' "$i")"; done
  for i in 200 201 202 205; do addr "10.99.0.$i" "discovered-$i" discovered "$(printf 'aa:bb:cc:00:02:%02x' "$i")"; done
  for i in $(seq 100 124); do addr "10.99.0.$i" "dyn-$i" assigned "$(printf 'aa:bb:cc:00:03:%02x' "$i")"; done
  echo "   - reserved ranges + ~60 addresses created (.50+ left free for the live allocation)"
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
    Subnets    demo-lab       10.99.0.0/24      populated — open it to see
                                                 the subnet map (gateway,
                                                 reserved, DHCP pool, ~60 hosts)
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
