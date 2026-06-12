# ISC Kea 3.0 DHCPv4 + control-agent for the IPForge demo.
#
# ISC open-sourced ALL hook libraries in Kea 3.0 — including host_cmds, which
# IPForge's `reservation-add` / `reservation-del` require. So this is fully free:
# no subscription. The packages come from ISC's kea-3-0 apt repo (the `isc-kea-*`
# names — NOT Debian's `kea-*`, which are an old 2.2.0 without the hooks).
# The build FAILS if libdhcp_host_cmds.so is absent, so you can't end up
# recording against a Kea that silently rejects reservation-add.
FROM debian:12-slim

ARG KEA_REPO=kea-3-0

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg jq postgresql-client \
 && curl -1sLf "https://dl.cloudsmith.io/public/isc/${KEA_REPO}/setup.deb.sh" | bash \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      isc-kea-dhcp4 isc-kea-ctrl-agent isc-kea-admin isc-kea-hooks isc-kea-pgsql \
 && rm -rf /var/lib/apt/lists/*

# Guarantee host_cmds is present (Kea 3.0 references it by its real arch path,
# /usr/lib/x86_64-linux-gnu/kea/hooks/, which the kea-dhcp4.conf uses; the kea
# service pins platform linux/amd64 so that path is stable).
RUN set -eu; \
    HOOK="$(find /usr/lib -name 'libdhcp_host_cmds.so' 2>/dev/null | head -1)"; \
    if [ -z "$HOOK" ]; then \
      echo "FATAL: libdhcp_host_cmds.so not found — wrong repo? expected isc-kea-hooks from kea-3-0."; \
      exit 1; \
    fi; \
    echo "host_cmds hook present at: $HOOK"

EXPOSE 8000
