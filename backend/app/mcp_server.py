"""MCP-001 — IPForge MCP server (stdio).

Run:  IPFORGE_URL=https://ipforge.example.com IPFORGE_TOKEN=ipfg_xxx \
      python -m app.mcp_server

Exposes IPForge as Model Context Protocol tools. Authorization is the API token's
role (read-only tokens can call read tools but the API rejects writes).
"""
import os

from mcp.server.fastmcp import FastMCP

from app.mcp_client import IPForgeClient

mcp = FastMCP("ipforge")


def _client() -> IPForgeClient:
    url = os.environ.get("IPFORGE_URL")
    token = os.environ.get("IPFORGE_TOKEN")
    if not url or not token:
        raise RuntimeError("Set IPFORGE_URL and IPFORGE_TOKEN")
    return IPForgeClient(url, token)


# ── read tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def list_subnets() -> list:
    """List all subnets with utilization and metadata."""
    return _client().list_subnets()


@mcp.tool()
def get_subnet(subnet_id: int) -> dict:
    """Get a single subnet by its numeric id."""
    return _client().get_subnet(subnet_id)


@mcp.tool()
def list_addresses(subnet_id: int | None = None, tag: str | None = None) -> list:
    """List IP addresses, optionally filtered by subnet id and/or tag."""
    return _client().list_addresses(subnet_id=subnet_id, tag=tag)


@mcp.tool()
def find_free_ip(subnet_id: int) -> str | None:
    """Return the lowest free IP in a subnet (or null if the subnet is full or too large to map)."""
    return _client().find_free_ip(subnet_id)


@mcp.tool()
def search(query: str) -> dict:
    """Search across subnets, addresses, DNS records and DHCP leases."""
    return _client().search(query)


@mcp.tool()
def list_drift(category: str | None = None, severity: str | None = None,
               needs_review: bool | None = None) -> list:
    """List open drift items (IPAM vs DNS/DHCP/scan discrepancies), with optional filters."""
    return _client().list_drift(category=category, severity=severity, needs_review=needs_review)


@mcp.tool()
def list_discovery(ip: str | None = None, mac: str | None = None) -> list:
    """List SNMP-discovered endpoints (IP/MAC/switchport/VLAN), optionally filtered by ip or mac."""
    return _client().list_discovery(ip=ip, mac=mac)


@mcp.tool()
def ip_history(ip: str) -> dict:
    """Get the lifecycle timeline (changes, drift, reachability) for an IP."""
    return _client().ip_history(ip)


# ── safe-write tools (subject to the token's role) ──────────────────────────────

@mcp.tool()
def allocate_ip(subnet_id: int, hostname: str, mac: str | None = None,
                register_dns: bool = False, register_dhcp: bool = False,
                dns_zone: str | None = None) -> dict:
    """Allocate the next free IP in a subnet for a hostname (idempotent by hostname).
    Optionally register DNS/DHCP. Requires an operator+ token."""
    return _client().allocate_ip(subnet_id, hostname, mac=mac, register_dns=register_dns,
                                 register_dhcp=register_dhcp, dns_zone=dns_zone)


@mcp.tool()
def tag_address(ip: str, tags: list[str]) -> dict:
    """Add tags to an address (preserves existing tags). Requires an operator+ token."""
    return _client().tag_address(ip, tags)


@mcp.tool()
def resolve_drift(drift_id: int, action: str | None = None) -> dict:
    """Resolve a drift item (optional action, e.g. 'import' or 'delete' for orphans).
    Requires an operator+ token."""
    return _client().resolve_drift(drift_id, action=action)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
