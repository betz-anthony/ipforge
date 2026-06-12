# ISC Kea DHCPv4 + control-agent for the IPForge demo (read/list story).
#
# IMPORTANT — reservation PUSH is not free:
# IPForge's keadhcp provider adds reservations with `reservation-add`, which is
# part of the `host_cmds` hook (libdhcp_host_cmds.so). As of Kea 2.7, host_cmds
# is STILL an ISC premium (subscriber-only) hook — it is NOT in the public apt
# repo (which ships lease_cmds, ha, stat_cmds, etc., but not host_cmds). So with
# this free image IPForge can read Kea scopes + leases, but `add_reservation`
# will fail with "command not supported".
#
# For the free DHCP-push money shot, use Pi-hole (see ../README.md A).
# If you have an ISC subscription, drop libdhcp_host_cmds.so into
# /usr/lib/<arch>/kea/hooks/ and add it to kea-dhcp4.conf hooks-libraries.
FROM debian:12-slim

ARG KEA_REPO=kea-2-7

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg jq \
 && curl -1sLf "https://dl.cloudsmith.io/public/isc/${KEA_REPO}/setup.deb.sh" | bash \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      kea-dhcp4-server kea-ctrl-agent kea-admin kea-common \
 && rm -rf /var/lib/apt/lists/*

# If a host_cmds hook is present (e.g. a subscriber mounted/installed it),
# symlink it to the stable path kea-dhcp4.conf expects. Absent = read-only demo.
RUN HOOK="$(find /usr/lib /opt -name 'libdhcp_host_cmds.so' 2>/dev/null | head -1)"; \
    if [ -n "$HOOK" ]; then mkdir -p /usr/lib/kea/hooks && ln -sf "$HOOK" /usr/lib/kea/hooks/libdhcp_host_cmds.so; \
      echo "host_cmds hook present: $HOOK"; \
    else echo "NOTE: no host_cmds hook (premium) — reservation-add unavailable; use Pi-hole for DHCP push."; fi

EXPOSE 8000
