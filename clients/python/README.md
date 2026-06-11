# ipforge-client

Official Python client for [IPForge](https://github.com/betz-anthony/ipforge) —
IPAM that pushes DNS/DHCP config. Sync, typed, one dependency (`requests`).

## Install

```bash
pip install ipforge-client
```

## Quickstart

```python
from ipforge_client import IPForge

client = IPForge("https://ipforge.example.com", token="ipfg_...")
# or rely on IPFORGE_URL / IPFORGE_TOKEN env vars: IPForge()

# List (auto-paginates across pages, yields typed models)
for addr in client.addresses.list(subnet_id=3, status="assigned"):
    print(addr.address, addr.hostname)

# Single page with total
page = client.addresses.list_page(limit=50, offset=0, subnet_id=3)
print(page.total, [a.address for a in page])

# Allocate the next free IP, registering DNS
result = client.subnets.allocate(3, hostname="web-01", register_dns=True, dns_zone="example.com")
print(result["address"])

# Create a DNS record
client.dns.create_record("example.com", name="web-01", record_type="A", value=result["address"])

# Audit log (cursor-paginated)
for entry in client.audit.list(username="admin"):
    print(entry.action, entry.resource_type)
```

## Errors

All errors derive from `ipforge_client.IPForgeError`:
`AuthError` (401), `ForbiddenError` (403, incl. read-only token writing),
`NotFoundError` (404), `ConflictError` (409), `ValidationError` (422, see
`.detail`), `ServerError` (5xx), `TransportError` (network/timeout).

## Notes

- Sync only. An async client (httpx-based) is a possible future addition.
- Models expose known fields as typed properties and keep the full payload on
  `.raw`, so new API fields never break the client.
- Targets the IPForge `/api/v1` API.
