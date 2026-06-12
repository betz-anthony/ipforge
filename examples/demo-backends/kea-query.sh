#!/usr/bin/env bash
# "dig for the demo Kea" — query the Kea control agent over HTTP and print the
# server's live DHCP state. Analogous to `dig @127.0.0.1 -p 15353 ...` for BIND.
#
#   ./kea-query.sh                 # reservations in subnet 1 (default)
#   ./kea-query.sh leases          # dynamic leases in subnet 1
#   ./kea-query.sh <kea-command>   # any raw dhcp4 command, e.g. config-get
#
# Needs curl + jq on the host. The control agent is published on :18000 by the
# demo compose.
set -euo pipefail
PORT="${KEA_PORT:-18000}"
case "${1:-reservations}" in
  reservations) cmd="reservation-get-all"; filter='.[0].arguments.hosts' ;;
  leases)       cmd="lease4-get-all";      filter='.[0].arguments.leases' ;;
  *)            cmd="$1";                  filter='.[0].arguments' ;;
esac
curl -s "http://localhost:${PORT}/" -H 'Content-Type: application/json' \
  -d "{\"command\":\"${cmd}\",\"service\":[\"dhcp4\"],\"arguments\":{\"subnet-id\":1,\"subnets\":[1]}}" \
  | jq "${filter}"
