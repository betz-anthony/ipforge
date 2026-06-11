"""Single source of truth for which /api/v1 operations the client implements
(COVERED) and which in-scope operations it intentionally omits in this version
(DEFERRED). Consumed by backend/tests/test_client_openapi_drift.py.

Path templates are relative to /api/v1 with every {param} normalized to {}.
"""

IN_SCOPE_PREFIXES = {
    "subnets", "addresses", "vlans", "dns", "dhcp", "drift", "discovery",
    "audit", "search",
}

COVERED = {
    # subnets + allocation
    ("GET", "/subnets"), ("POST", "/subnets"),
    ("GET", "/subnets/{}"), ("PUT", "/subnets/{}"), ("DELETE", "/subnets/{}"),
    ("GET", "/subnets/{}/map"),
    ("GET", "/subnets/{}/ranges"), ("POST", "/subnets/{}/ranges"),
    ("DELETE", "/subnets/{}/ranges/{}"),
    ("POST", "/subnets/{}/allocate"),
    # addresses
    ("GET", "/addresses"), ("POST", "/addresses"),
    ("GET", "/addresses/{}"), ("PUT", "/addresses/{}"), ("DELETE", "/addresses/{}"),
    ("GET", "/addresses/by-ip/{}"),
    ("GET", "/addresses/{}/history"), ("GET", "/addresses/by-ip/{}/history"),
    # vlans
    ("GET", "/vlans"), ("POST", "/vlans"),
    ("GET", "/vlans/{}"), ("PUT", "/vlans/{}"), ("DELETE", "/vlans/{}"),
    # dns
    ("GET", "/dns/zones"),
    ("GET", "/dns/zones/{}/records"), ("POST", "/dns/zones/{}/records"),
    ("DELETE", "/dns/zones/{}/records"),
    ("GET", "/dns/by-ip/{}"),
    # dhcp
    ("GET", "/dhcp/scopes"),
    ("GET", "/dhcp/scopes/{}/leases"),
    ("POST", "/dhcp/scopes/{}/reservations"),
    ("DELETE", "/dhcp/scopes/{}/reservations/{}"),
    ("GET", "/dhcp/by-ip/{}"),
    # read-only
    ("GET", "/drift"),
    ("GET", "/discovery/endpoints"),
    ("GET", "/audit"),
    ("GET", "/search"),
}

DEFERRED = {
    # subnets — capacity/suggestions
    ("GET", "/subnets/suggest-parent"),
    ("GET", "/subnets/forecasts"),
    ("GET", "/subnets/{}/forecast"),
    # addresses — enrichment / preview
    ("GET", "/addresses/{}/scan-history"),
    ("GET", "/addresses/{}/discovery"),
    ("GET", "/addresses/{}/delete-preview"),
    # addresses — reclaim router (mounted under /addresses)
    ("GET", "/addresses/stale"),
    ("GET", "/addresses/stale/count"),
    ("PUT", "/addresses/{}/reclaim"),
    ("POST", "/addresses/stale/bulk-deprecate"),
    # drift — writes/policies
    ("GET", "/drift/stats"),
    ("POST", "/drift/scan"),
    ("POST", "/drift/{}/resolve"),
    ("POST", "/drift/resolve-bulk"),
    ("GET", "/drift/policies"),
    ("PUT", "/drift/policies/{}"),
    ("DELETE", "/drift/policies/{}"),
    # discovery — device management
    ("GET", "/discovery/devices"),
    ("POST", "/discovery/devices"),
    ("PUT", "/discovery/devices/{}"),
    ("DELETE", "/discovery/devices/{}"),
    ("POST", "/discovery/devices/{}/poll"),
}
