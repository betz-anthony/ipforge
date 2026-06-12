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

echo "==> Creating demo subnet 10.99.0.0/24 (pinned to bind-demo + kea-demo)..."
SID="$(curl -s -X POST "$API/subnets" "${AUTH[@]}" \
  -d '{"name":"demo-lab","cidr":"10.99.0.0/24","dns_provider_name":"bind-demo","dhcp_provider_name":"kea-demo"}' \
  | jq -r '.id // empty')"
[ -n "$SID" ] && echo "   - subnet id $SID" || echo "   - (subnet may already exist; check the UI)"

cat <<EOF

────────────────────────────────────────────────────────────────────
 READY TO RECORD
   UI:     http://localhost:3000     (login: admin / admin)
   Subnet: demo-lab  10.99.0.0/24    (id ${SID:-?})

 Money shot — in the UI, allocate the next free IP in demo-lab:
   hostname = web01, enable Register DNS (zone demo.lab) + Register DHCP.

 Prove it on the real servers (split-screen with the UI):
   dig @127.0.0.1 -p 15353 web01.demo.lab A +short
   curl -s http://localhost:18000/ -H 'Content-Type: application/json' \\
     -d '{"command":"reservation-get-all","service":["dhcp4"],"arguments":{"subnet-id":1}}' \\
     | jq '.[0].arguments.hosts'

 Tear it all down (wipes state):  scripts/demo-down.sh
────────────────────────────────────────────────────────────────────
EOF
