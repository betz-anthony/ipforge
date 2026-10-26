// DNSNAME-001 — mirrors backend core/dns_names.py. Returns the zone-relative
// name when `name` ends in `.<zone>` (which the server would suffix again).
// Names with a trailing dot are absolute and never reported.
export function shortNameForZone(name: string, zone: string): string | null {
  const n = name.trim()
  if (n.endsWith('.')) return null // trailing dot = absolute name, nothing appended
  const z = zone.trim().replace(/\.+$/, '')
  if (!n || !z) return null
  const suffix = '.' + z.toLowerCase()
  if (n.toLowerCase().endsWith(suffix) && n.length > suffix.length) {
    return n.slice(0, n.length - suffix.length)
  }
  return null
}
