# Kea DHCPv4 + control-agent image GUARANTEED to include the host_cmds hook
# (libdhcp_host_cmds.so) — required for IPForge's reservation-add/-del commands.
#
# Why a Dockerfile instead of a stock image: ISC made the hooks (incl. host_cmds)
# open source starting Kea 2.7.x — in 2.6 and earlier host_cmds is premium
# (subscriber-only). This installs 2.7+ from ISC's official repo and FAILS THE
# BUILD if the hook isn't present, so you never get a silently-broken DHCP demo.
#
#   docker compose -f docker-compose.yml \
#     -f examples/demo-backends/docker-compose.demo-backends.yml build kea
#
# If the apt package names drift, the build errors at `apt-get install` — adjust
# KEA_REPO / the package list to match ISC's current naming for your version.
FROM debian:12-slim

# ISC publishes Kea apt repos per minor series at dl.cloudsmith.io/public/isc/.
# kea-2-7 (and later) ship the open-source hooks.
ARG KEA_REPO=kea-2-7

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg jq \
 && curl -1sLf "https://dl.cloudsmith.io/public/isc/${KEA_REPO}/setup.deb.sh" | bash \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      isc-kea-dhcp4 isc-kea-ctrl-agent isc-kea-admin isc-kea-hooks \
 && rm -rf /var/lib/apt/lists/*

# Hard guarantee: build fails loudly if the host_cmds hook is absent.
RUN set -eu; \
    HOOK="$(find /usr/lib /opt -name 'libdhcp_host_cmds.so' 2>/dev/null | head -1)"; \
    if [ -z "$HOOK" ]; then \
      echo "FATAL: libdhcp_host_cmds.so not found — this Kea build lacks host_cmds."; \
      echo "       Use a Kea >= 2.7 repo (open-source hooks) or the isc-kea-hooks package."; \
      exit 1; \
    fi; \
    echo "host_cmds hook present at: $HOOK"; \
    mkdir -p /usr/lib/kea/hooks; \
    ln -sf "$HOOK" /usr/lib/kea/hooks/libdhcp_host_cmds.so   # stable path for kea-dhcp4.conf

EXPOSE 8000
